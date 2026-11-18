# memo: architecture

`memo` (Latin *memorandum*, "to be remembered") holds what is authored, written by
the user or Claude: open items (`todo`) and working notes (`note`), the only data
that follows the user from host to host. It works alone; a reader such as a debrief
may read its files, whose formats it owns.

Moved from `dixie6502/mneme` on 2026-11-18, so that mneme holds only the memory
derived from transcripts.

## Notebooks

Authored data lives in [folio](https://github.com/dixie6502/folio)'s notebooks,
outside every clone: each folder's `TODO.md` and notes. folio owns the layout
and its sync; `memo` owns the formats of `TODO.md` and notes, and finds a
folder's notebook with `folio --dir`. Claude meets them only when a skill reads
them on purpose, never through a search of the project.

```
~/<host>/<owner>/
  <repo>/                     a clone: no notes inside
  notebooks/                  the owner's store: a git clone with a private remote
    .folio                    store marker
    <repo>/                   the clone's notebook
      .notebook               notebook marker
      TODO.md
      todo/                   item detail files, deleted with their item
      <note>.md
<folder>/notes/               any other folder's notebook, local and unsynced
```

- **Notebook**: the current folder's, as `folio --dir` prints it: a clone's in
  its owner's store, else the nearest `notes/`. There is no global notebook: a
  folder gets one with `folio init` (or `/todo init`, `/note`), elsewhere the
  skills refuse.
- **Stores are set up by the user**, by cloning the owner's notes repository
  into `~/<host>/<owner>/notebooks`. With no store there, `/todo init` and
  `/note` relay folio's refusal and ask: set up the store, or a local `notes/`
  (`--local`). Without a terminal, folio never decides for the user.
- Nothing is written into clones: no `TODO.md`, no `note/`. A project's files
  are found only through folio, never by searching it.
- `folio check` reports notebooks gone astray (orphans, strays) and stores that
  do not sync; `folio mv` moves a folder with its notebook.
- Requires the Go folio on `PATH`.

### Sync

folio's `folio-sync` service (a systemd user unit running `folio sync
--daemon`) commits, merges and pushes every store, keeping both sides of a
conflict and scanning with `gitleaks` before each push. `memo` has no sync of
its own and never commits a store. A finished item is deleted, and the store's
history keeps it. A local `notes/` has neither sync nor history.

## todo

Open items per notebook in `<notebook>/TODO.md`: questions and actions for the
user (`You`), then `Now`, `Next`, `Later`. Done items are deleted; the store's
history records them.

- **The `TODO.md` format is an interface**, owned by `todo` with its check
  script (`skills/todo/scripts/todo.sh check`). Other tools reference it, never
  copy it. A `PostToolUse` hook runs the check after every edit of a managed
  `TODO.md`.
- Long item detail goes in a detail file under `<notebook>/todo/`, linked from
  the item, and deleted with it.
- When adding an item, the user may name an existing note to link. todo never
  creates or deletes a note.

## note

Fleeting notes: research, design, work in progress. A note exists to be turned
into docs, which do not exist at first and are generated from the notes later.

- Created only by the user, through `note` (`disable-model-invocation`); needs
  `wkref` for links.
- Location: the current folder's notebook, beside its `TODO.md`.
  `[[wikilinks]]`, checked with `wkref check --root <notebook>`.
- Versioned and synced with their store (a local `notes/` is neither); a project
  repo never sees them.
- Each note has a `created` date (frontmatter, else the file's mtime). Notes older
  than 28 days are stale: `note list` and `note check` show them, and a debrief
  can list them.
- Operations: write (create or update), `list`, `check`, `convert` (lasting
  content into the project's `README.md`, `ARCHITECTURE.md`, `CLAUDE.md` or
  `docs/`, after the user approves the edits), `delete` (explicit yes only, with
  `wkref rm`).
- A note is deleted only with the user, never automatically: once its content is
  in docs, or (no docs target) once its findings are recorded elsewhere.
- Shared notes (meeting notes, for instance) are made by the user, from these
  files, when needed; memo publishes nothing.
- Exception: research repos, where the paper is the doc. The paper is
  versioned in its repo; notes feed it.
