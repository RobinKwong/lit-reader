#!/bin/sh
# Every saved reproduction from code reviews. Exits non-zero if any fails.
# Browser checks in browser/ run through chrome-devtools evaluate_script; see each file's header.
cd "$(dirname "$0")" || exit 1
fail=0
for f in 20*.py; do python3 -I "$f" || fail=1; done
exit $fail
