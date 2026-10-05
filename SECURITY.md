# Security

## Reporting a vulnerability

Report privately through GitHub:
<https://github.com/trycopilotai/swe-day/security/advisories/new>

That opens a private security advisory visible only to the
maintainers. Do not put the details of a vulnerability in a
public issue.

If that link shows "Not Found", private reporting is not
turned on for this repository. Open a public issue titled
"Security report waiting" that says only that you have a
report, with no details, and a maintainer will arrange a
private channel.

## What is in scope

- **Prompt content that redirects an agent.** `SKILL.md` and
  the two files under `references/` are instructions an
  agent follows through a whole unit of work, including
  commits and a landing step. Text in any of them that makes
  an agent skip a human gate, push to a shared repository,
  or treat repository content as instructions is a valid
  report.
- **The lock program.**
  `skills/swe-day/scripts/swe_day_lock.py` creates and
  removes one lock directory, and writes one metadata file
  inside it, at a path the caller names relative to a
  repository root, or at its default path there when none is
  named. It refuses a path argument that is
  absolute, contains `..`, or resolves outside that root,
  and it creates missing parent directories inside the root.
  A path argument that makes it write or delete outside the
  root is a finding. So is a sequence of `set-phase`
  and `clear-gate` commands that, within one held lock,
  advances a run past a human gate that was not cleared, or
  a command that changes a lock whose owner and session the
  caller does not state.
- **The banner program.**
  `skills/swe-day/scripts/swe_day_next.py` reads the lock
  metadata and prints a banner of one to three lines. It
  writes no file, and turns off Python's bytecode cache so
  that importing the lock program writes none either. A lock state that the lock program
  itself can write, for which the banner shows
  `OWNER: agent` while `set-phase` refuses the next phase,
  is a finding.
- **The install blocks.** The two README blocks run
  `mkdir -p`, `mktemp -d`, `git clone`, `cp`, `mv` and
  `rm -rf`, all inside one skills directory under `$HOME`. A
  repository state that makes either block write or delete
  outside its install target is in scope.
- **The build scripts.** `assets/build.py` finds a Chrome or
  Chromium binary from a fixed candidate list, runs it
  headless with a temporary profile directory, and writes
  the preview PNG and its stamp. `scripts/generate_demo.py`
  writes two SVG files; `scripts/verify_demo.py` only
  reads. `scripts/record_session.py` copies `skills/` into
  a temporary directory, runs the two programs there
  through `bash`, and rewrites the transcript and the
  manifest.
  `tests/test_integrations.py` runs `git` against the
  repository root and runs the lock program in a temporary
  directory. `tests/test_swe_day_next.py` runs both programs
  in temporary directories and imports the lock program to
  read its phase model.

## The lock is advisory

The lock coordinates cooperating callers. It is not a
security boundary, and these are known limits, not findings:

- Owner and session are plain strings that `status` prints.
  Any caller that can read the lock can state them, and any
  caller can run `clear-gate`. The program cannot tell an
  operator from an agent; the skill text is what tells an
  agent not to clear a gate on its own.
- The gate rules hold within one held lock. `release`
  followed by `acquire --phase <later phase>` starts a new
  run past earlier gates, and `release --abandon` ends a run
  with a gate pending. The program does not police either;
  the skill text reserves both for the operator.
- Anything that can write the repository can edit or delete
  the lock directory directly, including writing metadata
  the program would never write.
- Check-then-change steps are serialized with `flock` on the
  lock's parent directory. That protects only callers that
  use this program. Both programs need `fcntl` and do not
  run on a system without it. A process
  that swaps a directory on the lock path for a symlink
  while a command runs can redirect it.
- The metadata records the hostname, the process id, and the
  absolute repository path, so a lock directory should not
  be committed.

## What is out of scope

The skill sequences other skills that a wrapper binds. Their
behaviour, and the behaviour of Claude Code, Codex, or any
other host, is out of scope here. Report those to their own
maintainers.
