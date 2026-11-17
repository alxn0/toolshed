#!/usr/bin/env bash
# Close a handoff brief in ~/inbox.
#
# Usage: close.sh <file> done|accepted
#   <file>     bare file name of a brief in ~/inbox (no path)
#   done       delete the brief: all its work is done
#   accepted   move it to ~/inbox/accepted/: open items were queued elsewhere
# Fails if <file> has a path or is not a regular .md file in ~/inbox, or if
# ~/inbox/accepted/<file> already exists.
# Exit codes: 0 closed, 1 refused, 64 usage.
set -euo pipefail

readonly INBOX_DIR="$HOME/inbox"
readonly ACCEPTED_DIR="$INBOX_DIR/accepted"

fail() { echo "close.sh: $1" >&2; exit 1; }
usage() { echo "usage: close.sh <file> done|accepted" >&2; exit 64; }

(($# == 2)) || usage
file="$1"
outcome="$2"

# A bare name keeps rm and mv inside ~/inbox: the name comes from another machine.
[[ $file != */* && $file == *.md ]] || fail "\"$file\" must be a bare .md file name"
brief="$INBOX_DIR/$file"
[[ -f $brief && ! -L $brief ]] || fail "$brief: not a regular file"

case "$outcome" in
  done)
    rm -- "$brief"
    echo "deleted $brief"
    ;;
  accepted)
    mkdir -p "$ACCEPTED_DIR"
    [[ ! -e $ACCEPTED_DIR/$file ]] || fail "$ACCEPTED_DIR/$file already exists"
    mv -- "$brief" "$ACCEPTED_DIR/"
    echo "moved $file to $ACCEPTED_DIR/"
    ;;
  *) usage ;;
esac
