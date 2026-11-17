#!/usr/bin/env bash
# Send a handoff brief to the inbox of another machine, or stage it locally.
#
# Usage: send.sh <target> <brief>
#   <target>  ssh destination without path: an alias (dixie) or user@host;
#             or --local to stage the brief in ~/send/ for the receiver to pull
#   <brief>   local file following ../brief.md, checked by check-brief.sh
# Copies <brief> to <target>:inbox/, or to ~/send/ with --local. Fails if the
# target is not a bare [user@]host, if check-brief.sh refuses the brief, if
# ~/inbox is missing on the target, or if ~/send/<brief> already exists.
# Exit codes: 0 sent or staged, 1 refused or copy failed, 64 usage.
set -euo pipefail

readonly TARGET_PATTERN='^([A-Za-z0-9._-]+@)?[A-Za-z0-9][A-Za-z0-9._-]*$'
readonly LOCAL_TARGET="--local"
readonly SEND_DIR="$HOME/send"
CHECK_BRIEF="$(dirname "$(realpath "$0")")/check-brief.sh"
readonly CHECK_BRIEF

fail() { echo "send.sh: $1" >&2; exit 1; }

(($# == 2)) || { echo "usage: send.sh <target> <brief>" >&2; exit 64; }
target="$1"
brief="$2"

# A bare [user@]host keeps scp from writing outside inbox/ or reading an option.
[[ $target == "$LOCAL_TARGET" || $target =~ $TARGET_PATTERN ]] ||
  fail "target \"$target\" must be $LOCAL_TARGET, an ssh alias or user@host, without path or options"
"$CHECK_BRIEF" "$brief" || exit 1
brief_name=$(basename "$brief")

if [[ $target == "$LOCAL_TARGET" ]]; then
  mkdir -p "$SEND_DIR"
  [[ ! -e $SEND_DIR/$brief_name ]] || fail "$SEND_DIR/$brief_name already exists"
  cp -- "$brief" "$SEND_DIR/"
  cat <<EOF
staged $brief_name in $SEND_DIR/
on the receiver, pull it into the inbox and process it with:
  /inbox --pull <ssh alias of this machine, e.g. $(whoami)@$(hostname)>
EOF
  exit 0
fi

scp -q -- "$brief" "$target:inbox/" ||
  fail "scp to $target:inbox/ failed (does ~/inbox exist on $target?)"
echo "sent $brief_name to $target:inbox/"
