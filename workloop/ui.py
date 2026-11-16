"""The menus. Main screen is projects → seats; architected projects are a side route."""
import datetime as dt, os, sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from . import arch, config as cf, seats, store

con = Console()

SPLASH = r"""
 __      __  ___   ___  _  __ _     ___   ___  ___
 \ \    / / / _ \ | _ \| |/ /| |   / _ \ / _ \| _ \
  \ \/\/ / | (_) ||   /| ' < | |__| (_) | (_) |  _/
   \_/\_/   \___/ |_|_\|_|\_\|____|\___/ \___/|_|
"""


def _age(ts):
    if not ts:
        return "-"
    d = dt.datetime.now() - ts
    if d.days >= 1:
        return f"{d.days}d"
    h = d.seconds // 3600
    return f"{h}h" if h else f"{d.seconds // 60}m"


def _short(path, n=38):
    s = str(path or "")
    return s if len(s) <= n else "…" + s[-(n - 1):]


def ask_folder(label, default=""):
    """A folder that exists, or blank. Re-asks on a typo."""
    while True:
        v = Prompt.ask(label, default=default, show_default=bool(default)).strip().strip('"')
        if not v or v == "-":
            return ""
        v = os.path.abspath(os.path.expanduser(v))
        if Path(v).is_dir():
            return v
        con.print(f"[red]not a folder:[/] {v}  [dim](blank or - for none)[/]")


# ---------------------------------------------------------------- tables
def projects_table(ps):
    t = Table(title="PROJECTS", expand=False)
    t.add_column("#", justify="right", style="dim"); t.add_column("project", style="bold"); t.add_column("seats", justify="right")
    t.add_column("last"); t.add_column("flags"); t.add_column("folder", style="dim"); t.add_column("goal", max_width=50)
    for i, p in enumerate(ps, 1):
        live = store.live_seats(p)
        la = store.project_last_active(p)
        flags = []
        if any(x.get("limit") for x in live):
            flags.append("[red]LIMIT[/]")
        if la and (dt.datetime.now() - la).days >= cf.STALE_DAYS:
            flags.append(f"[yellow]stale {(dt.datetime.now() - la).days}d[/]")
        t.add_row(str(i), p["name"], str(len(live)), _age(la), " ".join(flags), _short(p.get("home") or "(no folder)"), (p.get("goal") or "")[:50])
    con.print(t)


def seats_table(p):
    t = Table(title=f"[bold]{p['name']}[/]  [dim]{(p.get('goal') or '')[:70]}[/]", expand=False)
    t.add_column("#", justify="right", style="dim"); t.add_column("seat", style="bold"); t.add_column("last"); t.add_column("flag"); t.add_column("last note", max_width=80)
    live = store.live_seats(p)
    for i, x in enumerate(live, 1):
        t.add_row(str(i), x["label"], _age(store.seat_mtime(x)), "[red]LIMIT[/]" if x.get("limit") else "", (x.get("last_note") or "")[:80])
    con.print(t)
    return live


def digest_line(p):
    f = store.digest_file(p)
    if not f.exists():
        return "[dim]digest: none yet · press ? then say 'refresh notes'[/]"
    lines = [l.strip("- ").strip() for l in cf.read(f).splitlines() if l.startswith("- ")]
    return f"[green]digest[/] refreshed {dt.datetime.fromtimestamp(f.stat().st_mtime):%d %b %H:%M} · {lines[0][:90] if lines else ''}  [dim](d to read)[/]"


# ---------------------------------------------------------------- actions
def add_seat(slug, takeover_id=None):
    reg = store.load()
    p = store.find_project(reg, slug)
    old = next((s for s in p.get("seats", []) if s["id"] == takeover_id), None)
    label = Prompt.ask("seat label", default=old["label"] if old else f"{p['name']} / seat {len(p.get('seats', [])) + 1}").strip()
    cwd = ask_folder("start in folder", default=(old or {}).get("cwd") if old and Path(old.get("cwd", "")).is_dir() else str(store.home(p))) or str(store.home(p))
    with store.mutate() as r:
        p = store.find_project(r, slug)
        seat = store.new_seat(p, label=label, cwd=cwd)
        if old:
            for s in p["seats"]:
                if s["id"] == takeover_id:
                    s["retired"] = True
            store.append_handoff(p, old["label"], f"retired; taken over by {seat['label']}")
    con.print(f"[dim]launching claude · {seat['label']} · {cwd}[/]")
    seats.launch_seat(p, seat, takeover=old)


