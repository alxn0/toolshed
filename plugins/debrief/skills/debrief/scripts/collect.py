#!/usr/bin/env python3
"""Collect what was done on this machine in a period, for /debrief.

Usage: collect.py [session|repo|machine] [period] [--session <id>]
  session  the session given by --session (default period: its whole span)
  repo     the git repository of the current folder (default inside one)
  machine  every repository and session of this machine (default elsewhere)
  period   today (default), yesterday, week (the last 7 days), YYYY-MM-DD,
           or YYYY-MM-DD to YYYY-MM-DD (both days included)

Sources, read-only:
  - Claude Code transcripts (~/.claude/projects): the user's prompts, the
    final reply of each turn, recaps (away summaries) and session titles.
    Sessions without a typed prompt (`claude -p`, SDK runs) are left out.
  - git: the user's commits (their user.email) on all branches, plus the
    current `git status` of each repository. In the machine scope, the
    repositories are those the sessions of the period worked in.
  - GitHub: the user's events (`gh api users/<me>/events`), private ones
    included, which GitHub keeps for 90 days, 300 events at most.

Prints a compact text dump, one line per item, grouped by repository. A
GitHub failure is printed in its section instead of stopping the rest.
Exit codes: 0 done, 1 bad scope (no repository, unknown session), 64 usage.
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude/projects"
SCOPES = ("session", "repo", "machine")
# Excerpt caps: enough to tell what a turn was about, small enough for a week.
PROMPT_CHARS = 400
REPLY_CHARS = 400
BODY_CHARS = 300
STAT_CHARS = 80
COMMENT_CHARS = 200
STATUS_LINES = 40
# GitHub serves at most 3 pages of 100 events, from the last 90 days.
EVENT_PAGES = 3
EVENTS_PER_PAGE = 100
EVENT_RETENTION = timedelta(days=90)
PULL_EVENTS = {
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "PullRequestReviewCommentEvent",
}
COMMAND_TAG = re.compile(r"<command-(name|args)>(.*?)</command-\1>", re.DOTALL)
GITHUB_REMOTE = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$")
REF_PREFIX = re.compile(r"^refs/(heads|remotes|tags)/")


class UsageError(ValueError):
    """Bad command-line arguments (exit 64)."""


class ScopeError(ValueError):
    """The requested scope does not exist here (exit 1)."""


@dataclass(frozen=True)
class Window:
    """Half-open time range [start, end), timezone-aware."""

    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


@dataclass
class Session:
    """What one transcript holds inside the window."""

    id: str
    title: str = ""
    cwd: str = ""
    branch: str = ""
    # The user typed at least one prompt (in the whole transcript).
    is_interactive: bool = False
    start: datetime | None = None
    end: datetime | None = None
    # Chronological `you: …`, `claude: …` and `recap: …` lines.
    turns: list[str] = field(default_factory=list)

    def has_activity(self) -> bool:
        return self.start is not None

    def span(self) -> Window:
        assert self.start and self.end
        return Window(self.start, self.end + timedelta(seconds=1))


def run(args: list[str], cwd: Path | None = None) -> str:
    """Run a command and return its stdout; raise on failure."""
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def local_midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()).astimezone()


def parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"not a date (YYYY-MM-DD): {text}") from None


def parse_period(words: list[str], today: date) -> Window:
    """Turn the period words into a window of whole local days."""
    match words or ["today"]:
        case ["today"]:
            first = last = today
        case ["yesterday"]:
            first = last = today - timedelta(days=1)
        case ["week"]:
            first, last = today - timedelta(days=6), today
        case [day]:
            first = last = parse_day(day)
        case [start, "to", end]:
            first, last = parse_day(start), parse_day(end)
        case _:
            raise UsageError(f"unknown period: {' '.join(words)}")
    if last < first:
        raise UsageError(f"period ends before it starts: {' '.join(words)}")
    return Window(
        local_midnight(first), local_midnight(last + timedelta(days=1))
    )


def parse_timestamp(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone()


def format_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def clip(text: str, limit: int) -> str:
    """Text on one line, cut at limit characters."""
    text = re.sub(r"\s*\n\s*", " / ", text.strip())
    return text if len(text) <= limit else text[:limit].rstrip() + " […]"


def join_text_blocks(content: str | list) -> str:
    """The text of a message, whether a string or a list of blocks."""
    if isinstance(content, str):
        return content.strip()
    return "\n".join(
        block.get("text", "")
        for block in content
        if block.get("type") == "text"
    ).strip()


def prompt_text(content: str | list) -> str:
    """The typed prompt, with a slash command reduced to `/name args`."""
    text = join_text_blocks(content)
    tags = dict(COMMAND_TAG.findall(text))
    return f"{tags['name']} {tags.get('args', '')}" if "name" in tags else text


def is_typed_prompt(record: dict) -> bool:
    """A prompt the user wrote, not a tool result or harness message."""
    origin = record.get("origin") or {}
    return record.get("type") == "user" and origin.get("kind") == "human"


def read_records(path: Path) -> Iterable[dict]:
    with path.open() as transcript:
        for line in transcript:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # a line being written right now


def read_session(path: Path, window: Window | None) -> Session:
    """Read one transcript, keeping only what falls inside the window."""
    session = Session(id=path.stem)
    pending_reply = ""  # last text of the current turn, kept at its end

    def end_turn() -> None:
        nonlocal pending_reply
        if pending_reply:
            session.turns.append(f"claude: {clip(pending_reply, REPLY_CHARS)}")
        pending_reply = ""

    for record in read_records(path):
        kind = record.get("type")
        if kind == "ai-title":
            session.title = record.get("aiTitle", session.title)
            continue
        if "timestamp" not in record or record.get("isSidechain"):
            continue
        is_prompt = is_typed_prompt(record)
        session.is_interactive |= is_prompt
        moment = parse_timestamp(record["timestamp"])
        if window and not window.contains(moment):
            continue
        message = record.get("message") or {}
        if is_prompt:
            end_turn()
            text = prompt_text(message.get("content", ""))
            session.turns.append(f"you: {clip(text, PROMPT_CHARS)}")
        elif kind == "assistant":
            text = join_text_blocks(message.get("content", ""))
            pending_reply = text or pending_reply
        elif kind == "system" and record.get("subtype") == "away_summary":
            end_turn()
            recap = clip(record["content"], REPLY_CHARS)
            session.turns.append(f"recap: {recap}")
        else:
            continue
        session.cwd = record.get("cwd", session.cwd)
        session.branch = record.get("gitBranch", session.branch)
        session.start = min(session.start or moment, moment)
        session.end = max(session.end or moment, moment)
    end_turn()
    return session


def read_sessions(window: Window) -> list[Session]:
    """Every interactive transcript with activity in the window, by start."""
    sessions = [
        read_session(path, window)
        for path in PROJECTS_DIR.glob("*/*.jsonl")
        if path.stat().st_mtime >= window.start.timestamp()
    ]
    active = [
        session
        for session in sessions
        if session.is_interactive and session.has_activity()
    ]
    # The filter above leaves only sessions with a start.
    return sorted(active, key=lambda session: session.start or window.start)


def find_transcript(session_id: str) -> Path:
    matches = list(PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    if not matches:
        raise ScopeError(f"no transcript for session {session_id}")
    return matches[0]


@cache
def find_repo_root(folder: str) -> Path | None:
    """The main checkout of the repository holding folder (worktrees too)."""
    try:
        common = run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=Path(folder),
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None  # not a repository, or the folder is gone
    common_dir = Path(common)
    return common_dir.parent if common_dir.name == ".git" else common_dir


def group_by_repo(sessions: list[Session]) -> dict[Path | None, list[Session]]:
    """Sessions by the repository they worked in; None for other folders."""
    groups = defaultdict(list)
    for session in sessions:
        groups[find_repo_root(session.cwd)].append(session)
    return groups


def github_names(root: Path) -> set[str]:
    """owner/name, lowercased, of every GitHub remote of the repository."""
    urls = run(["git", "remote", "-v"], cwd=root).split()
    return {
        match[1].lower()
        for url in urls
        if (match := GITHUB_REMOTE.search(url))
    }


def read_commits(root: Path, email: str, window: Window) -> list[str]:
    """The user's commits on all branches (stash excluded), one line each."""
    log = run(
        [
            "git", "log", "--exclude=refs/stash", "--all", "--source",
            f"--author={email}", "--shortstat",
            f"--since={window.start.isoformat()}",
            f"--until={window.end.isoformat()}",
            "--format=%x1e%h%x1f%aI%x1f%S%x1f%s%x1f%b%x1f",
        ],
        cwd=root,
    )  # fmt: skip
    lines = []
    for entry in log.split("\x1e")[1:]:
        short_hash, moment, ref, subject, body, stat = entry.split("\x1f")
        when = format_time(parse_timestamp(moment))
        branch = REF_PREFIX.sub("", ref)
        stat = clip(stat, STAT_CHARS)
        lines.append(f"- {short_hash} {when} {branch}: {subject} ({stat})")
        if body.strip():
            lines.append(f"  {clip(body, BODY_CHARS)}")
    return lines


