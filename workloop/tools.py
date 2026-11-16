"""Non-interactive subcommands: `workloop hook`, `workloop peek`, `workloop reg`.
hook is called by Claude Code; peek and reg are called by agents (and by you)."""
import argparse, json, sys
from . import config as cf, store, transcripts as tr


# ---------------------------------------------------------------- hook
def hook(argv=None):
    """Reads the hook JSON on stdin.
    Stop        -> seat last_active / last_note; capture HANDOFF: blocks.
    PreCompact  -> flag the seat as at its context limit, log it.
    SessionEnd  -> last_active + note.
    Sessions workloop does not know are ignored."""
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except Exception:
        return
    sid = payload.get("session_id", "")
    event = payload.get("hook_event_name", "")
    transcript = payload.get("transcript_path", "")
    text = tr.last_assistant(transcript) if transcript else ""
    flat = " ".join(text.split())[:160]
    limit_hit = None
    with store.mutate() as reg:
        p, seat = store.find_seat(reg, sid)
        if seat:
            seat["last_active"] = store.now()
            if transcript:
                seat["transcript"] = transcript
            if flat:
                seat["last_note"] = flat
                if "HANDOFF:" in text and event == "Stop":
                    store.append_handoff(p, seat["label"], text[text.index("HANDOFF:") + len("HANDOFF:"):].strip())
            if event == "PreCompact":
                seat["limit"] = True
                store.append_handoff(p, seat["label"], f"⚠ hit context limit. Last note: {seat.get('last_note') or '(none)'}\nContext handover: workloop → project → h.")
                limit_hit = seat["label"]
            elif event == "SessionEnd":
                store.append_handoff(p, seat["label"], f"session ended. Last note: {seat.get('last_note') or '(none)'}")
    if limit_hit:
        cf.notify("workloop", f"{limit_hit} is at its context limit. Hand over.")
    if not seat:
        from . import arch
        arch.hook(sid, event, flat)


# ---------------------------------------------------------------- peek
def peek(argv):
    ap = argparse.ArgumentParser(prog="workloop peek", description="Read what a seat said (user + assistant text, tool noise stripped).")
    ap.add_argument("project", nargs="?")
    ap.add_argument("--projects", action="store_true", help="list projects")
    ap.add_argument("--seat", help="index from --list, part of the label, or start of the session id")
    ap.add_argument("--all", action="store_true", help="every seat on the project")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--last", type=int, default=20)
    ap.add_argument("--grep")
    ap.add_argument("--width", type=int, default=500)
    a = ap.parse_args(argv)
    reg = store.load()
    if a.projects or not a.project:
        for x in reg["projects"]:
            print(f"{x['slug']:<28} {x.get('status', 'active'):<7} {len(store.live_seats(x))} live seats   {(x.get('goal') or '')[:70]}")
        return
    p = store.find_project(reg, a.project)
    if not p:
        sys.exit(f"no project '{a.project}'. Projects: {[x['slug'] for x in reg['projects']]}")
    seats = p.get("seats", [])
    if a.list or (not a.seat and not a.all):
        for i, x in enumerate(seats, 1):
            n = len(tr.messages(store.transcript(x)))
            print(f"{i}  {x['label']:<36} {'retired' if x.get('retired') else 'live':<8} {n:>4} msgs  last: {x.get('last_active', '')}")
        return
    targets = seats if a.all else []
    if a.seat:
        if a.seat.isdigit() and 1 <= int(a.seat) <= len(seats):
            targets = [seats[int(a.seat) - 1]]
        else:
            targets = [x for x in seats if a.seat.lower() in x["label"].lower() or x["id"].startswith(a.seat)]
    if not targets:
        sys.exit("no such seat")
    for x in targets:
        msgs = tr.messages(store.transcript(x))
        if a.grep:
            g = a.grep.lower()
            msgs = [m for m in msgs if g in m[1].lower()]
        else:
            msgs = msgs[-a.last:]
        print(f"===== {x['label']}  ({len(msgs)} shown) =====")
        for role, txt in msgs:
            print(f"[{role[:4]}] {txt[:a.width]}{'…' if len(txt) > a.width else ''}")
        print()


# ---------------------------------------------------------------- reg
def _die(msg):
    sys.exit(f"workloop reg: {msg}")


def _project(reg, key):
    p = store.find_project(reg, key)
    if not p:
        _die(f"no project '{key}'. Known: " + ", ".join(x["slug"] for x in reg["projects"]))
    return p


def _seat(p, key):
    seats = p.get("seats", [])
    if key.isdigit():
        i = int(key)
        if not 1 <= i <= len(seats):
            _die(f"seat index {i} out of range 1-{len(seats)} on {p['slug']}")
        return seats[i - 1]
    hits = [x for x in seats if x["label"] == key]
    if len(hits) != 1:
        _die(f"{len(hits)} seats labelled '{key}' on {p['slug']} (use the index from `reg seats {p['slug']}`)")
    return hits[0]


def _move(src, seat, dst):
    src["seats"].remove(seat)
    seat.setdefault("from_project", src["slug"])
    dst.setdefault("seats", []).append(seat)


