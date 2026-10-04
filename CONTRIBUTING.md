# Contributing

This repository is one skill, two small programs with their
tests, and the scripts that build and check the demo images.

## Run the checks first

```sh
make check
```

That runs `tests/test_swe_day_next.py` and
`tests/test_integrations.py`. Both need `python3` and `git`
and nothing else. The second needs a real clone with its
history and tags, because it reads `git log` and the release
tag.

**The packaging contract asserts on the README.** These will
fail on an innocent-looking prose edit:

- the claim line at the top of the README must appear
  verbatim, and the refusal it describes must be in the
  recorded transcript;
- each install block must carry its own `release=` pin at
  the version both plugin manifests ship;
- `SKILL.md` must stay under 500 lines;
- `evidence/demo-manifest.json` records the SHA-256 of
  `SKILL.md`, of both programs and of the transcript, so
  any edit to one of those four files, prose included,
  fails until the manifest is refreshed as described next.

If you change one of those, change the thing it describes
too.

## Changing a program or the transcript

After any edit to `SKILL.md` or to either program, run:

```sh
make record
make demo
```

`make record` runs `scripts/record_session.py`. It replays
the commands listed in the manifest in a throwaway
directory, writes the transcript with that directory's path
replaced by `/work` and your hostname by `host`, and rewrites the manifest's hashes,
date and interpreter. It needs `bash`, `git` and `python3`.
The transcript carries a new timestamp and process id each
time, so it changes even when the programs did not.
`make demo` rebuilds the two images from the transcript. `make assets` rebuilds the social preview and
needs Chrome or Chromium; `make asset-check` does not.

## What is most useful

Open an issue for any of these. The labels
`good first issue` and `help wanted` mark the ones that are
ready to pick up.

- **A run where an agent went past a human gate.** Say which
  gate, what the agent did next, and which host ran it.
- **A wrapper for a real repository.** The skill binds its
  inputs through a per-repository wrapper and ships none. A
  worked wrapper is the most valuable thing this repository
  can receive.
- **A lock state the program handles wrongly.** Attach the
  metadata file with the hostname and paths removed.

## Pull requests

Prose changes to `SKILL.md` and `references/steps.md` are
welcome. Say what an agent did before the change and what it
does after, on the same work item.

Keep `SKILL.md` under 500 lines; the suite enforces it.
Frontmatter carries `name` and `description` and nothing
else.

The top-level `skill` is a symlink to `skills/swe-day/`. Do
not reverse that orientation.

Commit with your own identity and no `Co-authored-by`
trailer of any kind. The suite fails on one anywhere in
history, so do not apply review suggestions through the
GitHub UI.