def render_session(session: Session) -> list[str]:
    assert session.start and session.end
    title = f' "{session.title}"' if session.title else ""
    span = f"{format_time(session.start)} → {format_time(session.end)}"
    return [
        (
            f"### Session {session.id}{title}, {span}, in {session.cwd}"
            f" on {session.branch or 'no branch'}"
        ),
        *(f"- {turn}" for turn in session.turns),
    ]


def render_repo(
    root: Path, names: set[str], window: Window, sessions: list[Session]
) -> list[str]:
    email = run(["git", "config", "user.email"], cwd=root).strip()
    status = run(["git", "status", "--short", "--branch"], cwd=root)
    lines = [
        (
            f"## {root} (GitHub: {', '.join(sorted(names)) or 'none'};"
            f" author {email})"
        ),
        "### Commits",
        *(read_commits(root, email, window) or ["- none"]),
        "### Status now",
        *(f"- {line}" for line in status.splitlines()[:STATUS_LINES]),
    ]
    for session in sessions:
        lines += render_session(session)
    return lines


def describe_event(event: dict) -> str:
    """One line: when, where, what; the rest of the payload is dropped."""
    payload = event["payload"]
    pull = payload.get("pull_request") or {}
    issue = payload.get("issue") or {}
    number = pull.get("number") or issue.get("number")
    title = pull.get("title") or issue.get("title")
    comment = (payload.get("comment") or {}).get("body", "")
    parts = [
        format_time(parse_timestamp(event["created_at"])),
        event["repo"]["name"],
        event["type"].removesuffix("Event"),
        payload.get("action"),
        payload.get("ref_type"),
        REF_PREFIX.sub("", payload.get("ref") or ""),
        f"#{number}" if number else None,
        "(pull request)" if "pull_request" in issue else None,
        f'"{title}"' if title else None,
        (payload.get("review") or {}).get("state"),
        f"comment: {clip(comment, COMMENT_CHARS)}" if comment else None,
    ]
    return " ".join(part for part in parts if part)


