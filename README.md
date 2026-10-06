# swe-day

A skill that has a coding agent run one bounded unit of
software work end to end, stopping at a human gate wherever
judgment decides the next move. It ships two small programs:
a single-writer lock and a next-action banner.

swe_day_lock.py refuses to acquire a lock that is held.

<picture>
  <source
    media="(prefers-reduced-motion: reduce)"
    srcset="assets/poster.svg"
  />
  <img
    src="assets/demo.svg"
    alt="A terminal acquires the swe-day lock, is refused a second acquire with exit status 2, renders the next-action banner, is refused a release by another caller with exit status 3, and releases the lock."
    width="100%"
  />
</picture>

The demo is reconstructed from
[`evidence/transcripts/lock-session.txt`](evidence/transcripts/lock-session.txt),
a captured run of the two programs in a throwaway
repository.

**Not measured, stated up front.**

- No agent ran a SWE day to produce the evidence here. The
  lock-session transcript shows only the lock and the
  banner, and both agent invocations under Evidence stopped
  at step 0.
- Whether an agent that follows `SKILL.md` actually stops at
  each human gate after step 0 has not been measured.
- Whether an agent takes the lock on a run with no wrapper
  that goes past step 0 has not been measured. Neither
  invocation went past step 0, and the recorded lock session
  does not use `--proceed-without`.
- The invocations loaded the skill from a plugin directory
  (Claude Code) and from a repository's `.agents/skills/`
  (Codex), not through the install blocks below.

## What is in it

- [`skills/swe-day/SKILL.md`](skills/swe-day/SKILL.md) is
  the spec: the signature, the inputs a wrapper binds, the
  stateful invocation contract, phase roles, operating
  discipline, and Active Run mode.
- [`skills/swe-day/references/steps.md`](skills/swe-day/references/steps.md)
  is the steps, numbered 0 to 17, each tagged with its owner
  and, where it has one, its blocking gate.
- [`skills/swe-day/references/summary.md`](skills/swe-day/references/summary.md)
  is a short summary for a human reader.
- [`skills/swe-day/scripts/swe_day_lock.py`](skills/swe-day/scripts/swe_day_lock.py)
  manages the lock: `acquire`, `status`, `set-phase`,
  `clear-gate` and `release`.
- [`skills/swe-day/scripts/swe_day_next.py`](skills/swe-day/scripts/swe_day_next.py)
  renders the next-action banner from the lock.

## Not included

The skill is a conductor. It sequences nine other skills,
and none of them ships here. Step 0 of
[`steps.md`](skills/swe-day/references/steps.md) names each
one with the name below:

- `fix-loop`: a bounded fix loop (step 8).
- `improve-coverage`: a coverage improver (step 10).
- `plan-commits`: a commit planner, called as
  `planCommits()` (steps 10, 13 and 16).
- `mutation-testing`: a mutation-testing audit (step 11).
- `result-visualizer`: a result visualizer (step 12).
- `review-watch`: a review watcher (step 12).
- `address-comments`: an operator-comment ingest (steps 10,
  12 and 13).
- `code-review`: a multi-persona code review (steps 10 and
  13).
- `handoff`: a handoff recorder (step 16).

A name resolves when a skill of that name is listed among
the agent session's available skills, or when a
per-repository wrapper binds the name to a skill or protocol
that is listed there. When one does not resolve, step 0
stops before taking the lock or editing anything and names
what is missing. It goes on only if the operator explicitly
agrees to run without them; the lock then records that
consent under the names above
(`acquire --proceed-without <name>`), and each step that
needed a missing skill is reported as not run. That check
is an instruction to the agent: neither program looks for
the skills, and the lock program records any non-empty name
it is given.

Every run that goes past the step 0 preflight takes the
lock at the end of step 0, with or without a wrapper. A run
that stops at the preflight writes nothing and takes no
lock. When no lock path is bound, the lock goes at the lock
program's default path inside `ops_repo`, the operator's
private operational repository, so the next-action banner
and the human gates hold for the rest of the run. Run
`python3 <skill-dir>/scripts/swe_day_lock.py --repo <ops_repo> status`
(`<skill-dir>` is the installed skill's directory, as SKILL.md's
Helper scripts section explains) to see that path:
it prints `lock_path` and writes nothing, before or after a
lock exists. Taking the lock is the run's first write to
that repository. Do not commit the lock directory; its
metadata records the hostname, process id and absolute
repository path.

None of the nine skills ships here, so on an install
without them every run stops at step 0 until each one
resolves or the operator agrees to go on without it.

## Use it

Read [`skills/swe-day/SKILL.md`](skills/swe-day/SKILL.md)
before you install it. The file is an instruction set that
steers an agent, so both installs below are pinned to a tag
rather than to `main`.

### Claude Code

Save this as `install.sh` and run it with `sh install.sh`.
It sets `set -eu` and an `EXIT` trap, so pasting it straight
into an interactive shell will end that shell if the clone
fails.