def edit_project(slug):
    p = store.find_project(store.load(), slug)
    con.print("[dim]Enter keeps the current value. For a folder, - clears it.[/]")
    name = Prompt.ask("name", default=p["name"]).strip() or p["name"]
    goal = Prompt.ask("goal", default=p.get("goal") or "").strip()
    home = ask_folder("home folder (where seats start)", default=p.get("home") or "")
    con.print(f"  extra folders now: {', '.join(p.get('dirs') or []) or 'none'}")
    dirs = list(p.get("dirs") or [])
    while True:
        c = Prompt.ask("  extra folders: [bold]a[/] add · [bold]c[/] clear · Enter done", default="", show_default=False).strip().lower()
        if c == "a":
            d = ask_folder("  folder")
            if d and d not in dirs:
                dirs.append(d)
        elif c == "c":
            dirs = []
        else:
            break
    read_first = Prompt.ask("read first (files a new seat should read)", default=p.get("read_first") or "").strip()
    avoid = Prompt.ask("do not touch (folders or files seats must leave alone)", default=p.get("avoid") or "").strip()
    with store.mutate() as r:
        q = store.find_project(r, slug)
        q.update(name=name, goal=goal, home=home, dirs=dirs, read_first="" if read_first == "-" else read_first, avoid="" if avoid == "-" else avoid)


def new_project():
    name = Prompt.ask("project name").strip()
    if not name:
        return
    goal = Prompt.ask("goal (one line)", default="").strip()
    reg = store.load()
    last_home = next((p["home"] for p in reversed(reg["projects"]) if p.get("home")), "")
    con.print("[dim]Home folder: where this project's seats start. Blank or - if it has none (pure discussion or investigation).[/]")
    home = ask_folder("home folder", default=last_home)
    sib = store.sibling_settings(reg, home)
    with store.mutate() as r:
        p = store.new_project(r, name, goal, home, dirs=list(sib.get("dirs") or []) if sib else [],
                              read_first=sib.get("read_first", "") if sib else "", avoid=sib.get("avoid", "") if sib else "")
    if sib:
        con.print(f"[dim]copied read-first, do-not-touch and extra folders from '{sib['name']}' (same home folder) · e in the project to change[/]")
    con.print(f"[green]created[/] {p['name']}  [dim]{store.pdir(p)}[/]")
    if Confirm.ask("Add the first seat now?", default=True):
        add_seat(p["slug"])


