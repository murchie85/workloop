"""Briefs and launches: seats (tracked, do the work) and the helper (detached, keeps the records)."""
import datetime as dt, shutil, subprocess
from pathlib import Path
from . import config as cf, store, transcripts as tr


def available():
    return cf.DRYRUN or shutil.which("claude") is not None


def call(cmd, cwd):
    if cf.DRYRUN:
        print("DRYRUN cwd=" + str(cwd))
        for part in cmd:
            print("  | " + part.replace("\n", "\n  |   "))
        return 0
    return subprocess.call(cmd, cwd=str(cwd))


def _add_dirs(dirs):
    """--add-dir takes several values, so it must be followed by another flag, never the prompt."""
    dirs = [str(d) for d in dirs if d]
    return ["--add-dir", *dirs] if dirs else []


# ---------------------------------------------------------------- seat brief
def brief(p, seat, takeover=None):
    me = cf.user_name()
    others = [s for s in store.live_seats(p) if s["id"] != seat["id"]]
    others_txt = "\n".join(f"- {s['label']}: {s.get('last_note') or '(no note yet)'}" for s in others) or "- none"
    cwd = seat.get("cwd") or str(store.home(p))
    folders = [f"- {cwd}  (you start here)"]
    folders += [f"- {d}" for d in p.get("dirs") or [] if d != cwd]
    notes = store.pdir(p) / "notes"
    peek = cf.tool("peek")
    txt = f"""You are seat "{seat['label']}" on project "{p['name']}".
Project goal: {p.get('goal') or '(not set)'}

Folders:
{chr(10).join(folders)}
"""
    if p.get("read_first"):
        txt += f"\nRead first: {p['read_first']}\n"
    if p.get("avoid"):
        txt += f"Do NOT read or modify: {p['avoid']}\n"
    txt += f"""
This seat is freeflow. It may stay a conversation (investigation, planning, writing) or turn into building something. Follow {me}'s lead; do not assume code is wanted.

Other live seats on this project:
{others_txt}

Project digest (kept by the helper agent; may be empty):
{store.digest(p) or '(none yet)'}

Recent handoffs on this project:
{store.recent_handoffs(p)}

Deeper context on demand (not by default):
  {peek} {p['slug']} --list
  {peek} {p['slug']} --seat N --last 40        (a sibling seat's recent exchanges)
  {peek} {p['slug']} --all --grep <term>       (search every seat on this project)
If {me} says "peek at seat N" or "look at what the other agents did", that is what is meant.

Protocol:
- Keep replies short. {me} reads compressed and asks for more.
- Say plainly what you did not verify.
- If you change files in a folder that is under git, commit your own work with the prefix [{p['name']}] when a piece is done. Never commit other seats' files, and never push unless asked.
- If the folder is not under git, or the work produced no code, there is nothing to commit. Findings worth keeping go in a short markdown file in {notes}
- HANDOFF: when {me} says "hand over", or you notice this conversation is very long, reply with a block that starts with the word HANDOFF: on its own line, then 5-10 lines: done, in flight, files touched, next steps, gotchas. That block is captured automatically.
"""
    if takeover:
        txt += f"""
CONTEXT HANDOVER: you are taking over from seat "{takeover['label']}", which hit its context limit. For the full picture run the peek command on that seat. Its last note: {takeover.get('last_note') or '(none)'}
Its last messages:
{tr.assistant_tail(store.transcript(takeover))}
Start by confirming in two lines what you understand the current state to be, then continue.
"""
    return txt


def launch_seat(p, seat, resume=False, takeover=None):
    cwd = seat.get("cwd") or ""
    if not Path(cwd).is_dir():          # seat recorded on another machine, or the folder moved
        cwd = str(store.home(p))
    extra = [d for d in store.extra_dirs(p) if d != cwd]
    if p.get("home") and p["home"] != cwd and Path(p["home"]).is_dir():
        extra.insert(0, p["home"])
    base = ["claude", "--settings", cf.hooks_file(), *_add_dirs(extra)]
    if resume:
        cmd = base + ["--resume", seat["id"]]
    else:
        first = (f"Your very first line, verbatim: 'I am seat {seat['label']}. /exit me when done, workloop tracks me.' "
                 f"Then say in two lines what you understand this seat is for, and wait for {cf.user_name()}.")
        cmd = base + ["--session-id", seat["id"], "-n", seat["label"], "--append-system-prompt", brief(p, seat, takeover), first]
    return call(cmd, cwd)


