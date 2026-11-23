#!/usr/bin/env bash
# Find opencode models and send them read-only prompts.
#
# Usage:
#   opencode.sh models <dir> [<word>...]
#     Print the model ids (provider/model) containing every word, case-insensitive.
#   opencode.sh ask <dir> <model> [<session>] < prompt
#     Send the prompt on stdin, print the reply, then `session=<id> cost=<usd>`.
# <dir> is the folder opencode runs in: the repository the model can read, and the
# project config that may add providers. Prompts run in a private opencode server
# with this script's own agent, which can only glob, grep and read files, never
# .env files.
# Exit codes: 0 done, 1 no model matches or opencode failed, 2 opencode or jq
# missing, 64 usage.
set -euo pipefail

# The agent is defined here, not borrowed: opencode's `plan` preset allows bash
# and web fetches, and a project config could redefine it.
readonly AGENT=relay-readonly
readonly AGENT_CONFIG='{"agent":{"relay-readonly":{
  "description":"Read-only agent for prompts relayed from Claude Code.",
  "mode":"primary",
  "permission":{"*":"deny","glob":"allow","grep":"allow",
                "read":{"*":"allow","*.env":"deny","*.env.*":"deny"}}}}}'

fail() { echo "opencode.sh: $1" >&2; exit 1; }
usage() { echo "usage: opencode.sh models <dir> [<word>...] | ask <dir> <model> [<session>] < prompt" >&2; exit 64; }

# opencode's installer puts it in ~/.opencode/bin, which non-login shells may not have.
PATH=$PATH:$HOME/.opencode/bin
for tool in opencode jq; do
  command -v "$tool" >/dev/null || { echo "$tool is not installed (see toolshed's README)" >&2; exit 2; }
done

# Exports provider keys kept in passage as opencode/<ENV_VAR> (e.g. opencode/GEMINI_API_KEY).
# They reach only opencode's private (--standalone) server, never a file or the shared service.
export_passage_keys() {
  command -v passage >/dev/null || return 0
  local entry name value
  for entry in "${PASSAGE_DIR:-$HOME/.passage/store}"/opencode/*.age; do
    [[ -e $entry ]] || continue
    name=$(basename "$entry" .age)
    [[ $name =~ ^[A-Z][A-Z0-9_]*$ ]] || fail "passage entry opencode/$name is not an environment variable name"
    value=$(passage show "opencode/$name") || fail "could not read passage entry opencode/$name"
    export "$name=${value%%$'\n'*}"
  done
}

list_models() {
  local all matches word
  all=$(opencode models --standalone) || fail "could not list models"
  matches=$all
  for word in "$@"; do
    matches=$(grep -iF -- "$word" <<<"$matches" || true)
  done
  [[ -n $matches ]] || fail "no model matches: $*. Available:"$'\n'"$all"
  echo "$matches"
}

ask() {
  local model=$1 session=${2:-}
  local args=(run --standalone --agent "$AGENT" --archived --format json -m "$model")
  [[ -n $session ]] && args+=(-s "$session")
  OPENCODE_CONFIG_CONTENT=$AGENT_CONFIG opencode "${args[@]}" | jq -rs '
    (map(select(.type == "error"))[0] // empty | "opencode.sh: \(.error.message)\n" | halt_error(1)),
    (map(select(.type == "text").part.text) | join("\n")
      | if . == "" then "opencode.sh: no reply\n" | halt_error(1) end),
    "session=\(.[0].sessionID) cost=\(map(select(.type == "step_finish").part.cost) | add)"'
}

(($# >= 2)) || usage
command=$1 dir=$2
shift 2
[[ -d $dir ]] || fail "no such folder: $dir"
cd "$dir"
export_passage_keys
case $command in
  models) list_models "$@" ;;
  ask) (($# == 1 || $# == 2)) || usage; ask "$@" ;;
  *) usage ;;
esac
