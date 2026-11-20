"""Email a reading copy to yourself (--email). Plain SMTP from the standard
library: the same paper and settings always send the same message.

Settings, in the [email] section of the settings file:
  to = "you@example.com"          required
  smtp_host = "smtp.gmail.com"    required
  smtp_port = "587"               587 (STARTTLS, the default) or 465 (TLS)
  smtp_user = "you@example.com"   default: to
  from = "you@example.com"        default: smtp_user

The password is never kept in the settings file. It comes from the
LIT_READER_SMTP_PASSWORD environment variable or, on a Mac, from Keychain:
  security add-generic-password -s lit-reader -a you@example.com -w
"""
import os
import re
import shutil
import smtplib
import ssl
import subprocess
from email.message import EmailMessage

MAX_BYTES = 18 * 1000 * 1000  # Gmail refuses messages over 25 MB, and base64 adds a third
KEYCHAIN_SERVICE = "lit-reader"
TYPES = {".epub": ("application", "epub+zip"), ".html": ("text", "html")}


class MailError(Exception):
    pass


def settings(conf, config_path):
    """The [email] settings, checked, with the password found, before any build starts."""
    e = conf.get("email") if isinstance(conf.get("email"), dict) else {}
    missing = [k for k in ("to", "smtp_host") if not e.get(k)]
    if missing:
        raise MailError("--email needs an [email] section in %s with %s. Run: lit-reader setup-email"
                        % (config_path, " and ".join(missing)))
    port = e.get("smtp_port") or "587"
    if port not in ("587", "465"):
        raise MailError("smtp_port must be 587 (STARTTLS) or 465 (TLS), not %s" % port)
    user = e.get("smtp_user") or e["to"]
    return {"to": e["to"], "host": e["smtp_host"], "port": int(port), "user": user,
            "from": e.get("from") or user, "password": password(user)}


def password(user):
    pw = os.environ.get("LIT_READER_SMTP_PASSWORD")
    if pw:
        return pw
    if has_keychain():  # macOS Keychain; arguments, never a shell
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", user, "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.rstrip("\n")
    raise MailError("no email password found for %s. Run lit-reader setup-email to store it in Keychain, "
                    "or set LIT_READER_SMTP_PASSWORD" % user)


def has_keychain():
    return shutil.which("security") is not None


def in_keychain(user):
    return has_keychain() and subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", user],
        capture_output=True).returncode == 0


# Mail services whose server can be filled in from the address, and where their app passwords live.
PROVIDERS = {
    "gmail.com": ("smtp.gmail.com", "Gmail needs an app password, made at https://myaccount.google.com/apppasswords "
                                    "(2-Step Verification has to be on)."),
    "icloud.com": ("smtp.mail.me.com", "iCloud Mail needs an app-specific password, made at https://account.apple.com "
                                       "under Sign-In and Security."),
}
PROVIDERS["googlemail.com"] = PROVIDERS["gmail.com"]
PROVIDERS["me.com"] = PROVIDERS["mac.com"] = PROVIDERS["icloud.com"]
MANAGED = ("to", "smtp_host", "smtp_port", "smtp_user", "from")
ADDRESS = re.compile(r"[^@\s\"'\\]+@[^@\s\"'\\]+\.[^@\s\"'\\]+")
SECTION = re.compile(r"\s*\[([A-Za-z0-9_-]+)\]\s*")  # the same rule as core.read_settings
UNQUOTABLE = re.compile(r"[\"\\\n]")


def ask(label, default=None, check=None, why=""):
    while True:
        got = input("%s%s: " % (label, " [%s]" % default if default else "")).strip() or default or ""
        if got and (check is None or check(got)):
            return got
        print("  " + (why or "This one is needed."))


def yes(label, default=True):
    got = input("%s [%s] " % (label, "Y/n" if default else "y/N")).strip().lower()
    return default if not got else got.startswith("y")


def with_section(text, values):
    """The settings file's text with its [email] keys set to values. Other
    sections, other keys and comments are kept as they were."""
    lines = text.splitlines()
    body = ['%s = "%s"' % (k, values[k]) for k in MANAGED if values.get(k)]
    start = next((i for i, l in enumerate(lines) if (SECTION.fullmatch(l) or [None, None])[1] == "email"), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines + ([""] if lines else []) + ["[email]"] + body) + "\n"
    end = next((i for i in range(start + 1, len(lines)) if SECTION.fullmatch(lines[i])), len(lines))
    kept = [l for l in lines[start + 1:end] if not re.match(r"\s*(%s)\s*=" % "|".join(MANAGED), l)]
    return "\n".join(lines[:start + 1] + body + kept + lines[end:]) + "\n"


def setup(config_path, read_settings, version):
    """lit-reader setup-email: ask for the settings, write them, store the
    password and send a test. Returns the exit status."""
    try:
        return run_setup(config_path, read_settings, version)
    except (KeyboardInterrupt, EOFError):
        print("\nstopped; anything confirmed before this was kept.")
        return 1


