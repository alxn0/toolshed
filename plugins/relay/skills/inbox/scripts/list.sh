#!/usr/bin/env bash
# List handoff briefs waiting in ~/inbox: one line per brief, "<file>  <title>",
# or "<file>  INVALID: <problem>" when the handoff skill's check-brief.sh refuses
# it. Prints "inbox empty" when there is none. Read-only.
set -euo pipefail

readonly INBOX_DIR="$HOME/inbox"
CHECK_BRIEF="$(dirname "$(realpath "$0")")/../../handoff/scripts/check-brief.sh"
readonly CHECK_BRIEF

shopt -s nullglob
briefs=("$INBOX_DIR"/*.md)
if ((${#briefs[@]} == 0)); then
  echo "inbox empty"
  exit 0
fi
for brief in "${briefs[@]}"; do
  if problem=$("$CHECK_BRIEF" "$brief" 2>&1); then
    title=$(grep -m1 -E '^# +[^ ]' "$brief")
    echo "$(basename "$brief")  ${title#"# "}"
  else
    echo "$(basename "$brief")  INVALID: ${problem#"check-brief.sh: $brief: "}"
  fi
done
