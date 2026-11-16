# Contributing

Pull requests are welcome. This repo holds code only, so please keep anything personal out of it.

## Do not include

- **Personal information**: real names, email addresses, usernames of other people, phone numbers, home-folder paths such as `C:\Users\<you>\...` or `/Users/<you>/...`.
- **Your workloop data**: anything from your data folder (`~/.workloop`), including `projects.yaml`, handoff logs, digests, notes, architected project files and `config.yaml`.
- **Seat content**: transcripts, seat briefs, last notes, session ids, or output pasted from `workloop peek`.
- **Details of your work**: project names, goals, folder names, hostnames, internal URLs, ticket numbers, or anything from an employer or client.
- **Secrets**: tokens, keys, passwords, hook settings that contain them.

This applies to code, tests, comments, commit messages, the PR description and screenshots. If you need an example, make one up (`Patching`, `seat 1`, `/path/to/folder`).

## Before you open a PR

1. Set a no-reply git identity for this repo so your email is not in the commits (see the README, "Contributing changes back").
2. Read your own diff: `git diff main...HEAD`.
3. Check that no data files slipped in: `git status` should list code and docs only.
4. Reproduce bugs with `WORKLOOP_HOME` pointed at an empty temporary folder, so examples come from throwaway data and not from your real projects.

A PR that contains personal or work data will be closed without merging, because the data would stay in the public history.
