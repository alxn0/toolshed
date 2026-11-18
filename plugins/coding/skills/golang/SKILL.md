---
description: Go development patterns, tooling (mise, gofmt, go vet, staticcheck), naming, structure, error handling and testing conventions. Auto-loads when working with .go files.
paths: "**/*.go"
---

# Go Development Patterns

## Language Preferences

- Use the current stable Go, pinned per project in `mise.toml` and in the `go`
  line of `go.mod`, so every machine builds with the same toolchain.
- Code style is whatever `gofmt` outputs; there is no line-length rule.
- Standard library first: add a dependency only when the standard library has
  no reasonable equivalent. Each dependency is code to audit and update.
- No cgo in builds: prefer pure-Go dependencies so a plain `go build` works
  everywhere, including cross-compiles.

## Tools & Environment

**Toolchain**: one `mise.toml` at the project root, with the current stable Go
version:

```toml
[tools]
go = "<current stable>"
"go:honnef.co/go/tools/cmd/staticcheck" = "latest"
```

mise is installed on some machines only. Where it is missing, still write
`mise.toml` for the others, use the Go toolchain on `PATH`, and run staticcheck
with `go run honnef.co/go/tools/cmd/staticcheck@latest ./...` rather than
installing it.

**Code quality** before a commit:

```bash
gofmt -l .           # formatting: prints nothing when clean
go vet ./...         # suspicious constructs
staticcheck ./...    # bugs, dead code, simplifications
go test ./...        # tests
```

Add `scripts/check.sh` only when a project needs more than these four, such as
code generation or a build step, so the full sequence lives in one place.

**Dependencies**: `go mod tidy` after adding or removing an import; commit
`go.sum`.

## Preferred Libraries

- **CLI**: the standard `flag` package for a single command;
  `github.com/spf13/cobra` once there are subcommands
- **SQLite**: `modernc.org/sqlite` (pure Go)
- **PostgreSQL**: `github.com/jackc/pgx/v5`, queries generated with `sqlc` when
  there are many
- **Config**: flags and environment variables first; a TOML file only when
  needed
- **Logging**: `log/slog`
- **Concurrency**: `golang.org/x/sync/errgroup`

## Naming Conventions

- **Packages**: short, lowercase, one word, no underscores (`store`, `render`),
  named by what they provide. Names like `util`, `common` or `helpers` say
  nothing and attract unrelated code.
- **Files**: `snake_case.go`, tests beside them as `snake_case_test.go`
- **Exported identifiers**: `PascalCase`; unexported: `camelCase`
- **Initialisms**: keep one case (`userID`, `HTTPClient`, `parseURL`)
- **No stutter**: `store.Open`, not `store.OpenStore`; the package name is
  already part of every call
- **Interfaces**: one method → method name + `er` (`Reader`); otherwise named by
  role
- **Constants**: `camelCase` or `PascalCase` like any identifier, not
  `SCREAMING_SNAKE_CASE`
- **Abbreviations**: descriptive names everywhere, except this closed list of Go
  idioms:
  - `ctx` (`context.Context`), `err` (`error`), `ok` (comma-ok results)
  - one- or two-letter method receivers named after the type
    (`func (s *Store)`)
  - `i`, `j` as loop indexes in loops of a few lines

## Project Structure

```
project/
├── cmd/<binary>/          # main package, one folder per binary: flags, wiring, exit codes
├── internal/<package>/    # all other code; not importable by other modules
├── testdata/              # fixtures and golden files, ignored by the go tool
├── scripts/               # project scripts, when needed
├── tmp/                   # temporary files (testing, scratch)
├── go.mod
└── mise.toml
```

- Organize packages by domain (`store`, `render`), not by technical layer
  (`models`, `services`), so a change stays inside one package.
- Start with few packages; split one only when it has two clear
  responsibilities.
- No `pkg/` folder: code is `internal/` unless another module really imports
  it.
- `main` stays thin: parse input, build dependencies, call `internal/`, and map
  errors to exit codes in one place.

## Programming Paradigms

**Plain functions and structs first**:
- Functions over methods when there is no state to hold
- Structs hold data; methods only when they need the struct's fields
- Make the zero value useful, or provide one constructor `NewX` that validates
- Composition through fields; embedding only to promote a small, intended
  method set

**Interfaces**:
- Define an interface where it is consumed, not where it is implemented
- Accept interfaces, return concrete types
- Wait for a second implementation before adding an interface; one
  implementation behind an interface is indirection with no benefit

**Generics**: only to remove real duplication across types, not in advance.

**Concurrency** (only when there is a measured or obvious need):
- `context.Context` as the first parameter of anything that blocks or does I/O
- `errgroup` over raw goroutines and `sync.WaitGroup` when errors matter
- The goroutine's creator is responsible for stopping it, so none outlive
  their work

## Error Handling

- Return errors; `panic` only for programmer bugs, not expected failures
- Wrap with context: `fmt.Errorf("open store %s: %w", path, err)`; message is
  lowercase, no trailing punctuation
- Sentinel errors (`var ErrNotFound = errors.New("not found")`) or typed errors
  for callers that branch; check with `errors.Is` / `errors.As`, since string
  comparison breaks when a message changes
- Handle an error once: either return it or log it, not both
- Validate input at the boundary (`cmd/`, HTTP handlers) with descriptive
  messages
- `defer` cleanup right after acquiring a resource; check the error of `Close`
  on writes, where it can report lost data

## Testing Patterns

- Standard `testing` package only, no assertion library
- Table-driven tests with `t.Run` subtests named by scenario
- Fixtures and golden files in `testdata/`; regenerate golden files with an
  `-update` flag
- Real dependencies, no mocks: a temporary SQLite file (`t.TempDir()`), a real
  local PostgreSQL, a real HTTP server from `net/http/httptest`
- `t.Helper()` in helpers, `t.Cleanup()` for teardown, `t.Parallel()` when tests
  share nothing
- Descriptive test names: `TestParseDuration`, subtests
  `"rejects negative values"`
- When the code uses goroutines, check for races with `go test -race ./...`.
  The race detector needs cgo and a C compiler at test time only, so it does
  not conflict with cgo-free builds.

## Performance Considerations

- Measure before optimizing: benchmarks (`func BenchmarkX(b *testing.B)`) and
  `pprof`
- Preallocate slices and maps when the size is known
- Stream large inputs (`io.Reader`, `bufio.Scanner`) instead of loading them
  whole