```sh
set -eu
release=v0.1.8
install_target="$HOME/.claude/skills/swe-day"
install_parent="$(dirname "$install_target")"
mkdir -p "$install_parent"
install_tmp="$(mktemp -d "$install_parent/.swe-day.XXXXXX")"
install_stage="$install_tmp/package"
rollback_install() {
  if [ ! -e "$install_target" ]; then
    if [ -e "$install_tmp/previous" ]; then
      mv "$install_tmp/previous" "$install_target"
    fi
  fi
  rm -rf "$install_tmp"
}
trap rollback_install EXIT
git clone --quiet --depth 1 --branch "$release" \
  https://github.com/trycopilotai/swe-day \
  "$install_tmp/clone"
mkdir -p "$install_stage"
cp -R "$install_tmp/clone/skill/." "$install_stage/"
if [ -e "$install_target" ]; then
  mv "$install_target" "$install_tmp/previous"
fi
mv "$install_stage" "$install_target"
trap - EXIT
rm -rf "$install_tmp"
```

Invoke it as `/swe-day`.

### Codex

Save this one the same way. The only line that differs from
the block above is `install_target`.

```sh
set -eu
release=v0.1.8
install_target="$HOME/.agents/skills/swe-day"
install_parent="$(dirname "$install_target")"
mkdir -p "$install_parent"
install_tmp="$(mktemp -d "$install_parent/.swe-day.XXXXXX")"
install_stage="$install_tmp/package"
rollback_install() {
  if [ ! -e "$install_target" ]; then
    if [ -e "$install_tmp/previous" ]; then
      mv "$install_tmp/previous" "$install_target"
    fi
  fi
  rm -rf "$install_tmp"
}
trap rollback_install EXIT
git clone --quiet --depth 1 --branch "$release" \
  https://github.com/trycopilotai/swe-day \
  "$install_tmp/clone"
mkdir -p "$install_stage"
cp -R "$install_tmp/clone/skill/." "$install_stage/"
if [ -e "$install_target" ]; then
  mv "$install_target" "$install_tmp/previous"
fi
mv "$install_stage" "$install_target"
trap - EXIT
rm -rf "$install_tmp"
```

Invoke it as `$swe-day`.

Each block works in a temporary `.swe-day.*` directory
beside the target and removes it on exit. An existing
install at the target is replaced.

While it clones, `git` warns that the tag "is not a commit"
and notes a detached `HEAD`. Both are expected for a clone
pinned to an annotated tag.

Both blocks copy through `skill/`, a symlink to
`skills/swe-day/`, so the installed directory holds
`SKILL.md`, `agents/`, `references/` and `scripts/` as real
files. The repository also carries
`.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`
for a marketplace. No marketplace lists this skill, so no
marketplace install is described here.

## Evidence

`evidence/transcripts/lock-session.txt` is the captured run
behind the claim at the top of this file.
`scripts/record_session.py` wrote each `$` line and each
exit status; the rest is the two programs' output, with two
edits: the throwaway directory's path was replaced with
`/work`, and the recording machine's hostname with `host`.
The transcript itself carries no notice of that.
`evidence/demo-manifest.json` is where the edits are
declared, as `replace-capture-root` and `replace-hostname`,
beside the SHA-256 of both programs and of `SKILL.md`, the
commands, the interpreter, the date, and the SHA-256 of the
transcript.

`make check` runs the programs' own tests and a packaging
contract that ties this file, both plugin manifests, the
transcript and the demo images to each other.

### Agent invocations

Each client was started once, at v0.1.6, on one synthetic
fixture: a small Python repository and a separate ops
repository, with work item D01 (add a `--version` flag to
`cli.py`), no wrapper, and none of the nine delegated skills
supplied by the fixture or this package. This is one run per
client, not a benchmark.

- [`evidence/transcripts/2026-10-05-claude-code-invocation.txt`](evidence/transcripts/2026-10-05-claude-code-invocation.txt):
  Claude Code 2.1.220, invoked with `/swe-day`. It loaded the
  skill, stopped at step 0, took no lock, edited nothing, and
  asked whether to proceed without the missing skills. It
  named all nine as missing, but the session listed a skill
  named `code-review` that ships with Claude Code, so by step
  0's rule only eight were.
- [`evidence/transcripts/2026-10-05-codex-invocation.txt`](evidence/transcripts/2026-10-05-codex-invocation.txt):
  Codex 0.146.0, invoked with `$swe-day`. It stopped at step
  0 naming all nine, none of which the session listed, with
  no lock and no edits.

`scripts/render_invocation.py` wrote both from the clients'
raw output, which is not committed. It keeps each tool
call's name, arguments and status, not the tool's output,
and cuts any argument string longer than 300 characters,
marking the cut `...[N more characters]`. Its only other
edits are the ones `evidence/demo-manifest.json` declares
for each invocation: `replace-plugin-root`,
`replace-capture-root`, `replace-scratch-root`,
`replace-home` and `replace-hostname`. The manifest also
records each model, prompt and outcome and both files'
SHA-256.

**Known limits.** Step 0 resolves a delegated skill by name
alone, so an unrelated skill with the same name, such as
Claude Code's own `code-review`, counts as resolved.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Security

See [`SECURITY.md`](SECURITY.md).

## License

MIT. See [`LICENSE`](LICENSE).

## Not affiliated with GitHub or GitHub Copilot

The `trycopilotai` organisation name is not a claim of any
relationship with GitHub Copilot. This project is not
affiliated with, endorsed by, or sponsored by GitHub, Inc.
GitHub and GitHub Copilot are trademarks of GitHub, Inc.