def project_view(slug):
    while True:
        p = store.find_project(store.load(), slug)
        if not p:
            return
        con.print()
        live = seats_table(p)
        folder = p.get("home") or "(no folder: seats start in the project's notes folder)"
        con.print(f"  [dim]{folder}{' · git' if p.get('home') and store.is_git(p['home']) else ''}{' · +' + str(len(p['dirs'])) + ' attached' if p.get('dirs') else ''}[/]")
        con.print("  " + digest_line(p))
        con.print("  [bold]1-9[/] resume seat   [bold]a[/] add seat   [bold]h[/] context handover   [bold]r[/] retire seat   [bold]d[/] digest   [bold]o[/] handoffs\n"
                  "  [bold]?[/] helper   [bold]e[/] edit project   [bold]f[/] open notes folder   [bold]x[/] close project   [bold]b[/] back")
        c = Prompt.ask("›", default="b", show_default=False).strip().lower()
        if c.isdigit() and 1 <= int(c) <= len(live):
            seat = live[int(c) - 1]
            con.print(f"[dim]resuming · {seat['label']}[/]")
            seats.launch_seat(p, seat, resume=True)
        elif c == "a":
            add_seat(slug)
        elif c in ("h", "r"):
            n = Prompt.ask("context handover: which seat # is at its limit" if c == "h" else "retire which seat #", default="").strip()
            if n.isdigit() and 1 <= int(n) <= len(live):
                old = live[int(n) - 1]
                if c == "h":
                    con.print("[yellow]If the old agent is still open, say 'hand over' to it first so it writes its HANDOFF block, then close it.[/]")
                    if Confirm.ask(f"Start a replacement for {old['label']} now?", default=True):
                        add_seat(slug, takeover_id=old["id"])
                elif Confirm.ask(f"Retire {old['label']}? (hidden, transcript kept)", default=False):
                    with store.mutate() as r:
                        _, s = store.find_seat(r, old["id"])
                        s["retired"] = True
        elif c == "d":
            con.print(Panel(store.digest(p) or "(none yet — ask the helper to refresh notes)", title=f"digest · {p['name']}"))
        elif c == "o":
            con.print(Panel(store.recent_handoffs(p, 60), title=f"handoffs · {p['name']}"))
        elif c == "?":
            con.print(f"[dim]helper · {p['name']} · detached, not tracked[/]")
            seats.launch_helper(p)
        elif c == "e":
            edit_project(slug)
        elif c == "f":
            cf.open_path(store.pdir(p))
        elif c == "x":
            if Confirm.ask("Close project (seats kept, hidden from the list)?", default=False):
                with store.mutate() as r:
                    store.find_project(r, slug)["status"] = "closed"
                return
        elif c == "b":
            return


def closed_menu():
    ps = [p for p in store.load()["projects"] if p.get("status") == "closed"]
    if not ps:
        con.print("[dim]no closed projects[/]")
        return
    for i, p in enumerate(ps, 1):
        con.print(f"  [bold]{i}[/]  {p['name']}  [dim]{len(p.get('seats', []))} seats{' · folded into ' + p['folded_into'] if p.get('folded_into') else ''}[/]")
    n = Prompt.ask("reopen # (Enter = back)", default="").strip()
    if n.isdigit() and 1 <= int(n) <= len(ps):
        with store.mutate() as r:
            q = store.find_project(r, ps[int(n) - 1]["slug"])
            q["status"] = "active"
            q.pop("folded_into", None)


def first_run():
    if cf.load_config().get("name"):
        return
    con.print("[bold]First run.[/] Agents address you by name in their briefs.")
    name = Prompt.ask("your name", default=os.environ.get("USERNAME") or os.environ.get("USER") or "").strip()
    cf.save_config({"name": name or "the user"})
    con.print(f"[dim]data folder: {cf.DATA}[/]")


def main():
    cf.ensure_data()
    try:
        first_run()
        if not seats.available():
            con.print("[red]claude CLI not found on PATH. Menus work, launching seats will not.[/]")
        while True:
            ps = store.open_projects(store.load())
            con.print(f"[bold yellow]{SPLASH}[/]")
            if ps:
                projects_table(ps)
            else:
                con.print("  [dim]No projects yet. Press n to make one.[/]")
            narch = len(arch.Project.active())
            con.print(f"  [bold]1-9[/] open project   [bold]n[/] new project   [bold]s[/] state   [bold]?[/] helper (all projects)   [bold]c[/] closed\n"
                      f"  [bold]a[/] architected projects (staged: plan → build → ship){f' · {narch} active' if narch else ''}   [bold]q[/] quit")
            c = Prompt.ask("›", default="", show_default=False).strip().lower()
            if c.isdigit() and 1 <= int(c) <= len(ps):
                project_view(ps[int(c) - 1]["slug"])
            elif c == "n":
                new_project()
            elif c == "s":
                con.print(Panel("\n".join(seats.state_lines()), title="state"))
                Prompt.ask("[dim]enter to continue[/]", default="", show_default=False)
            elif c == "?":
                con.print("[dim]helper · all projects · detached, not tracked[/]")
                seats.launch_helper()
            elif c == "c":
                closed_menu()
            elif c == "a":
                arch.menu()
            elif c == "q":
                break
    except (KeyboardInterrupt, EOFError):
        con.print()
    sys.exit(0)
