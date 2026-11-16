# workloop

A terminal menu for running several long-lived Claude Code sessions ("seats") per project, and keeping track of them.

- **Project**: a name, a goal, and optionally a home folder with extra folders attached. A folder does not need to be a git repo, and several projects can share one folder.
- **Seat**: one Claude Code session inside a project. Seats are freeflow: a seat can stay a conversation (investigation, planning, writing) or turn into building something. It commits only if it changed files in a folder that is under git.
- **Helper**: a detached session that reads the seats' transcripts, writes the project digest, and tidies the registry (fold projects, move or retire seats).
- **Architected project** (optional side route): idea → eval → plan → build → ship, one agent per stage, with a fast mode that goes from a one-line steer to a visual plan.

## Install

Needs Python 3.8+ and the `claude` CLI on PATH.

```
pip install -r requirements.txt
```

Then put `bin/` on PATH (Windows uses `bin/workloop.cmd`, macOS and Linux use `bin/workloop`) and run `workloop`. The first run asks for your name, which the agents use in their briefs.

### Setting up a new machine, step by step

1. Check the prerequisites: `python --version` (3.8+), `git --version`, `claude --version` (installed and signed in).
2. Get the code: `git clone <this repo's URL>`, or download the ZIP from the repo page if git should not be signed in on the machine.
3. From the repo folder: `pip install -r requirements.txt`.
4. Add the repo's `bin` folder to PATH. To try it without changing PATH, run `python bin/workloop` (Windows: `python bin\workloop`).
5. Run `workloop` and give your name.
6. Press `n` to create the first project: a name, a one-line goal and a home folder (the folder you work from; leave it blank for pure discussion or investigation work). Say yes to adding the first seat.

To check the install without starting Claude, set `WORKLOOP_DRYRUN=1` first: workloop then prints the Claude command it would run.

### Contributing changes back

Before the first commit on a machine, set the git identity for this repo so no personal email lands in the history. GitHub lists your no-reply address under Settings → Emails ("Keep my email addresses private"):

```
git config user.name "<your GitHub username>"
git config user.email "<id>+<username>@users.noreply.github.com"
```

Projects, seats and notes live in the data folder (below), never in the repo, so nothing personal is committed by using workloop.

## Where things live

The repo holds code only. Everything personal is in the data folder, `~/.workloop` by default (set `WORKLOOP_HOME` to move it):

```
config.yaml           your name
projects.yaml         the registry: projects and their seats
projects/<slug>/      handoffs.md, digest.md, notes/
architected/<slug>/   staged projects: idea.md, loop.yaml, stage files
backups/              registry copies taken before `workloop reg` edits
hooks.json            hook settings passed to each session
```

Nothing is written into the folders you work in. Hooks are passed to Claude with `--settings`, so a seat is only tracked when it is started or resumed from workloop.

## Main screen

| key | does |
|---|---|
| `1-9` | open a project |
| `n` | new project: name, goal, home folder (blank for none) |
| `s` | state: last activity per project, commits and dirty files for folders under git |
| `?` | helper across all projects |
| `c` | closed projects, reopen one |
| `a` | architected projects |

Inside a project:

| key | does |
|---|---|
| `1-9` | resume a seat |
| `a` | add a seat (label, start folder) |
| `h` | context handover: retire a seat and start a fresh replacement briefed with its last messages |
| `r` | retire a seat |
| `d` / `o` | read the digest / the handoff log |
| `?` | helper for this project |
| `e` | edit name, goal, folders, "read first", "do not touch" |
| `f` | open the project's notes folder |
| `x` | close the project |

## Flags

- **LIMIT**: the seat hit its context limit and is compacting right now.
- **EXTENDED**: the seat carried on after compacting (`x3` = three times). It still works, but earlier detail may be lost, so consider a handover (`h`) to a fresh seat.
- **stale**: no activity on the project for 5 days.

## What a seat is told

Its project and goal, its folders, what to read first and what to leave alone, the other live seats and their last notes, the digest, recent handoffs, and how to peek at sibling seats. When you say "hand over", it replies with a `HANDOFF:` block, which is captured into the handoff log.

## Commands agents use

```
workloop peek <project> --list                 seats and message counts
workloop peek <project> --seat N --last 40     a seat's recent exchanges
workloop peek <project> --all --grep <term>    search every seat
workloop reg projects | seats <project>
workloop reg fold <src> <dst> | move-seat <src> <N|label> <dst>
workloop reg new "<name>" --goal "..." | goal | rename | close | reopen | retire | unretire | relabel
```

## Layout

```
bin/workloop          entry point (menu, peek, reg, hook)
workloop/store.py     registry, handoffs, digests
workloop/seats.py     seat and helper briefs, launching Claude
workloop/tools.py     hook, peek, reg
workloop/arch.py      architected projects
workloop/ui.py        menus
workloop/prompts/     stage prompts for architected projects
```

`WORKLOOP_DRYRUN=1` prints the Claude command instead of running it.

## Licence

MIT. See [LICENSE](LICENSE).
