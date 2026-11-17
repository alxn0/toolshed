#!/usr/bin/env bash
# Pull the handoff briefs staged by `send.sh --local` on another machine.
#
# Usage: pull.sh <host>
#   <host>  ssh destination of the sender: an alias or user@host, no path
# Copies every <host>:send/*.md into ~/inbox/, then deletes them on <host>.
# Refuses everything if one name is unsafe or already in ~/inbox. Prints the
# pulled files, or "nothing staged on <host>".
# Exit codes: 0 pulled or nothing staged, 1 refused or ssh/scp failed, 64 usage.
set -euo pipefail

readonly INBOX_DIR="$HOME/inbox"
# Names safe to pass to the remote shell; check-brief.sh checks the exact format.
readonly SAFE_NAME_PATTERN='^[A-Za-z0-9._-]+\.md$'
# Remote command printing one staged file name per line; no ~/send means none.
# shellcheck disable=SC2016 # expands on the remote side
readonly LIST_STAGED='cd send 2>/dev/null || exit 0; for f in *.md; do [ -f "$f" ] && echo "$f"; done; exit 0'

fail() { echo "pull.sh: $1" >&2; exit 1; }

(($# == 1)) || { echo "usage: pull.sh <host>" >&2; exit 64; }
host="$1"
[[ $host != -* && $host != *[:/]* ]] ||
  fail "host \"$host\" must be an ssh alias or user@host, without path or options"

staged=$(ssh -- "$host" "$LIST_STAGED") || fail "ssh to $host failed"
mapfile -t names < <(printf '%s' "$staged")
if ((${#names[@]} == 0)); then
  echo "nothing staged on $host"
  exit 0
fi

for name in "${names[@]}"; do
  [[ $name =~ $SAFE_NAME_PATTERN ]] || fail "$host:send/$name: unsafe file name, nothing pulled"
  [[ ! -e $INBOX_DIR/$name ]] || fail "$INBOX_DIR/$name already exists, nothing pulled"
done

mkdir -p "$INBOX_DIR"
scp -q -- "${names[@]/#/$host:send/}" "$INBOX_DIR/" || fail "scp from $host:send/ failed"
ssh -- "$host" "cd send && rm -- ${names[*]}" ||
  fail "pulled into $INBOX_DIR/, but could not delete them in $host:send/"
printf 'pulled %s\n' "${names[@]}"
echo "from $host:send/ into $INBOX_DIR/ (deleted on $host)"
