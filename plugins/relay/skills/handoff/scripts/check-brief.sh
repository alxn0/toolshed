#!/usr/bin/env bash
# Check that a file follows the handoff brief format of ../brief.md.
#
# Usage: check-brief.sh <brief>
# Checks the file name (<YYYY-MM-DD>-<slug>.md), the frontmatter (from, date),
# the "# " title and every "## " section of the template. Prints nothing when
# the brief is valid, else the first problem on stderr.
# Exit codes: 0 valid, 1 invalid, 64 usage.
set -euo pipefail

readonly BRIEF_NAME_PATTERN='^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9]+(-[a-z0-9]+)*\.md$'
BRIEF_TEMPLATE="$(dirname "$(realpath "$0")")/../brief.md"
readonly BRIEF_TEMPLATE

fail() { echo "check-brief.sh: $1" >&2; exit 1; }

(($# == 1)) || { echo "usage: check-brief.sh <brief>" >&2; exit 64; }
brief="$1"

[[ -f $brief ]] || fail "$brief: not found"
[[ $(basename "$brief") =~ $BRIEF_NAME_PATTERN ]] ||
  fail "$brief: name must be <YYYY-MM-DD>-<slug>.md"

# Frontmatter: the lines between a first-line "---" and the next "---".
frontmatter=$(awk 'NR == 1 { if ($0 != "---") exit 1; next }
  $0 == "---" { is_closed = 1; exit }
  { print }
  END { if (!is_closed) exit 1 }' "$brief") ||
  fail "$brief: missing frontmatter between \"---\" lines"
grep -qE '^from: *[^ ]' <<<"$frontmatter" || fail "$brief: frontmatter missing \"from:\""
grep -qE '^date: *[0-9]{4}-[0-9]{2}-[0-9]{2} *$' <<<"$frontmatter" ||
  fail "$brief: frontmatter missing \"date: <YYYY-MM-DD>\""

grep -qE '^# +[^ ]' "$brief" || fail "$brief: missing \"# <title>\" line"

[[ -r $BRIEF_TEMPLATE ]] || fail "template $BRIEF_TEMPLATE not found"
# Required sections are the "## " headings inside the template's code fence.
mapfile -t required_lines < <(awk '/^```/ { in_fence = !in_fence; next } in_fence && /^## /' "$BRIEF_TEMPLATE")
((${#required_lines[@]} > 0)) || fail "no \"## \" sections in $BRIEF_TEMPLATE"
for required_line in "${required_lines[@]}"; do
  grep -qxF -- "$required_line" "$brief" || fail "$brief: missing \"$required_line\""
done