def fetch_events(login: str, start: datetime) -> list[dict]:
    """The user's events, newest first, back to start or GitHub's limit."""
    events = []
    for page in range(1, EVENT_PAGES + 1):
        url = f"users/{login}/events?per_page={EVENTS_PER_PAGE}&page={page}"
        batch = json.loads(run(["gh", "api", url]))
        events += batch
        if not batch or parse_timestamp(batch[-1]["created_at"]) < start:
            break
    return events


def fetch_pull_title(repo: str, number: int) -> str | None:
    try:
        url = f"repos/{repo}/pulls/{number}"
        return run(["gh", "api", url, "--jq", ".title"]).strip() or None
    except subprocess.CalledProcessError:
        return None  # deleted repository or lost access: keep the event


def add_pull_titles(events: list[dict]) -> None:
    """Fill in the pull request titles the events feed leaves out."""
    untitled = [
        (event["repo"]["name"], pull)
        for event in events
        if event["type"] in PULL_EVENTS
        and (pull := event["payload"].get("pull_request"))
        and "title" not in pull
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        titles = pool.map(
            lambda item: fetch_pull_title(item[0], item[1]["number"]), untitled
        )
        for (_, pull), title in zip(untitled, titles, strict=True):
            pull["title"] = title


def render_github(window: Window, names: set[str] | None) -> list[str]:
    """The user's GitHub events in the window; names limits the repos."""
    try:
        login = run(["gh", "config", "get", "-h", "github.com", "user"])
        login = login.strip()
        if not login:
            return ["## GitHub", "- not read: gh is not logged in"]
        events = fetch_events(login, window.start)
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        return ["## GitHub", f"- not read: {detail.strip()}"]
    kept = [
        event
        for event in events
        if window.contains(parse_timestamp(event["created_at"]))
        and (names is None or event["repo"]["name"].lower() in names)
    ]
    add_pull_titles(kept)
    reached_cap = len(events) >= EVENTS_PER_PAGE * EVENT_PAGES and (
        window.contains(parse_timestamp(events[-1]["created_at"]))
    )
    too_old = window.start < datetime.now().astimezone() - EVENT_RETENTION
    note = (
        ", incomplete: older events are gone" if reached_cap or too_old else ""
    )
    lines = [f"- {describe_event(event)}" for event in kept]
    return [f"## GitHub, as {login}{note}", *(lines or ["- none"])]


def parse_args(argv: list[str]) -> tuple[str | None, list[str], str | None]:
    """Split argv into (scope, period words, session id)."""
    words, session_id = list(argv), None
    if "--session" in words:
        index = words.index("--session")
        if index + 1 >= len(words):
            raise UsageError("--session needs an id")
        session_id = words[index + 1]
        del words[index : index + 2]
    scope = words.pop(0) if words and words[0] in SCOPES else None
    return scope, words, session_id


def select(
    argv: list[str],
) -> tuple[str, Window, dict[Path | None, list[Session]]]:
    """The scope, its window, and its sessions grouped by repository."""
    scope, period_words, session_id = parse_args(argv)
    today = date.today()
    current_root = find_repo_root(str(Path.cwd()))
    scope = scope or ("repo" if current_root else "machine")
    if scope == "session":
        if not session_id:
            raise UsageError("session scope needs --session <id>")
        transcript = find_transcript(session_id)
        session = read_session(transcript, None)
        if not session.has_activity():
            raise ScopeError(f"session {session_id} has no activity")
        window = session.span()
        if period_words:
            window = parse_period(period_words, today)
            session = read_session(transcript, window)
        sessions = [session] if session.has_activity() else []
        return scope, window, {find_repo_root(session.cwd): sessions}
    window = parse_period(period_words, today)
    groups = group_by_repo(read_sessions(window))
    if scope == "repo":
        if not current_root:
            raise ScopeError(f"not in a git repository: {Path.cwd()}")
        return scope, window, {current_root: groups.get(current_root, [])}
    if current_root:
        groups.setdefault(current_root, [])
    return scope, window, groups


def collect(argv: list[str]) -> str:
    scope, window, groups = select(argv)
    lines = [
        (
            f"# Debrief data, {scope} scope, "
            f"{format_time(window.start)} → {format_time(window.end)}"
        )
    ]
    names = set()
    for root in sorted(root for root in groups if root):
        root_names = github_names(root)
        names |= root_names
        lines += render_repo(root, root_names, window, groups[root])
    if groups.get(None):
        lines.append("## Sessions outside repositories")
        for session in groups[None]:
            lines += render_session(session)
    lines += render_github(window, None if scope == "machine" else names)
    return "\n".join(lines)


def main() -> None:
    try:
        print(collect(sys.argv[1:]))
    except UsageError as error:
        print(f"collect.py: {error}", file=sys.stderr)
        sys.exit(64)
    except ScopeError as error:
        print(f"collect.py: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
