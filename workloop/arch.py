"""Architected projects: the optional staged route.
  full: ideation → eval → formalisation → tooling → build → feature_complete → shipped
  fast: fast_plan → build → feature_complete → shipped
Each stage from eval onward is a tracked Claude session inside DATA/architected/<slug>/,
which writes a stage file whose YAML frontmatter is read back into loop.yaml."""
import datetime as dt, re, shutil, uuid
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from . import config as cf, seats, transcripts as tr

con = Console()

STAGES = ["ideation", "eval", "formalisation", "tooling", "build", "feature_complete", "shipped"]
FAST_STAGES = ["fast_plan", "build", "feature_complete", "shipped"]
# Stages that run as a Claude session, with the file Claude must produce.
CLAUDE_STAGES = {"fast_plan": "plan.md", "eval": "eval.md", "formalisation": "formalisation.md",
                 "tooling": "tooling.md", "build": "build.md", "feature_complete": "feature_complete.md"}
STAGE_COLOUR = {"fast_plan": "bright_yellow", "ideation": "white", "eval": "yellow", "formalisation": "yellow",
                "tooling": "cyan", "build": "cyan", "feature_complete": "magenta", "shipped": "green"}


def decide(scores):
    """Eval pass rule: value + niche + distribution >= 10 and complexity <= 4 → go; 7-9 → park; else kill."""
    total = sum(int(scores.get(k) or 0) for k in ("value", "niche", "distribution"))
    if total >= 10 and int(scores.get("complexity") or 5) <= 4:
        return "go"
    return "park" if total >= 7 else "kill"


def today():
    return dt.date.today().isoformat()


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