def run_setup(config_path, read_settings, version):
    conf = read_settings(config_path) if config_path.is_file() else {}
    old = conf.get("email") if isinstance(conf.get("email"), dict) else {}
    print("This sets up --email, which sends reading copies through your own mail account.\n"
          "Press Return to keep the value in brackets.\n")
    to = ask("Your email address (copies go here)", old.get("to"), ADDRESS.fullmatch,
             "That doesn't look like an email address.")
    host_default, hint = PROVIDERS.get(to.rsplit("@", 1)[1].lower(), (None, ""))
    if old.get("to") and old["to"].rsplit("@", 1)[-1].lower() != to.rsplit("@", 1)[1].lower():
        old = {}  # a new mail service: the old server and login don't carry over
    host = ask("Mail server (SMTP)", old.get("smtp_host") or host_default,
               lambda v: re.fullmatch(r"[A-Za-z0-9.:-]+", v),
               "That should be a server name such as smtp.example.com, or an address such as 127.0.0.1.")
    port = ask("Port, 587 or 465", old.get("smtp_port") or "587", lambda v: v in ("587", "465"),
               "587 (STARTTLS) or 465 (TLS); 587 suits most services.")
    user = ask("Login name", old.get("smtp_user") or to, lambda v: not re.search(r"[\s\"'\\]", v),
               "A login name can't contain spaces or quotes.")
    sender = old.get("from") if old.get("from") and not UNQUOTABLE.search(old["from"]) else None
    if old.get("from") and not sender:
        print("  Your from line can't be written back as it is, so it's left out: %s" % old["from"])
    values = {"to": to, "smtp_host": host, "smtp_port": port, "smtp_user": user if user != to else None,
              "from": sender}
    new = with_section(config_path.read_text(encoding="utf-8") if config_path.is_file() else "", values)
    print("\nThe [email] section of %s will read:\n" % config_path)
    print("\n".join('  %s = "%s"' % (k, values[k]) for k in MANAGED if values.get(k)))
    if not yes("\nWrite it?"):
        print("Nothing was written.")
        return 1
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_path.with_name(config_path.name + ".tmp")
    try:
        tmp.write_text(new, encoding="utf-8")
        read_settings(tmp)  # the file must still read back before it replaces the old one
        os.replace(str(tmp), str(config_path))
    finally:
        if tmp.exists():
            tmp.unlink()
    print("wrote %s" % config_path)

    print()
    if hint:
        print(hint)
    if os.environ.get("LIT_READER_SMTP_PASSWORD"):
        print("LIT_READER_SMTP_PASSWORD is set, so lit-reader uses that password.")
    elif has_keychain():
        if not in_keychain(user) or yes("Keychain already holds a password for %s. Replace it?" % user, False):
            print("Keychain will ask for the password twice. It is kept in Keychain, not in the settings file.")
            r = subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", user,
                                "-l", "lit-reader email", "-w"])  # -w last, with no value: security prompts for it
            if r.returncode != 0:
                print("Keychain didn't store it. To try again: lit-reader setup-email")
                return 1
            print("stored the password in Keychain")
    else:
        print("Set the LIT_READER_SMTP_PASSWORD environment variable to your password, then run this again to test.")
        return 0

    if not yes("\nSend a test email to %s now?" % to):
        return 0
    try:
        s = settings(read_settings(config_path), config_path)
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = "lit-reader test", s["from"], s["to"]
        m.set_content("Your email settings work. To send a paper:\n\n  lit-reader paper.pdf --email\n\n"
                      "Sent by lit-reader %s.\n" % version)
        send(s, m)
    except MailError as e:
        print("The test didn't go through: %s\nRun lit-reader setup-email again to change anything." % e)
        return 1
    print("sent. If it arrives, --email is ready.")
    return 0


def message(s, path, title, reference, version):
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise MailError("%s is %.1f MB, too large to email; most mail services stop at 25 MB"
                        % (path.name, len(data) / 1e6))
    kind = TYPES.get(path.suffix)
    if not kind:
        raise MailError("can't email %s: only .epub and .html copies are sent" % path.name)
    how = ("On an iPhone, open it from Mail and it goes into Apple Books; in the Gmail app, use the share button and choose Books."
           if path.suffix == ".epub" else
           "Open it in a browser. A phone's attachment preview shows the text but may not run the page's script.")
    m = EmailMessage()
    m["Subject"] = "Reading copy: %s" % title
    m["From"] = s["from"]
    m["To"] = s["to"]
    m.set_content("%s\n\nAttached: %s (%.1f MB). %s\n\nSent by lit-reader %s.\n"
                  % (reference, path.name, len(data) / 1e6, how, version))
    m.add_attachment(data, maintype=kind[0], subtype=kind[1], filename=path.name)  # base64, so no server can re-encode it
    return m


def send(s, m):
    ctx = ssl.create_default_context()
    try:
        tls = s["port"] == 465
        with (smtplib.SMTP_SSL(s["host"], 465, context=ctx, timeout=60) if tls
              else smtplib.SMTP(s["host"], 587, timeout=60)) as server:
            if not tls:
                server.starttls(context=ctx)  # never log in over an unencrypted connection
            server.login(s["user"], s["password"])
            server.send_message(m)
    except smtplib.SMTPAuthenticationError:
        raise MailError("%s refused the login for %s. Gmail and many providers need an app password, not your normal one."
                        % (s["host"], s["user"]))
    except UnicodeError:  # smtplib sends the login in ASCII
        raise MailError("the login name or password has a character outside plain ASCII, which mail servers don't accept")
    except (smtplib.SMTPException, OSError) as e:
        raise MailError("couldn't send through %s: %s" % (s["host"], e))