def reg(argv):
    """Registry surgery. Every write first copies projects.yaml into backups/.
    Seats keep their session ids, so hooks and peek keep working after a move."""
    ap = argparse.ArgumentParser(prog="workloop reg", description=reg.__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("projects", help="every project incl. closed, with seat counts")
    s = sub.add_parser("seats", help="seats on a project"); s.add_argument("project")
    s = sub.add_parser("fold", help="move ALL seats of src into dst, close src, merge the goal"); s.add_argument("src"); s.add_argument("dst")
    s = sub.add_parser("move-seat"); s.add_argument("src"); s.add_argument("seat"); s.add_argument("dst")
    s = sub.add_parser("new"); s.add_argument("name"); s.add_argument("--goal", default=""); s.add_argument("--home", default="")
    for name in ("goal", "rename"):
        s = sub.add_parser(name); s.add_argument("project"); s.add_argument("text")
    for name in ("close", "reopen"):
        s = sub.add_parser(name); s.add_argument("project")
    for name in ("retire", "unretire"):
        s = sub.add_parser(name); s.add_argument("project"); s.add_argument("seat")
    s = sub.add_parser("relabel"); s.add_argument("project"); s.add_argument("seat"); s.add_argument("text")
    a = ap.parse_args(argv)

    if a.cmd == "projects":
        for p in store.load()["projects"]:
            extra = f"  (folded into {p['folded_into']})" if p.get("folded_into") else ""
            print(f"{p['slug']:<28} {p.get('status', 'active'):<7} seats {len(store.live_seats(p))}/{len(p.get('seats', []))}  {p['name']}{extra}")
        return
    if a.cmd == "seats":
        p = _project(store.load(), a.project)
        for i, x in enumerate(p.get("seats", []), 1):
            state = "retired" if x.get("retired") else ("LIMIT" if x.get("limit") else "live")
            print(f"{i:>2}  {x['label']:<36} {state:<8} last {x.get('last_active', '-')}  {(x.get('last_note') or '')[:60]}")
        return

    with store.mutate(backup=True) as r:
        if a.cmd == "fold":
            src, dst = _project(r, a.src), _project(r, a.dst)
            if src is dst:
                _die("src and dst are the same project")
            labels = [x["label"] for x in src.get("seats", [])]
            for seat in list(src.get("seats", [])):
                _move(src, seat, dst)
            src["status"], src["folded_into"] = "closed", dst["slug"]
            if src.get("goal") and src["goal"] not in (dst.get("goal") or ""):
                dst["goal"] = ((dst.get("goal") or "").rstrip(" .") + ". " + src["goal"]).strip(". ").strip()
            store.append_handoff(dst, "reg", f"project '{src['name']}' folded in: seats {', '.join(labels) or 'none'}. Its old handoff log stays at {store.handoff_file(src)}.")
            store.append_handoff(src, "reg", f"folded into '{dst['name']}' ({dst['slug']}); all seats moved, project closed.")
            print(f"folded {src['slug']} -> {dst['slug']}: {len(labels)} seat(s) moved, {src['slug']} closed")
        elif a.cmd == "move-seat":
            src, dst = _project(r, a.src), _project(r, a.dst)
            seat = _seat(src, a.seat)
            _move(src, seat, dst)
            store.append_handoff(dst, "reg", f"seat '{seat['label']}' moved in from '{src['name']}'.")
            store.append_handoff(src, "reg", f"seat '{seat['label']}' moved out to '{dst['name']}'.")
            print(f"moved '{seat['label']}' {src['slug']} -> {dst['slug']}")
        elif a.cmd == "new":
            if store.find_project(r, a.name) or store.find_project(r, store.slugify(a.name)):
                _die(f"project '{a.name}' exists")
            p = store.new_project(r, a.name.strip(), a.goal.strip(), a.home.strip())
            print(f"new project {p['slug']}")
        elif a.cmd == "goal":
            p = _project(r, a.project); p["goal"] = a.text.strip(); print(f"{p['slug']} goal: {p['goal']}")
        elif a.cmd == "rename":
            p = _project(r, a.project); old = p["name"]; p["name"] = a.text.strip(); print(f"renamed '{old}' -> '{p['name']}' (slug {p['slug']} kept)")
        elif a.cmd == "close":
            p = _project(r, a.project); p["status"] = "closed"; print(f"closed {p['slug']}")
        elif a.cmd == "reopen":
            p = _project(r, a.project); p["status"] = "active"; p.pop("folded_into", None); print(f"reopened {p['slug']}")
        elif a.cmd == "retire":
            seat = _seat(_project(r, a.project), a.seat); seat["retired"] = True; print(f"retired '{seat['label']}'")
        elif a.cmd == "unretire":
            seat = _seat(_project(r, a.project), a.seat); seat["retired"] = False; print(f"live again: '{seat['label']}'")
        elif a.cmd == "relabel":
            seat = _seat(_project(r, a.project), a.seat); old = seat["label"]; seat["label"] = a.text.strip(); print(f"'{old}' -> '{seat['label']}'")