class Project:
    def __init__(self, path):
        self.path = path
        self.file = path / "loop.yaml"
        self.data = yaml.safe_load(cf.read(self.file)) or {}

    @classmethod
    def create(cls, name, idea, mode="full"):
        slug = slugify(name)
        path = cf.ARCH / slug
        if path.exists():
            raise FileExistsError(slug)
        path.mkdir(parents=True)
        cf.write(path / "idea.md", f"# {name}\n\n{idea.strip()}\n")
        p = cls(path)
        p.data = {"loopfile": 1, "name": name, "slug": slug, "created": today(), "mode": mode, "track": None,
                  "stage": "fast_plan" if mode == "fast" else "ideation", "status": "active",
                  "sessions": {}, "scores": {}, "log": []}
        p.log(p.data["stage"], "steer captured" if mode == "fast" else "idea captured")
        p.save()
        return p

    @classmethod
    def all(cls):
        if not cf.ARCH.exists():
            return []
        ps = [cls(d) for d in sorted(cf.ARCH.iterdir()) if (d / "loop.yaml").exists()]
        return sorted(ps, key=lambda p: p.touched, reverse=True)

    @classmethod
    def active(cls):
        """Counts toward the limit: active, and not a fast run still at the plan checkpoint."""
        return [p for p in cls.all() if p.status == "active" and not (p.is_fast and p.stage == "fast_plan")]

    def save(self):
        cf.write(self.file, yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True))

    def log(self, stage, note):
        self.data.setdefault("log", []).append({"date": today(), "stage": stage, "note": note})

    name = property(lambda s: s.data.get("name", s.path.name))
    slug = property(lambda s: s.data.get("slug", s.path.name))
    stage = property(lambda s: s.data.get("stage", "ideation"))
    status = property(lambda s: s.data.get("status", "active"))
    track = property(lambda s: s.data.get("track") or "-")
    mode = property(lambda s: s.data.get("mode") or "full")
    is_fast = property(lambda s: s.mode == "fast")
    stages = property(lambda s: FAST_STAGES if s.is_fast else STAGES)
    scores = property(lambda s: s.data.get("scores") or {})
    digest = property(lambda s: cf.read(s.path / "DIGEST.md").strip())

    @property
    def touched(self):
        log = self.data.get("log") or []
        return log[-1]["date"] if log else self.data.get("created", "1970-01-01")

    @property
    def days_idle(self):
        return (dt.date.today() - dt.date.fromisoformat(self.touched)).days

    @property
    def next_stage(self):
        st = self.stages
        if self.stage not in st:
            return None
        i = st.index(self.stage)
        return st[i + 1] if i + 1 < len(st) else None

    def session_for(self, stage):
        return (self.data.get("sessions") or {}).get(stage)

    def session_meta(self, stage):
        return (self.data.get("session_meta") or {}).get(stage) or {}

    def set_session_meta(self, stage, **kw):
        self.data.setdefault("session_meta", {}).setdefault(stage, {}).update(kw)

    def transcript(self, stage):
        sid = self.session_for(stage)
        return tr.transcript_path(self.path, sid, self.session_meta(stage).get("transcript")) if sid else None

    def new_session(self, stage):
        sid = str(uuid.uuid4())
        self.data.setdefault("sessions", {})[stage] = sid
        self.save()
        return sid

    def set_stage(self, stage, note=None):
        self.data["stage"] = stage
        self.log(stage, note or f"entered {stage}")
        self.save()

    def set_status(self, status, note=None):
        self.data["status"] = status
        self.log(self.stage, note or status)
        self.save()

    def trash(self):
        """Move the folder to architected/.trash/<slug>-<timestamp>. Recoverable."""
        t = cf.ARCH / ".trash"
        t.mkdir(exist_ok=True)
        dest = t / f"{self.slug}-{dt.datetime.now():%Y%m%d-%H%M%S}"
        shutil.move(str(self.path), str(dest))
        return dest

    def ingest(self, stage):
        """Pull the frontmatter of the stage file into loop.yaml. None if the file is missing."""
        fname = CLAUDE_STAGES.get(stage)
        f = self.path / fname if fname else None
        if not f or not f.exists():
            return None
        m = re.match(r"^---\r?\n(.*?)\r?\n---", cf.read(f), re.S)
        try:
            meta = (yaml.safe_load(m.group(1)) if m else {}) or {}
        except yaml.YAMLError:
            meta = {}
        self.data = yaml.safe_load(cf.read(self.file)) or self.data     # the hook may have written since
        if stage in ("eval", "fast_plan"):
            scores = {k: meta.get(k) for k in ("complexity", "value", "niche", "reuse", "distribution") if k in meta}
            if scores:
                scores["decision"] = meta.get("decision") or decide(scores)
                self.data["scores"] = scores
            if meta.get("track") in ("knowledge", "product"):
                self.data["track"] = meta["track"]
            if meta.get("summary"):
                self.data["summary"] = meta["summary"]
        self.log(stage, f"{fname} ingested")
        self.save()
        return meta


