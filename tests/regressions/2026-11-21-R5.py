"""R5: no transition on .bar or .progress may come after the reduced-motion block that turns them off."""
import re, sys
from pathlib import Path
css = (Path(__file__).resolve().parents[2] / "src/lit_reader/reader.css").read_text(encoding="utf-8")
# rules that only apply when motion is fine are allowed anywhere
css = re.sub(r"@media \(prefers-reduced-motion: no-preference\) \{(?:[^{}]*\{[^}]*\})*\s*\}", "", css)
rm = max(m.start() for m in re.finditer(r"@media \(prefers-reduced-motion: reduce\)", css))
late = [m.group(0) for m in re.finditer(r"(?m)^\s*\.(bar|progress)\s*\{[^}]*transition[^}]*\}", css) if m.start() > rm]
print("R5", "pass" if not late else "FAIL %r" % late)
sys.exit(0 if not late else 1)
