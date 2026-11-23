# toolshed

A shared Claude Code plugin marketplace of small utilities. Enable only the plugins you want.

| Plugin | Skill | Trigger | Does |
|---|---|---|---|
| `relay` | `handoff` | `/handoff <target>` | Draft a self-contained brief of the session, approve it, copy it to `<target>:inbox/`, or with `--local` stage it in `~/send/` for the receiver to pull |
| | `inbox` | `/inbox [--pull <host>]` | Plan and do a received brief with approval, then delete it or queue what is left; `--pull` first moves the briefs staged on `<host>` into `~/inbox/` |
| | `whereami` | `/whereami` | Print `user@host:cwd` of the session |
| | `spawn` | `/spawn <folder>` | Start Claude with Remote Control in a detached tmux session in a folder (path, or a word resolved via `z` then `find`, approved by you) |
| | `opencode` | `/opencode <model-hint> <request>` | Send a read-only prompt to another model through opencode (model matched from `opencode models`, approved by you) and check its reply |
| `modes` | `chat` | `/chat` | Read-only discussion mode: read files, search the web, no code changes |
| | `wait` | `/wait` | Present a plan and wait for confirmation before implementing |
| | `go` | `/go` | Finisher: simplify, test end-to-end, code-review. No commit |
| `coding` | `python` | auto on `*.py` | Python conventions and tooling (uv, ruff, ty, polars) |
| | `golang` | auto on `*.go` | Go conventions and tooling (mise, gofmt, go vet, staticcheck) |
| `memo` | `todo` | `/todo`, and when work leaves something open | Track the project's open items in a managed `TODO.md` (`You`, `Now`, `Next`, `Later`), checked after every edit by a hook |
| | `note` | `/note <title>` | Fleeting notes (research, design, work in progress), written only on request, until turned into docs |
| `debrief` | `debrief` | `/debrief [session\|repo\|machine] [period]` | Report what was done today (or another period) in the session, the repository or across the machine: features, fixes, PRs and issues, unfinished work, from git, GitHub events and transcripts |

## Install

Add to `~/.claude/settings.json`, keeping only the plugins you want:

```json
{
  "extraKnownMarketplaces": {
    "toolshed": { "source": { "source": "github", "repo": "alxn0/toolshed" }, "autoUpdate": true }
  },
  "enabledPlugins": {
    "relay@toolshed": true,
    "modes@toolshed": true,
    "coding@toolshed": true,
    "memo@toolshed": true,
    "debrief@toolshed": true
  }
}
```

Or from the CLI:

```bash
claude plugin marketplace add alxn0/toolshed
claude plugin install relay@toolshed   # repeat per plugin
```

`opencode` needs [opencode](https://opencode.ai) and `jq`. Provider API keys can live in
[passage](https://github.com/FiloSottile/passage) as `opencode/<ENV_VAR>` (e.g.
`passage insert opencode/GEMINI_API_KEY`): the script exports each one to opencode's private
server only, so no key is stored unencrypted. `debrief` reads GitHub through `gh` when it is logged in. `memo` needs [folio](https://github.com/dixie6502/folio) on `PATH`, and `note` needs `wkref` for
its links. Every `TODO.md` and note lives in the current folder's folio notebook, outside the
clones: the owner's `notebooks/` store (the owner's notes repository cloned into
`~/<host>/<owner>/notebooks`), or a local `notes/` folder elsewhere. folio's `folio-sync` service
syncs the stores; `memo` never commits. Do not enable it next to another plugin that ships a `todo`
skill: both would manage open items. Design: [`plugins/memo/ARCHITECTURE.md`](plugins/memo/ARCHITECTURE.md).

Skills answer to their bare name (`/go`) unless another skill uses it; then use `/<plugin>:<skill>`,
e.g. `/modes:go`.

## Layout

```
.claude-plugin/marketplace.json   lists every plugin
plugins/<plugin>/
  .claude-plugin/plugin.json      plugin manifest
  skills/<skill>/SKILL.md         one folder per skill
```

To add a plugin: create `plugins/<plugin>/` with that layout, then add it to `marketplace.json`.
To add a skill to an existing plugin: add `plugins/<plugin>/skills/<skill>/` and list it in the
plugin's `description`.

## Develop

Register the local clone instead of GitHub; it is loaded in place, so edits apply
after `/reload-plugins`:

```bash
claude plugin marketplace add ~/GitHub/alxn0/toolshed
claude plugin install relay@toolshed
```

Check the layout with `claude plugin validate .` (marketplace) or
`claude plugin validate plugins/<plugin>`.
