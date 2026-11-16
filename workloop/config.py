"""Paths, user settings and the few things that differ per platform.

Code lives in the repo (ROOT). Everything personal lives in the data folder (DATA):
  ~/.workloop            or whatever WORKLOOP_HOME points at
    config.yaml          your name
    projects.yaml        the registry: projects and their seats
    projects/<slug>/     handoffs.md, digest.md, notes/ for each project
    architected/<slug>/  staged-pipeline projects (optional route)
    backups/             registry copies taken before `workloop reg` edits
    hooks.json           hook settings handed to every Claude session workloop starts
"""
import json, os, subprocess, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "workloop" / "prompts"
DATA = Path(os.environ.get("WORKLOOP_HOME") or Path.home() / ".workloop")
REG = DATA / "projects.yaml"
PROJECT_DATA = DATA / "projects"
ARCH = DATA / "architected"
BACKUPS = DATA / "backups"
CONFIG = DATA / "config.yaml"
HOOKS = DATA / "hooks.json"

STALE_DAYS = 5
BACKLOG_LIMIT = 5      # active architected projects
DRYRUN = bool(os.environ.get("WORKLOOP_DRYRUN"))   # print Claude commands instead of running them


def ensure_data():
    for d in (DATA, PROJECT_DATA, ARCH, BACKUPS):
        d.mkdir(parents=True, exist_ok=True)


def read(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return default


def write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def load_config():
    return yaml.safe_load(read(CONFIG)) or {}


def save_config(cfg):
    write(CONFIG, yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))


def user_name():
    """The person the agents report to. Asked once on first run, kept in config.yaml."""
    return load_config().get("name") or os.environ.get("USERNAME") or os.environ.get("USER") or "the user"


def posix(p):
    """Forward slashes: valid on Windows and safe inside bash command lines."""
    return str(p).replace("\\", "/")


def tool(sub):
    """Command line an agent can paste to call back into workloop (peek, reg)."""
    return f'"{posix(sys.executable)}" "{posix(ROOT / "bin" / "workloop")}" {sub}'


def hooks_file():
    """Hook settings passed to Claude with --settings, so nothing is written into the
    folders you work in. Rewritten every launch in case the repo or Python moved."""
    ensure_data()
    ev = {"type": "command", "command": tool("hook"), "timeout": 15}
    cfg = {"hooks": {k: [{"hooks": [ev]}] for k in ("Stop", "PreCompact", "SessionEnd")}}
    write(HOOKS, json.dumps(cfg, indent=2) + "\n")
    return str(HOOKS)


# ---------------------------------------------------------------- platform
def clip():
    """Clipboard text, or '' if it cannot be read."""
    if sys.platform == "win32":
        cmd = ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]
    elif sys.platform == "darwin":
        cmd = ["pbpaste"]
    else:
        cmd = ["xclip", "-selection", "clipboard", "-o"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
    except Exception:
        return ""


def open_path(path):
    """Open a file or folder with the system default (browser for .html, file manager for folders)."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.call(["open", str(path)])
        else:
            subprocess.call(["xdg-open", str(path)])
    except Exception:
        pass


def notify(title, msg):
    """Best-effort desktop notification from a hook. Silent if the platform has no easy route."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}" sound name "Glass"'], timeout=5)
        elif sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, msg], timeout=5)
    except Exception:
        pass
