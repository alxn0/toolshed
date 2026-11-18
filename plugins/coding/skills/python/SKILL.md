---
description: Python conventions - tooling (uv, ruff, ty, pytest), flat project layout, type hints, preferred libraries (polars), functional style, testing. Auto-loads when working with .py files.
paths: "**/*.py"
---

# Python

## Version and style

- Target the latest Python, minimum 3.10, so `X | None`, `match` and built-in
  generics are always available.
- Line length 80, set in `pyproject.toml` under `[tool.ruff]` so ruff enforces
  it. Short lines keep side-by-side diffs readable.

## Type hints

- Annotate function signatures, including third-party types (`pl.DataFrame`,
  `requests.Response`). The signature documents the function, and `ty` can only
  check what is annotated.
- Use built-in generics and unions: `list[str]`, `dict[str, int]`, `X | None`.
  Take abstract types from `collections.abc` as parameters (`Iterable`,
  `Mapping`, `Callable`) and return concrete ones.
- Leave local variables unannotated unless the type is unclear. Skip elaborate
  typing (`TypeVar` chains, `Protocol` hierarchies, overloads) unless a caller
  needs it: it costs more to read than it catches.

## Tooling

uv manages projects and dependencies. Use pixi instead when the project needs
conda-ecosystem packages (PyTorch, TensorFlow, C++ libraries).

New project with the flat layout below (uv defaults to `src/`):

```bash
uv init --package --name <package_name> --vcs none .
mv src/<package_name> . && rmdir src
printf '\n[tool.uv.build-backend]\nmodule-root = ""\n' >> pyproject.toml
uv add --dev pytest ruff ty
```

Day to day:

- Add a dependency: `uv add <package>`
- Format and lint: `uv run ruff format .` and `uv run ruff check .`
- Type check: `uv run ty check`
- Test: `uv run pytest`

Environment variables come from direnv, so read them with `os.environ`. Don't
load `.env` files from code.

## Libraries

- DataFrames: `polars`; `pandas` only when a dependency requires it. For a
  handful of rows the stdlib `csv` module is enough.
- Scientific computing: `scipy`, `numpy`; machine learning: `scikit-learn`.
- Data apps and dashboards: `streamlit`.
- Tests: `pytest`.
- Structured config and data records: `dataclasses`.

## Project layout

```
project/
├── package_name/      # source, flat
├── tests/             # test_<module>.py per module
├── tmp/               # scratch files, git-ignored
└── pyproject.toml
```

Keep modules directly in `package_name/`. Add subpackages only when asked or
when the package grows past what one folder can hold readably, and split by
feature, not by technical layer (`billing/`, not `models/`).

## Style

- Prefer pure functions and immutable data over classes. They are easier to
  test and to reason about.
- Use comprehensions for transformations and filtering, and generators for
  large or lazy sequences. Comprehensions read better in Python than `map`,
  `filter` and `reduce`.
- Use a class when it clearly earns its place: a `dataclass` (often
  `frozen=True`) for records, a client that holds a session or connection, or
  state with behaviour attached. Favour composition over inheritance.
- Cache expensive pure computations with `functools.cache`, and expensive
  attributes with `functools.cached_property`.

## Data processing

- Use polars method chaining, one operation per line.
- Pass an explicit schema when reading files, so bad input fails at the
  boundary.
- Use lazy reading (`scan_csv`, `scan_parquet`) on large files so polars can
  optimize the query and avoid loading everything.

## Errors

- Validate input at the boundary and fail with a message that names the bad
  value.
- Raise the most specific built-in exception. Define your own (subclass of a
  built-in such as `ValueError`) only when callers need to tell the error
  apart.
- Use context managers (`with`) for files, sessions and locks.

## Testing

- One test file per module: `tests/test_<module>.py`.
- Use fixtures for shared setup and `pytest.mark.parametrize` for input
  variations.
- Name tests after the behaviour: `test_monthly_revenue_rejects_negative_units`.