# ---------------------------------------------------------------- hook (called from tools.hook)
def hook(sid, event, note):
    for p in Project.all():
        stage = next((st for st, s in (p.data.get("sessions") or {}).items() if s == sid), None)
        if not stage:
            continue
        p.set_session_meta(stage, last_active=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
        if note:
            p.set_session_meta(stage, last_note=note)
        if event == "PreCompact":
            p.set_session_meta(stage, limit=True)
            p.log(stage, "context limit hit; handover available (h)")
            cf.notify("workloop", f"{p.name} · {stage} session at context limit.")
        p.save()
        return


# ---------------------------------------------------------------- sessions
def stage_prompt(stage):
    me = cf.user_name()
    common = cf.read(cf.PROMPTS / "_common.md").replace("{STAGE}", stage.upper().replace("_", " "))
    return (common + "\n" + cf.read(cf.PROMPTS / f"{stage}.md")).replace("{NAME}", me)


def run_stage(p, stage, resume=False, extra=None, takeover=False):
    sid = p.session_for(stage)
    base = ["claude", "--settings", cf.hooks_file()]
    if resume and sid:
        cmd = base + ["--resume", sid] + ([extra] if extra else [])
    else:
        old_tail = tr.assistant_tail(p.transcript(stage)) if takeover and sid else ""
        sid = p.new_session(stage)
        sp = stage_prompt(stage)
        if p.digest:
            sp += "\n\nPROJECT DIGEST (from the helper; read before anything else):\n" + p.digest
        if old_tail:
            sp += "\n\nCONTEXT HANDOVER: the previous session for this stage hit its context limit. Its last messages:\n" + old_tail + "\nConfirm the current state in two lines, then continue the stage."
        first = ("FAST MODE. Read idea.md (the steer) and produce plan.md + plan.html. Keep every message to one line."
                 if stage == "fast_plan" else f"Run the {stage.upper()} stage for this project. Start by reading idea.md.")
        cmd = base + ["--session-id", sid, "-n", f"{p.name} · {stage}", "--append-system-prompt", sp, first]
    seats.call(cmd, p.path)


def helper_brief(p):
    me = cf.user_name()
    sessions = "\n".join(f"- {st}: {sid[:8]}… last: {(p.session_meta(st).get('last_note') or '-')[:100]}" for st, sid in (p.data.get("sessions") or {}).items()) or "- none yet"
    files = ", ".join(f.name for f in sorted(p.path.iterdir()) if f.suffix in (".md", ".html", ".yaml") and f.name != "DIGEST.md")
    paths = "\n".join(f"- {st}: {p.transcript(st)}" for st in (p.data.get("sessions") or {})) or "- none yet"
    return f"""You are the HELPER for architected project "{p.name}" (folder: {p.path}, stage: {p.stage}, mode: {p.mode}).
You are detached: not tracked, you do not build the product. You read, summarise, cross-reference, and keep the project's own records straight.

Files here: {files}
Stage sessions:
{sessions}
Their transcripts (JSONL; read the user and assistant text, skip tool noise):
{paths}
Also: git log in this folder if it is a repo.

What you may change, yourself, when {me} asks (do not hand back a to-do):
- {p.path / 'DIGEST.md'} (you own it): 10-25 lines: State now · Done (with hashes if any) · In flight · Next · Gotchas. Every later stage session reads it at start, so write it for a fresh agent.
- idea.md and the stage output files (eval.md, formalisation.md, plan.md ...): merge, split, tidy, bring in material {me} points you at.
- loop.yaml: stage / status / track / scores / log entries, keeping the existing keys and YAML shape. Never touch the `sessions` map.
Do not edit product code or files outside this folder.

Jobs: "what have we done so far" (bullets, newest first) · "refresh notes" (rewrite DIGEST.md) · "what's blocked" · "tidy this up" (do it, then say in two lines what changed).
Rules: most compressed format possible, {me} asks for more. Never speculate beyond what the transcripts, files and git show.
"""


# ---------------------------------------------------------------- display
def stage_label(p):
    if p.status != "active":
        return f"[dim]{p.status}[/]"
    return f"[{STAGE_COLOUR.get(p.stage, 'white')}]{p.stage}[/]" + ("[dim] ⚡[/]" if p.is_fast else "")


def score_label(p):
    sc = p.scores
    if not sc:
        return "[dim]-[/]"
    d = sc.get("decision", "")
    col = {"go": "green", "park": "yellow", "kill": "red"}.get(d, "white")
    return f"V{sc.get('value', '?')} N{sc.get('niche', '?')} D{sc.get('distribution', '?')} C{sc.get('complexity', '?')} [{col}]{d}[/]"


def table(projects, title):
    t = Table(title=f"{title}  [dim]({len(Project.active())}/{cf.BACKLOG_LIMIT} active)[/]", expand=False)
    for col in ("#", "project", "track", "stage", "eval", "idle"):
        t.add_column(col, justify="right" if col in ("#", "idle") else "left", style="bold" if col == "project" else None)
    for i, p in enumerate(projects, 1):
        idle = p.days_idle
        t.add_row(str(i), p.name, p.track, stage_label(p), score_label(p), f"[red]{idle}d[/]" if idle >= 7 else f"{idle}d")
    con.print(t)


def ask_text(label):
    """One-line prompt; '@clip' reads the clipboard instead (long pastes can jam the terminal)."""
    v = Prompt.ask(f"{label} [dim](or @clip)[/]")
    if v.strip() == "@clip":
        v = cf.clip()
        con.print(f"[dim]from clipboard: {v[:100]}{'…' if len(v) > 100 else ''}[/]")
    return v


def open_plan(p):
    plan = p.path / "plan.html"
    if plan.exists():
        cf.open_path(plan)
        return True
    con.print("[yellow]No plan.html yet.[/]")
    return False


# ---------------------------------------------------------------- flow
def run(p, stage, resume=False, extra=None, takeover=False):
    if stage not in CLAUDE_STAGES:
        return
    if not seats.available():
        con.print("[red]claude CLI not found on PATH.[/]")
        return
    con.print(f"[dim]launching claude · stage={stage} · {'resume' if resume else ('handover' if takeover else 'new session')}[/]")
    run_stage(p, stage, resume=resume, extra=extra, takeover=takeover)
    p.data = yaml.safe_load(cf.read(p.file)) or p.data
    if takeover:
        p.set_session_meta(stage, limit=False)
        p.save()
    if stage == "fast_plan":
        return      # fast_checkpoint() ingests and decides
    meta = p.ingest(stage)
    if stage == "formalisation" and open_plan(p):
        con.print("[dim]visual plan opened in your browser · approve here, or continue the session with changes[/]")
    if meta is None:
        con.print(f"[yellow]No {CLAUDE_STAGES[stage]} written yet. Resume the session to finish the stage.[/]")
        return
    if stage == "eval":
        d = p.scores.get("decision")
        con.print(f"[bold]Eval decision:[/] {score_label(p)}  track={p.track}")
        if d == "park":
            p.set_status("parked", "parked by eval")
        elif d == "kill":
            p.set_status("killed", "killed by eval")
    elif stage == "feature_complete":
        con.print("[green]feature-complete checklist verified[/]" if meta.get("complete") else "[yellow]checklist not complete yet[/]")


def pipeline(p):
    """Walk the stages one after another. Each gate is one keypress."""
    while True:
        p = Project(p.path)
        if p.status != "active":
            con.print(f"[dim]{p.name} is {p.status}. Pipeline stops here.[/]")
            return
        nxt = p.next_stage
        if not nxt:
            con.print("[green]Shipped.[/]")
            return
        con.print(f"\n[bold]{p.name}[/]  stage [bold]{p.stage}[/]  eval {score_label(p)}  track={p.track}")
        if nxt == "formalisation" and p.scores.get("decision") not in ("go", None):
            con.print(f"[yellow]Eval said '{p.scores.get('decision')}'.[/]")
        gate = {"eval": "score it", "formalisation": "map it (visual plan)", "tooling": "acquire tools (~10 min)", "build": "build it (long)",
                "feature_complete": "verify the feature-complete bar", "shipped": "mark shipped"}.get(nxt, nxt)
        c = Prompt.ask(f"→ [bold]{nxt}[/] · {gate}   [dim]Enter=go · p=park · k=kill · m=menu[/]", default="", show_default=False).strip().lower()
        if c == "p":
            p.set_status("parked"); con.print("[yellow]parked[/]"); return
        if c == "k":
            if Confirm.ask("Kill?", default=False):
                p.set_status("killed"); con.print("[red]killed[/]"); return
            continue
        if c == "m":
            return
        if nxt == "shipped":
            p.set_stage("shipped", "shipped"); p.set_status("shipped"); con.print("[green]shipped[/]"); return
        p.set_stage(nxt)
        run(p, nxt)
        if not (p.path / CLAUDE_STAGES[nxt]).exists():
            return      # stage not finished; come back through the project screen


def fast_checkpoint(p):
    """Visual go / no-go loop after a fast_plan session."""
    while True:
        meta = p.ingest("fast_plan")
        if meta is None:
            con.print("[yellow]No plan.md written. (r)esume the session, (k)ill, or (b)ack.[/]")
            c = Prompt.ask("›", choices=["r", "k", "b"], show_choices=False)
            if c == "r":
                run(p, "fast_plan", resume=True); continue
            if c == "k":
                p.set_status("killed", "fast run abandoned")
            return
        open_plan(p)
        con.print(f"[bold]{p.name}[/]  {score_label(p)}  track={p.track}")
        if p.data.get("summary"):
            con.print(f"[dim]{p.data['summary']}[/]")
        con.print("  [bold]g[/] go → build   [bold]i[/] iterate (one-line steer)   [bold]o[/] open plan again   [bold]p[/] park   [bold]n[/] no-go")
        c = Prompt.ask("›", choices=["g", "i", "o", "p", "n"], show_choices=False)
        if c == "g":
            if len(Project.active()) >= cf.BACKLOG_LIMIT:
                con.print(f"[red]{cf.BACKLOG_LIMIT} architected projects already active. Park or kill one first.[/]"); continue
            p.set_stage("build", "go from fast checkpoint")
            run(p, "build"); pipeline(p); return
        if c == "i":
            steer = ask_text("steer").strip()
            if steer:
                with (p.path / "idea.md").open("a", encoding="utf-8") as fh:
                    fh.write(f"\n\n## Steer {today()}\n{steer}\n")
                p.log("fast_plan", f"steer: {steer[:80]}"); p.save()
                run(p, "fast_plan", resume=True, extra=f"New steer: {steer}. Revise plan.md and plan.html.")
        elif c == "o":
            open_plan(p)
        elif c == "p":
            p.set_status("parked", "parked at fast checkpoint"); return
        elif c == "n":
            p.set_status("killed", "no-go at fast checkpoint"); return


def new_project(fast=False):
    if not fast and len(Project.active()) >= cf.BACKLOG_LIMIT:
        con.print(f"[red]{cf.BACKLOG_LIMIT} architected projects already active. Park, kill or ship one first.[/]")
        return
    name = Prompt.ask("name").strip()
    if not name:
        return
    if fast:
        idea = ask_text("steer").strip()
    else:
        how = Prompt.ask("idea via  [bold]t[/] type one line · [bold]c[/] clipboard", choices=["t", "c"], default="c", show_choices=False)
        idea = cf.clip() if how == "c" else ask_text("idea").strip()
        if how == "c":
            con.print(f"[dim]from clipboard: {idea[:100]}{'…' if len(idea) > 100 else ''}[/]")
    if not idea:
        con.print("[red]Nothing captured.[/]")
        return
    try:
        p = Project.create(name, idea, mode="fast" if fast else "full")
    except FileExistsError as e:
        con.print(f"[red]An architected project '{e}' already exists.[/]")
        return
    con.print(f"[green]Saved[/] → {p.path}")
    if fast:
        run(p, "fast_plan"); fast_checkpoint(p)
    else:
        pipeline(p)


def open_project(p):
    while True:
        p = Project(p.path)
        cur = p.stage
        meta_lines = "".join(f"{st:<16} {'[red]LIMIT[/] ' if m.get('limit') else ''}[dim]{(m.get('last_note') or '')[:80]}[/]\n" for st, m in (p.data.get("session_meta") or {}).items())
        con.print()
        con.print(Panel(f"[bold]{p.name}[/]  [dim]{p.slug}[/]\nstage {stage_label(p)}   status [bold]{p.status}[/]   track {p.track}\n"
                        f"eval {score_label(p)}   idle {p.days_idle}d\n{meta_lines}"
                        + ("[green]digest[/] present (d to read)\n" if p.digest else "[dim]digest: none · ? helper → 'refresh notes'[/]\n")
                        + f"[dim]{p.path}[/]", title="architected project", expand=False))
        opts = []
        if p.is_fast and cur == "fast_plan" and p.status == "active":
            opts.append(("v", "visual checkpoint (go / iterate / no-go)"))
        if cur in CLAUDE_STAGES and p.session_for(cur):
            opts.append(("c", f"continue {cur} session"))
        if p.status == "active" and p.next_stage and not (p.is_fast and cur == "fast_plan"):
            opts.append(("n", f"continue pipeline → {p.next_stage}"))
        if cur in CLAUDE_STAGES:
            opts.append(("r", f"re-run {cur} (new session)"))
            if p.session_for(cur):
                opts.append(("h", f"context handover for {cur}"))
        opts += [("?", "helper (detached)"), ("i", "show idea"), ("l", "show log")]
        if p.digest:
            opts.append(("d", "show digest"))
        opts.append(("f", "open folder"))
        opts += [("p", "park"), ("k", "kill")] if p.status == "active" else [("a", "reactivate")]
        opts += [("D", "delete (moves the folder to .trash)"), ("b", "back")]
        for k, label in opts:
            con.print(f"  [bold]{k}[/]  {label}")
        c = Prompt.ask("›", choices=[k for k, _ in opts], show_choices=False)
        if c == "v":
            fast_checkpoint(p)
        elif c == "c":
            run(p, cur, resume=True)
        elif c == "n":
            pipeline(p)
        elif c == "r":
            run(p, cur)
        elif c == "h":
            run(p, cur, takeover=True)
        elif c == "?":
            seats.call(["claude", "--append-system-prompt", helper_brief(p), f"Helper for {p.name}. Say in one line what you can do, then wait."], p.path)
        elif c == "d":
            con.print(Panel(p.digest, title="DIGEST.md"))
        elif c == "i":
            con.print(Panel(cf.read(p.path / "idea.md"), title="idea.md"))
        elif c == "l":
            for e in p.data.get("log", []):
                con.print(f"  [dim]{e['date']}[/]  {e['stage']:<16} {e['note']}")
        elif c == "f":
            cf.open_path(p.path)
        elif c == "p":
            p.set_status("parked"); con.print("[yellow]parked[/]")
        elif c == "k":
            if Confirm.ask("Kill (kept on disk, marked killed)?", default=False):
                p.set_status("killed"); con.print("[red]killed[/]")
        elif c == "a":
            if len(Project.active()) >= cf.BACKLOG_LIMIT:
                con.print(f"[red]{cf.BACKLOG_LIMIT} already active.[/]")
            else:
                p.set_status("active", "reactivated")
        elif c == "D":
            if Confirm.ask(f"Delete '{p.name}'? The folder moves to .trash, recoverable.", default=False):
                con.print(f"[red]deleted[/] → {p.trash()}"); return
        elif c == "b":
            return


def menu():
    show_all = False
    while True:
        ps = Project.all() if show_all else [p for p in Project.all() if p.status in ("active", "parked")]
        con.print()
        con.print("[bold]Architected projects[/]  [dim]idea → eval → plan → build → ship, one agent per stage[/]")
        if ps:
            table(ps, "all" if show_all else "active + parked")
        else:
            con.print("  [dim]none yet[/]")
        con.print("  [bold]1-9[/] open   [bold]n[/] new (full: eval first)   [bold]f[/] ⚡ fast (steer → visual plan → go/no-go)   [bold]a[/] show all / fewer   [bold]b[/] back")
        c = Prompt.ask("›", default="b", show_default=False).strip().lower()
        if c.isdigit() and 1 <= int(c) <= len(ps):
            open_project(ps[int(c) - 1])
        elif c == "n":
            new_project()
        elif c == "f":
            new_project(fast=True)
        elif c == "a":
            show_all = not show_all
        elif c == "b":
            return
