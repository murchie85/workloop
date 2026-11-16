"""The registry: projects and their seats (DATA/projects.yaml), plus each project's
handoff log, digest and notes folder (DATA/projects/<slug>/).

A project is a name, a goal and optionally a home folder with extra folders attached.
A seat is one long-lived Claude session inside a project.

Hooks write the registry while the menu is open, so every change goes through
`mutate()`: it takes a lock, loads the file fresh, applies the change and saves."""
import contextlib, datetime as dt, os, re, shutil, time, uuid
from pathlib import Path
import yaml
from . import config as cf, transcripts as tr


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "project"


# ---------------------------------------------------------------- registry file
def load():
    reg = yaml.safe_load(cf.read(cf.REG)) or {}
    reg.setdefault("projects", [])
    return reg


def _save(reg):
    cf.ensure_data()
    tmp = cf.REG.with_suffix(".tmp")
    cf.write(tmp, yaml.safe_dump(reg, sort_keys=False, allow_unicode=True))
    os.replace(tmp, cf.REG)


@contextlib.contextmanager
def mutate(backup=False):
    """with mutate() as reg: change reg; it is saved on exit."""
    cf.ensure_data()
    lock = cf.DATA / "projects.lock"
    deadline = time.time() + 5
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # a lock older than 30s belongs to a process that died
            try:
                if time.time() - lock.stat().st_mtime > 30:
                    lock.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise RuntimeError(f"registry is locked ({lock}); delete the file if nothing else is running")
            time.sleep(0.05)
    try:
        if backup and cf.REG.exists():
            shutil.copy2(cf.REG, cf.BACKUPS / f"projects-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.yaml")
        reg = load()
        yield reg
        _save(reg)
    finally:
        os.close(fd)
        with contextlib.suppress(OSError):
            lock.unlink()


# ---------------------------------------------------------------- lookups
def find_project(reg, key):
    for p in reg["projects"]:
        if p["slug"] == key or p["name"] == key:
            return p
    return None


def find_seat(reg, session_id):
    for p in reg["projects"]:
        for seat in p.get("seats", []):
            if seat["id"] == session_id:
                return p, seat
    return None, None


def live_seats(p):
    return [s for s in p.get("seats", []) if not s.get("retired")]


def open_projects(reg):
    return [p for p in reg["projects"] if p.get("status", "active") != "closed"]


# ---------------------------------------------------------------- project folders
def pdir(p):
    d = cf.PROJECT_DATA / p["slug"]
    (d / "notes").mkdir(parents=True, exist_ok=True)
    return d


def home(p):
    """Where the project's seats start. Its own data folder when no home folder is set."""
    h = p.get("home")
    return Path(h) if h and Path(h).is_dir() else pdir(p)


def extra_dirs(p):
    """Folders attached to every seat on top of its working folder."""
    out = [d for d in p.get("dirs") or [] if Path(d).is_dir()]
    if p.get("home") and Path(p["home"]).is_dir():
        out.append(str(pdir(p)))      # so seats can read the digest and write notes
    return out


def is_git(path):
    p = Path(path)
    return any((q / ".git").exists() for q in [p, *p.parents])


# ---------------------------------------------------------------- create
def new_project(reg, name, goal="", home_dir="", dirs=None, read_first="", avoid=""):
    slug, n = slugify(name), 2
    base = slug
    while find_project(reg, slug):
        slug, n = f"{base}-{n}", n + 1
    p = {"name": name, "slug": slug, "goal": goal, "status": "active", "home": home_dir, "dirs": dirs or [],
         "read_first": read_first, "avoid": avoid, "created": now(), "seats": []}
    reg["projects"].append(p)
    pdir(p)
    return p


def new_seat(p, label=None, cwd=None):
    seat = {"id": str(uuid.uuid4()), "label": label or f"{p['name']} / seat {len(p.get('seats', [])) + 1}",
            "cwd": str(cwd or home(p)), "started": now(), "last_active": now(), "last_note": "",
            "limit": False, "retired": False}
    p.setdefault("seats", []).append(seat)
    return seat


def sibling_settings(reg, home_dir):
    """Read-first and do-not-touch text from another project on the same home folder."""
    for p in reversed(reg["projects"]):
        if home_dir and p.get("home") and os.path.normcase(p["home"]) == os.path.normcase(home_dir):
            if p.get("read_first") or p.get("avoid") or p.get("dirs"):
                return p
    return None


# ---------------------------------------------------------------- transcripts
def transcript(seat):
    return tr.transcript_path(seat.get("cwd", ""), seat["id"], seat.get("transcript"))


def seat_mtime(seat):
    return tr.mtime(seat.get("cwd", ""), seat["id"], seat.get("transcript"))


def project_last_active(p):
    ts = [t for t in (seat_mtime(s) for s in live_seats(p)) if t]
    return max(ts) if ts else None


# ---------------------------------------------------------------- handoffs and digest
def handoff_file(p):
    return pdir(p) / "handoffs.md"


def digest_file(p):
    return pdir(p) / "digest.md"


def append_handoff(p, seat_label, text):
    f = handoff_file(p)
    if not f.exists():
        cf.write(f, f"# {p['name']} — handoffs\n\n")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {now()} · {seat_label}\n{text.strip()}\n")


def recent_handoffs(p, n_lines=30):
    lines = cf.read(handoff_file(p)).splitlines()
    return "\n".join(lines[-n_lines:]) if lines else "(none yet)"


def digest(p):
    return cf.read(digest_file(p)).strip()
