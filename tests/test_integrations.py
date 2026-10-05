#!/usr/bin/env python3
"""The packaging contract.

Facts this repository states in more than one place are
pinned here where a script can compare them: the name and
version, the claim and the transcript behind it, the demo
images, the install blocks, and the evidence hashes.

Runs offline with the standard library and `git`:

    python3 tests/test_integrations.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "swe-day"
PACKAGE = ROOT / "skills" / NAME
LOCK = PACKAGE / "scripts" / "swe_day_lock.py"
BANNER = PACKAGE / "scripts" / "swe_day_next.py"
SKILL = PACKAGE / "SKILL.md"
README = ROOT / "README.md"
TRANSCRIPT = ROOT / "evidence" / "transcripts" / "lock-session.txt"
MANIFEST = ROOT / "evidence" / "demo-manifest.json"
CLAIM = "swe_day_lock.py refuses to acquire a lock that is held."
REFUSAL = "swe-day lock already exists; stale locks require human review."
REPOSITORY = "https://github.com/trycopilotai/" + NAME


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(product: str) -> dict:
    return json.loads(read(ROOT / product / "plugin.json"))


def frontmatter(text: str) -> dict:
    """The `key: value` pairs between the two `---` lines."""
    lines = text.splitlines()
    if lines[0] != "---":
        raise AssertionError("SKILL.md does not open with frontmatter")
    end = lines.index("---", 1)
    fields: dict = {}
    key = None
    for line in lines[1:end]:
        match = re.match(r"^([a-z_-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            fields[key] = match.group(2).strip()
            continue
        if key is None or not line.startswith(" "):
            raise AssertionError("unexpected frontmatter line: " + line)
        fields[key] = (fields[key] + " " + line.strip()).strip()
    for name, value in fields.items():
        if value.startswith(">-"):
            fields[name] = value[2:].strip()
    return fields


def interface_yaml(text: str) -> dict:
    """The quoted scalars under `interface:` in agents/openai.yaml."""
    lines = text.splitlines()
    if lines[0] != "interface:":
        raise AssertionError("openai.yaml does not start with interface:")
    fields: dict = {}
    key = None
    for line in lines[1:]:
        match = re.match(r"^  ([a-z_]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            fields[key] = match.group(2).strip()
            continue
        fields[key] = (fields[key] + " " + line.strip()).strip()
    for name, value in fields.items():
        if not (value.startswith('"') and value.endswith('"')):
            raise AssertionError(name + " is not a double-quoted scalar")
        fields[name] = value[1:-1]
    return fields


def install_blocks() -> list:
    return re.findall(r"```sh\nset -eu\n(.*?)```", read(README), flags=re.S)


class LayoutTest(unittest.TestCase):
    def test_skill_is_a_symlink_into_the_canonical_package(self) -> None:
        link = ROOT / "skill"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(str(link)), "skills/" + NAME)
        self.assertFalse(PACKAGE.is_symlink())

    def test_package_holds_what_the_readme_says_it_installs(self) -> None:
        for relative in (
            "SKILL.md",
            "agents/openai.yaml",
            "references/steps.md",
            "references/summary.md",
            "scripts/swe_day_lock.py",
            "scripts/swe_day_next.py",
        ):
            self.assertTrue((PACKAGE / relative).is_file(), relative)

    def test_history_has_no_co_author_trailer(self) -> None:
        messages = git("log", "--all", "--format=%B")
        self.assertNotIn("co-authored-by", messages.lower())


class SkillTest(unittest.TestCase):
    def test_frontmatter_is_name_and_description_only(self) -> None:
        fields = frontmatter(read(SKILL))
        self.assertEqual(sorted(fields), ["description", "name"])
        self.assertEqual(fields["name"], NAME)
        self.assertRegex(NAME, r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(NAME), 64)
        self.assertTrue(fields["description"])
        self.assertLessEqual(len(fields["description"]), 1024)

    def test_skill_stays_under_five_hundred_lines(self) -> None:
        self.assertLess(len(read(SKILL).splitlines()), 500)

    def test_files_the_skill_points_at_exist(self) -> None:
        text = read(SKILL)
        for relative in (
            "scripts/swe_day_lock.py",
            "scripts/swe_day_next.py",
            "references/steps.md",
        ):
            self.assertIn(relative, text)
            self.assertTrue((PACKAGE / relative).is_file(), relative)

    def test_helper_invocations_name_the_skill_directory(self) -> None:
        # The agent runs from the target repository, so a bare
        # `python3 scripts/...` cannot find the helpers.
        documents = [SKILL, *sorted((PACKAGE / "references").glob("*.md"))]
        calls = []
        for document in documents:
            for call in re.findall(r"python3 (\S*scripts/swe_day_\w+\.py)", read(document)):
                calls.append(call)
                self.assertEqual(
                    call.split("scripts/")[0], "<skill-dir>/", document.name
                )
        self.assertGreaterEqual(len(calls), 4)
        self.assertIn("`<skill-dir>`", read(SKILL))

    def test_step_zero_and_readme_name_the_same_delegated_skills(self) -> None:
        # Step 0 names each delegated skill once; that name is the
        # value an operator passes to `acquire --proceed-without`.
        steps = read(PACKAGE / "references" / "steps.md")
        preflight = steps.split("### 0. ", 1)[1].split("### 1. ", 1)[0]
        in_steps = re.findall(r"^\s*\| `([a-z-]+)` \| steps? ", preflight, flags=re.M)
        section = read(README).split("## Not included", 1)[1].split("\n## ", 1)[0]
        in_readme = re.findall(r"^- `([a-z-]+)`: ", section, flags=re.M)
        self.assertEqual(len(in_steps), 9)
        self.assertEqual(len(set(in_steps)), len(in_steps))
        self.assertEqual(sorted(in_steps), sorted(in_readme))
        self.assertIn("nine", " ".join(read(SKILL).split()))
        self.assertNotIn("first eight", read(README))

    def test_step_zero_lists_every_step_that_names_a_delegated_skill(self) -> None:
        # A step that calls a skill by name must appear in that
        # skill's row, or a missing skill leaves it out of NOT-RUN.
        steps = read(PACKAGE / "references" / "steps.md")
        sections = re.split(r"^### (\d+)\. ", steps, flags=re.M)
        bodies = dict(zip(sections[1::2], sections[2::2]))
        rows = re.findall(r"^\s*\| `([a-z-]+)` \| steps? ([\d, ]+) \|", bodies["0"], flags=re.M)
        aliases = {"plan-commits": "planCommits"}
        checked = 0
        for name, served in rows:
            if name == "handoff":
                continue  # also the name of the handoff document
            listed = {step.strip() for step in served.split(",")}
            for token in (name, aliases.get(name, name)):
                pattern = r"(?<![(\w-])%s(?![\w-])" % re.escape(token)
                for number, body in bodies.items():
                    if number != "0" and re.search(pattern, body):
                        self.assertIn(number, listed, name)
                        checked += 1
        self.assertGreaterEqual(checked, 6)

    def test_docs_say_where_the_default_lock_goes(self) -> None:
        steps = read(PACKAGE / "references" / "steps.md")
        preflight = " ".join(steps.split("### 0. ", 1)[1].split("### 1. ", 1)[0].split())
        self.assertIn("`--repo` is `ops_repo` and `--lock-path` is omitted", preflight)
        self.assertIn("it prints `lock_path` and writes nothing", preflight)
        self.assertIn("Never commit it", preflight)
        for document in (README, SKILL, PACKAGE / "references" / "summary.md"):
            text = " ".join(read(document).split())
            self.assertIn("default path inside `ops_repo`", text, document.name)
            self.assertNotIn("default path in the target repository", text, document.name)

    def test_status_reports_the_default_lock_path_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-B", str(LOCK), "--repo", directory, "status"],
                capture_output=True,
                text=True,
                check=True,
            )
            status = json.loads(result.stdout)
            self.assertFalse(status["locked"])
            self.assertTrue(status["lock_path"].endswith("swe-day.lock"))
            self.assertEqual(os.listdir(directory), [])

    def test_step_zero_always_takes_the_lock_and_stops_on_a_missing_skill(
        self,
    ) -> None:
        steps = read(PACKAGE / "references" / "steps.md")
        preflight = steps.split("### 0. ", 1)[1].split("### 1. ", 1)[0]
        flat = " ".join(preflight.split())
        self.assertIn("`--lock-path` is omitted, so the script uses its default", flat)
        self.assertIn("--proceed-without", flat)
        self.assertIn("acquire nothing, edit nothing", flat)
        self.assertIn("A run that stops in step 0 writes nothing and takes no lock", flat)
        skill = " ".join(read(SKILL).split())
        self.assertIn("lock script's default path inside `ops_repo`", skill)
        # A run that stops at the preflight takes no lock, so no
        # document may say that every run holds or takes it.
        documents = [README, SKILL, *sorted((PACKAGE / "references").glob("*.md"))]
        for document in documents:
            text = " ".join(read(document).split())
            self.assertIsNone(
                re.search(r"[Ee]very run (holds|takes|acquires)", text), document.name
            )
            self.assertNotIn("on every run:", text, document.name)
        for conditional in (
            "If `ops_repo_lock` is bound",
            "When bound, acquire it",
            "If the wrapper binds `ops_repo_lock`",
            "manages an optional",
        ):
            self.assertNotIn(conditional, flat + skill)


class ManifestTest(unittest.TestCase):
    def test_both_manifests_agree(self) -> None:
        claude = manifest(".claude-plugin")
        codex = manifest(".codex-plugin")
        for field in (
            "name",
            "version",
            "description",
            "license",
            "homepage",
            "repository",
            "skills",
        ):
            self.assertEqual(claude[field], codex[field], field)
        self.assertEqual(claude["name"], NAME)
        self.assertEqual(claude["skills"], "./skills/")
        self.assertEqual(claude["repository"], REPOSITORY)
        self.assertEqual(claude["license"], "MIT")
        self.assertRegex(claude["version"], r"^\d+\.\d+\.\d+$")

    def test_a_release_tag_on_head_is_the_manifest_version(self) -> None:
        tags = git("tag", "--points-at", "HEAD").split()
        releases = [tag for tag in tags if tag.startswith("v")]
        if not releases:
            self.skipTest("HEAD carries no release tag")
        self.assertEqual(releases, ["v" + manifest(".claude-plugin")["version"]])

    def test_codex_interface_matches_the_agent_file(self) -> None:
        interface = manifest(".codex-plugin")["interface"]
        for field in (
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
            "websiteURL",
        ):
            self.assertTrue(interface.get(field), field)
        prompts = interface["defaultPrompt"]
        self.assertEqual(len(prompts), 1)
        self.assertIn("$" + NAME, prompts[0])
        agent = interface_yaml(read(PACKAGE / "agents" / "openai.yaml"))
        self.assertEqual(agent["default_prompt"], prompts[0])
        self.assertEqual(agent["display_name"], interface["displayName"])
        self.assertEqual(agent["short_description"], interface["shortDescription"])


class ReadmeTest(unittest.TestCase):
    def test_claim_is_on_its_own_line(self) -> None:
        self.assertIn(CLAIM, read(README).splitlines())

    def test_transcript_shows_the_refused_second_acquire(self) -> None:
        lines = read(TRANSCRIPT).splitlines()
        acquires = [i for i, line in enumerate(lines) if line.startswith("$ lock acquire")]
        self.assertEqual(len(acquires), 2)
        second = lines[acquires[1] :]
        self.assertEqual(second[1], REFUSAL)
        status = second.index('$ echo "exit status: $?"')
        self.assertEqual(second[status + 1], "exit status: 2")
        self.assertIn(REFUSAL, read(LOCK))

    def test_each_install_block_pins_the_manifest_version(self) -> None:
        version = manifest(".claude-plugin")["version"]
        blocks = install_blocks()
        self.assertEqual(len(blocks), 2)
        roots = []
        for block in blocks:
            self.assertEqual(
                re.findall(r"^release=(\S+)$", block, flags=re.M),
                ["v" + version],
            )
            self.assertIn(REPOSITORY + " \\\n", block)
            self.assertIn('--branch "$release"', block)
            target = re.findall(r'^install_target="\$HOME/(\S+)"$', block, flags=re.M)
            self.assertEqual(len(target), 1)
            roots.append(target[0])
        self.assertEqual(
            sorted(roots),
            [".agents/skills/" + NAME, ".claude/skills/" + NAME],
        )

    def test_relative_links_resolve(self) -> None:
        targets = re.findall(r"\]\(([^)#]+)\)", read(README))
        self.assertTrue(targets)
        for target in targets:
            if target.startswith("http"):
                continue
            self.assertTrue((ROOT / target).exists(), target)

    def test_readme_says_what_was_not_measured(self) -> None:
        text = " ".join(read(README).split())
        self.assertIn("No agent ran a SWE day", text)
        self.assertIn("has not been measured", text)

    def test_demo_is_offered_with_a_reduced_motion_poster(self) -> None:
        text = read(README)
        picture = re.search(r"<picture>(.*?)</picture>", text, flags=re.S)
        self.assertIsNotNone(picture)
        body = picture.group(1)
        self.assertIn('media="(prefers-reduced-motion: reduce)"', body)
        self.assertIn('srcset="assets/poster.svg"', body)
        self.assertIn('src="assets/demo.svg"', body)


class EvidenceTest(unittest.TestCase):
    def test_manifest_hashes_match_the_files(self) -> None:
        record = json.loads(read(MANIFEST))
        self.assertEqual(record["skill"]["sha256"], sha256(SKILL))
        programs = {item["path"]: item["sha256"] for item in record["programs"]}
        self.assertEqual(
            programs,
            {
                str(LOCK.relative_to(ROOT)): sha256(LOCK),
                str(BANNER.relative_to(ROOT)): sha256(BANNER),
            },
        )
        self.assertEqual(record["output"]["sha256"], sha256(TRANSCRIPT))
        self.assertIs(record["output"]["edited"], True)
        self.assertTrue(record["output"]["transforms"])
        self.assertIs(record["agent"]["invoked_the_skill"], False)

    def test_manifest_commands_are_the_ones_in_the_transcript(self) -> None:
        record = json.loads(read(MANIFEST))
        commands = [
            line[2:]
            for line in read(TRANSCRIPT).splitlines()
            if line.startswith("$ ") and not line.startswith("$ echo")
        ]
        self.assertEqual(record["invocation"]["commands"], commands)

    def test_readme_names_every_edit_the_manifest_declares(self) -> None:
        record = json.loads(read(MANIFEST))
        names = [entry["name"] for entry in record["output"]["transforms"]]
        self.assertEqual(names, ["replace-capture-root", "replace-hostname"])
        for name in names:
            self.assertIn("`%s`" % name, read(README))
        hostnames = [
            line for line in read(TRANSCRIPT).splitlines() if '"hostname"' in line
        ]
        self.assertTrue(hostnames)
        self.assertEqual(set(hostnames), {'  "hostname": "host",'})

    def test_a_second_acquire_is_refused_as_the_transcript_shows(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            subprocess.run(["git", "init", "-q", raw], check=True)
            command = [
                sys.executable,
                str(LOCK),
                "--repo",
                raw,
                "--lock-path",
                "locks/day.lock",
                "acquire",
                "--work-item",
                "D01",
                "--plan-path",
                "plans/d01.md",
            ]
            first = subprocess.run(
                command + ["--owner", "alex", "--session-id", "s1"],
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                command + ["--owner", "blake", "--session-id", "s2"],
                capture_output=True,
                text=True,
            )
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 2)
        self.assertIn(REFUSAL, (second.stdout + second.stderr).splitlines())

    def test_transcript_carries_no_capture_path(self) -> None:
        text = read(TRANSCRIPT)
        self.assertIn('"repo": "/work/ops-repo"', text)
        self.assertNotIn("/var/folders", text)
        self.assertNotIn("/tmp", text)


class DemoTest(unittest.TestCase):
    def test_images_agree_with_the_transcript(self) -> None:
        verifier = load(ROOT / "scripts" / "verify_demo.py", "verify_demo")
        generator = verifier.load_generator()
        self.assertEqual(verifier.problems_in(generator, read(TRANSCRIPT)), [])


class SocialPreviewTest(unittest.TestCase):
    def test_preview_is_the_size_github_expects(self) -> None:
        header = (ROOT / "assets" / "social-preview.png").read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", header[16:24]), (1280, 640))

    def test_stamp_binds_the_source_and_the_render(self) -> None:
        recorded = {}
        for line in read(ROOT / "assets" / "social-preview.sha256").splitlines():
            value, name = line.split()
            recorded[name] = value
        for name in ("social-preview.html", "social-preview.png"):
            self.assertEqual(recorded[name], sha256(ROOT / "assets" / name), name)

    def test_preview_source_carries_the_claim(self) -> None:
        text = " ".join(read(ROOT / "assets" / "social-preview.html").split())
        self.assertIn(CLAIM, text)


class SupportFilesTest(unittest.TestCase):
    def test_license_is_mit(self) -> None:
        self.assertTrue(read(ROOT / "LICENSE").startswith("MIT License\n"))

    def test_security_names_this_repository_for_reports(self) -> None:
        self.assertIn(
            REPOSITORY + "/security/advisories/new",
            read(ROOT / "SECURITY.md"),
        )

    def test_contributing_names_the_check_command(self) -> None:
        self.assertIn("make check", read(ROOT / "CONTRIBUTING.md"))


if __name__ == "__main__":
    unittest.main()