# ---------------------------------------------------------------- helper (detached, id not kept)
def helper_brief(p=None):
    me = cf.user_name()
    peek, reg = cf.tool("peek"), cf.tool("reg")
    if p:
        scope = f'project "{p["name"]}" (slug {p["slug"]}). Goal: {p.get("goal") or "(not set)"}'
        seats = "\n".join(f"- {x['label']} ({'retired' if x.get('retired') else 'live'}) last: {x.get('last_note') or '-'}" for x in p.get("seats", [])) or "- none"
        files = f"- digest you maintain: {store.digest_file(p)}\n- handoff log (append only): {store.handoff_file(p)}\n- notes the seats leave: {store.pdir(p) / 'notes'}"
        cmds = f"  {peek} {p['slug']} --list\n  {peek} {p['slug']} --seat N --last 60\n  {peek} {p['slug']} --all --grep <term>"
        folders = [p["home"]] if p.get("home") else []
        folders += p.get("dirs") or []
    else:
        r = store.load()
        scope = "ALL projects"
        seats = "\n".join(f"- {x['name']} ({x['slug']}, {x.get('status', 'active')}): {len(store.live_seats(x))} live seats · {x.get('goal') or ''}" for x in r["projects"]) or "- none"
        files = f"- digests you maintain: {cf.PROJECT_DATA}/<slug>/digest.md (one per project)\n- handoff logs (append only): {cf.PROJECT_DATA}/<slug>/handoffs.md"
        cmds = f"  {peek} --projects\n  {peek} <slug> --list\n  {peek} <slug> --seat N --last 60\n  {peek} <slug> --all --grep <term>"
        folders = sorted({x["home"] for x in store.open_projects(r) if x.get("home")})
    work = "\n".join(f"- {f}" + ("  (git: `git -C <folder> log --since=... --format='%h %s'` is useful)" if store.is_git(f) else "  (not under git)") for f in folders) or "- none (these projects have no work folder)"
    return f"""You are the HELPER for {scope}.
You are detached: your session is not tracked and you own no project work. Seats do the work; you run the workloop around them.
Your cwd is workloop's data folder. The work folders below are attached READ-ONLY: read anything there, never edit, never commit.
{work}

Seats you can look into:
{seats}

How to read what the agents did (their transcripts, tool noise stripped):
{cmds}

WHAT YOU MAY CHANGE (do it yourself, do not hand {me} a to-do):
- The registry {cf.REG}, ONLY through the reg tool (it backs the file up first and logs the change to the handoff logs):
    {reg} projects
    {reg} seats <slug>
    {reg} fold <src> <dst>                 move every seat of <src> into <dst>, close <src>, merge goals
    {reg} move-seat <src> <N|label> <dst>
    {reg} new "<name>" --goal "..."
    {reg} goal <slug> "..."      {reg} rename <slug> "..."
    {reg} close <slug>           {reg} reopen <slug>
    {reg} retire <slug> <N|label>    {reg} unretire <slug> <N|label>    {reg} relabel <slug> <N|label> "..."
  Never hand-edit projects.yaml (the hooks write it concurrently). <src>/<dst>/<slug> take the slug or the name.
- Digest files (rewrite freely) and handoff logs (append only).
- When you fold or split projects, also fold or split their digests, and leave a one-line pointer in the old digest.

Files you own:
{files}

Jobs {me} will ask for, in their words:
- "what have we done so far" → answer from peeks, handoff log and git log where there is one. Compressed: bullets, one line each, newest first.
- "refresh notes" / "refresh the digest" → rewrite the digest file(s): 10-25 lines. Sections: State now · Done recently (with commit hashes if any) · In flight per seat · Next · Gotchas. New seats read this file at start, so write it for a fresh agent.
- "fold X into Y" / "merge these" / "split this out" / "close that" / "retire that seat" → do it with the reg tool, then fix the digests, then report in two lines what moved.
- "what's stale / what's blocked" → compare seats' last activity and notes.
- anything else that is reading, summarising, cross-referencing agents, or tidying the projects.

Rules: most compressed format possible, {me} asks for more. Never speculate about work you did not find in a transcript, log or git. A registry change is cheap and backed up: when asked for one, make it, do not ask twice.
"""


def launch_helper(p=None):
    if p:
        folders = ([p["home"]] if p.get("home") else []) + (p.get("dirs") or [])
        cwd = store.pdir(p)
    else:
        folders = sorted({x["home"] for x in store.open_projects(store.load()) if x.get("home")})
        cwd = cf.DATA
    folders = [f for f in folders if Path(f).is_dir()]
    cmd = ["claude", *_add_dirs(folders), "--append-system-prompt", helper_brief(p),
           "Helper for " + (p["name"] if p else "all projects") + ". Say in one line what you can do, then wait."]
    return call(cmd, cwd)


# ---------------------------------------------------------------- state
def _git(folder, *args):
    try:
        return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20).stdout.strip().splitlines()
    except Exception:
        return []


def state_lines():
    """Compact state of everything, as text lines."""
    reg = store.load()
    out = []
    since = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    for h in sorted({p["home"] for p in store.open_projects(reg) if p.get("home") and Path(p["home"]).is_dir()}):
        if store.is_git(h):
            out.append(f"{h}: {len(_git(h, 'log', f'--since={since}', '--format=%s'))} commits since {since}, {len(_git(h, 'status', '--short'))} dirty files")
        else:
            out.append(f"{h}: not under git")
    for p in store.open_projects(reg):
        la = store.project_last_active(p)
        age = (dt.datetime.now() - la).days if la else None
        seats = store.live_seats(p)
        flag = "STALE" if age is not None and age >= cf.STALE_DAYS else ("LIMIT" if any(x.get("limit") for x in seats) else "")
        out.append(f"{p['name']:<32} seats={len(seats)}  last={la.strftime('%d %b %H:%M') if la else '-':<13} {flag}")
    return out or ["no projects yet"]
