"""Locate Claude Code session transcripts and reduce them to user + assistant text."""
import os, re, json, datetime as dt
from pathlib import Path

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def encode_cwd(path):
    return re.sub(r"[^A-Za-z0-9-]", "-", str(path))


def transcript_path(cwd, session_id, known=None):
    """`known` is the path a hook reported for this session; it wins when it still exists."""
    if known and Path(known).exists():
        return Path(known)
    name = f"{session_id}.jsonl"
    first = CLAUDE_PROJECTS / encode_cwd(cwd) / name
    if first.exists():
        return first
    # Claude files a session under the resolved folder, so a junction or symlink in
    # the recorded cwd misses. Try the resolved path, then look in every project folder.
    try:
        real = CLAUDE_PROJECTS / encode_cwd(os.path.realpath(cwd)) / name
        if real.exists():
            return real
        for hit in CLAUDE_PROJECTS.glob(f"*/{name}"):
            return hit
    except OSError:
        pass
    return first


def mtime(cwd, session_id, known=None):
    t = transcript_path(cwd, session_id, known)
    return dt.datetime.fromtimestamp(t.stat().st_mtime) if t.exists() else None


def _text(c):
    if isinstance(c, str):
        return c
    return " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")


def messages(path):
    """[(role, text)] for user + assistant text only; tool noise stripped."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"type":"user"' not in line and '"type":"assistant"' not in line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            role = j.get("type")
            if role not in ("user", "assistant"):
                continue
            txt = " ".join(_text(j.get("message", {}).get("content", "")).split())
            if not txt or txt.startswith("<") or txt.startswith("[Request interrupted"):
                continue
            out.append((role, txt))
    return out


def assistant_tail(path, max_chars=2500, max_msgs=6):
    tail = [m for r, m in messages(path) if r == "assistant"][-max_msgs:]
    return "\n".join("- " + m[:600] for m in tail)[-max_chars:]


def last_assistant(path, tail_bytes=300_000):
    """Last assistant text, reading only the tail of the transcript (cheap on huge sessions)."""
    path = Path(path)
    if not path.exists():
        return ""
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - tail_bytes))
        chunk = fh.read().decode("utf-8", errors="replace")
    last = ""
    for line in chunk.splitlines()[1:] if size > tail_bytes else chunk.splitlines():
        if '"type":"assistant"' not in line:
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("type") != "assistant":
            continue
        txt = _text(j.get("message", {}).get("content", "")).strip()
        if txt:
            last = txt
    return last
