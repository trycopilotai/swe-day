#!/usr/bin/env python3
"""Tests for the swe-day lock and its next-action banner.

Most tests run the two programs as a caller would, in a throwaway
repository. Three import the lock program to read its phase model:

    python3 tests/test_swe_day_next.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "swe-day" / "scripts"
)
LOCK_SCRIPT = SCRIPTS_DIR / "swe_day_lock.py"
NEXT_SCRIPT = SCRIPTS_DIR / "swe_day_next.py"
LOCK_PATH = ".agents/locks/swe-day.lock"
ME = ("--owner", "agent-a", "--session-id", "session-a")


class Harness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def lock(self, *args: str, lock_path: str | None = None):
        command = [sys.executable, str(LOCK_SCRIPT), "--repo", str(self.repo)]
        if lock_path is not None:
            command += ["--lock-path", lock_path]
        return subprocess.run(command + list(args), capture_output=True, text=True)

    def render(self, lock_path: str | None = None):
        command = [sys.executable, str(NEXT_SCRIPT), "--repo", str(self.repo)]
        if lock_path is not None:
            command += ["--lock-path", lock_path]
        return subprocess.run(command + ["render"], capture_output=True, text=True)

    def acquire(self, phase: str = "preflight", who=ME):
        return self.lock(
            "acquire",
            "--work-item",
            "D99",
            "--plan-path",
            "plans/test.plan.md",
            "--phase",
            phase,
            *who,
        )

    def set_phase(self, phase: str, *extra: str, who=ME):
        return self.lock("set-phase", "--phase", phase, *extra, *who)

    def status(self) -> dict:
        result = self.lock("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def clear(self, gate: str, who=ME):
        return self.lock("clear-gate", gate, *who)

    def metadata_path(self) -> Path:
        return self.repo / LOCK_PATH / "metadata.json"

    def metadata(self) -> dict:
        return json.loads(self.metadata_path().read_text(encoding="utf-8"))

    def banner(self) -> str:
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


class AcquireTests(Harness):
    def test_a_held_lock_refuses_a_second_acquire(self) -> None:
        self.assertEqual(self.acquire().returncode, 0)
        second = self.acquire(who=("--owner", "agent-b", "--session-id", "session-b"))
        self.assertEqual(second.returncode, 2)
        self.assertIn("swe-day lock already exists", second.stderr)
        self.assertEqual(self.metadata()["owner"], "agent-a")

    def test_acquire_without_a_session_is_refused(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(LOCK_SCRIPT),
                "--repo",
                str(self.repo),
                "acquire",
                "--owner",
                "agent-a",
                "--work-item",
                "D99",
                "--plan-path",
                "plans/test.plan.md",
            ],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--session-id", result.stderr)
        self.assertFalse((self.repo / LOCK_PATH).exists())

    def test_acquire_refuses_a_phase_outside_the_model(self) -> None:
        for phase in ("not-a-phase", "preflight\nOWNER: agent", ""):
            self.assertEqual(self.acquire(phase=phase).returncode, 4, phase)
            self.assertFalse((self.repo / LOCK_PATH).exists())

    def test_acquire_refuses_an_empty_owner_or_session(self) -> None:
        for who in (
            ("--owner", "", "--session-id", "session-a"),
            ("--owner", " ", "--session-id", "session-a"),
            ("--owner", "agent-a", "--session-id", " "),
        ):
            self.assertEqual(self.acquire(who=who).returncode, 2, who)
            self.assertFalse((self.repo / LOCK_PATH).exists())

    def test_no_lock_means_no_active_run(self) -> None:
        self.assertEqual(self.banner().strip(), "no active swe-day")


class LockPathTests(Harness):
    def test_a_lock_path_cannot_leave_the_repository(self) -> None:
        outside = self.base / "outside.lock"
        for escaping in ("../outside.lock", str(outside), "."):
            acquired = self.lock(
                "acquire",
                "--work-item",
                "D99",
                "--plan-path",
                "p.md",
                *ME,
                lock_path=escaping,
            )
            self.assertEqual(acquired.returncode, 5, escaping)
            self.assertEqual(self.render(lock_path=escaping).returncode, 5, escaping)
            released = self.lock("release", *ME, lock_path=escaping)
            self.assertEqual(released.returncode, 5, escaping)
        self.assertFalse(outside.exists())

    def test_release_does_not_follow_an_escaping_directory(self) -> None:
        victim = self.base / "victim"
        victim.mkdir()
        (victim / "metadata.json").write_text(
            json.dumps({"owner": "agent-a", "session_id": "session-a"}),
            encoding="utf-8",
        )
        (self.repo / "link.lock").symlink_to(victim)
        released = self.lock("release", *ME, lock_path="link.lock")
        self.assertEqual(released.returncode, 5)
        self.assertTrue((victim / "metadata.json").exists())

    def test_a_symlink_at_the_lock_path_is_refused(self) -> None:
        (self.repo / "inside").mkdir()
        (self.repo / "live.lock").symlink_to(self.repo / "inside")
        (self.repo / "dangling.lock").symlink_to(self.repo / "missing")
        for name in ("live.lock", "dangling.lock"):
            self.assertEqual(self.render(lock_path=name).returncode, 5, name)
            acquired = self.lock(
                "acquire",
                "--work-item",
                "D99",
                "--plan-path",
                "p.md",
                *ME,
                lock_path=name,
            )
            self.assertEqual(acquired.returncode, 5, name)
        self.assertFalse((self.repo / "missing").exists())
        self.assertEqual(list((self.repo / "inside").iterdir()), [])

    def test_a_lock_cannot_be_acquired_inside_another(self) -> None:
        self.acquire()
        inner = self.lock(
            "acquire",
            "--work-item",
            "D98",
            "--plan-path",
            "p.md",
            "--owner",
            "agent-b",
            "--session-id",
            "session-b",
            lock_path=LOCK_PATH + "/inner.lock",
        )
        self.assertEqual(inner.returncode, 5)
        self.assertFalse((self.repo / LOCK_PATH / "inner.lock").exists())

    def test_a_held_lock_cannot_be_named_as_the_repository(self) -> None:
        self.acquire()
        held = self.repo / LOCK_PATH
        (held / "sub").mkdir()
        for repo in (held, held / "sub"):
            inner = subprocess.run(
                [sys.executable, str(LOCK_SCRIPT), "--repo", str(repo)]
                + ["--lock-path", "inner.lock", "acquire"]
                + ["--work-item", "D98", "--plan-path", "p.md"]
                + ["--owner", "agent-b", "--session-id", "session-b"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(inner.returncode, 5, inner.stderr)
            self.assertFalse((repo / "inner.lock").exists())

    def test_release_leaves_a_directory_holding_anything_else(self) -> None:
        self.acquire()
        stray = self.repo / LOCK_PATH / "inner.lock"
        stray.mkdir()
        (stray / "metadata.json").write_text("{}", encoding="utf-8")
        released = self.lock("release", *ME)
        self.assertEqual(released.returncode, 6)
        self.assertIn("inner.lock", released.stderr)
        self.assertTrue((stray / "metadata.json").exists())
        self.assertTrue(self.metadata_path().exists())

    def test_a_path_that_cannot_be_resolved_is_refused(self) -> None:
        (self.repo / "loop").symlink_to(self.repo / "loop")
        for bad in ("loop/day.lock", "x" * 300 + "/day.lock"):
            for command in (("status",), ("release", *ME)):
                result = self.lock(*command, lock_path=bad)
                self.assertEqual(result.returncode, 5, bad)
                self.assertNotIn("Traceback", result.stderr)
            rendered = self.render(lock_path=bad)
            self.assertEqual(rendered.returncode, 5, bad)
            self.assertNotIn("Traceback", rendered.stderr)
        long_repo = subprocess.run(
            [sys.executable, str(LOCK_SCRIPT), "--repo", "y" * 300, "status"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(long_repo.returncode, 5)
        self.assertNotIn("Traceback", long_repo.stderr)

    def test_a_lock_that_cannot_be_examined_is_not_an_idle_run(self) -> None:
        import os

        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        self.acquire()
        lock_dir = self.repo / LOCK_PATH
        for sealed in (lock_dir, lock_dir.parent):
            sealed.chmod(0)
            try:
                banner = self.render()
                status = self.lock("status")
                acquired = self.acquire()
            finally:
                sealed.chmod(0o700)
            self.assertEqual(banner.returncode, 0, banner.stderr)
            self.assertIn("OWNER: human", banner.stdout)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["metadata"], "unreadable")
            self.assertIn(acquired.returncode, (2, 6))
            self.assertNotIn("Traceback", acquired.stderr)

    def test_a_repo_that_does_not_exist_is_refused(self) -> None:
        missing = self.base / "typo" / "repo"
        command = [sys.executable, str(LOCK_SCRIPT), "--repo", str(missing)]
        acquired = subprocess.run(
            command + ["acquire", "--work-item", "D99", "--plan-path", "p.md", *ME],
            capture_output=True,
            text=True,
        )
        self.assertEqual(acquired.returncode, 5)
        self.assertFalse((self.base / "typo").exists())

    def test_an_unrelated_metadata_file_is_not_a_lock(self) -> None:
        for directory in (self.repo, self.repo / ".agents"):
            directory.mkdir(exist_ok=True)
            (directory / "metadata.json").write_text(
                '{"name": "something else"}', encoding="utf-8"
            )
        self.assertEqual(self.acquire().returncode, 0)

    def test_a_lock_path_through_a_file_is_refused_without_a_traceback(self) -> None:
        (self.repo / "plain").write_text("", encoding="utf-8")
        acquired = self.lock(
            "acquire",
            "--work-item",
            "D99",
            "--plan-path",
            "p.md",
            *ME,
            lock_path="plain/x/day.lock",
        )
        self.assertEqual(acquired.returncode, 5)
        self.assertNotIn("Traceback", acquired.stderr)
        self.assertEqual(
            self.render(lock_path="plain/x/day.lock").stdout.strip(),
            "no active swe-day",
        )

    def test_release_deletes_nothing_when_a_leftover_is_a_directory(self) -> None:
        self.acquire()
        (self.repo / LOCK_PATH / ".metadata.json.tmp").mkdir()
        for _ in range(3):
            released = self.lock("release", *ME)
            self.assertEqual(released.returncode, 6)
            self.assertNotIn("Traceback", released.stderr)
            self.assertTrue(self.metadata_path().exists())

    def test_metadata_that_is_a_fifo_is_not_waited_on(self) -> None:
        import os

        self.acquire()
        self.metadata_path().unlink()
        os.mkfifo(self.metadata_path())
        commands = (
            [sys.executable, str(NEXT_SCRIPT), "--repo", str(self.repo), "render"],
            [sys.executable, str(LOCK_SCRIPT), "--repo", str(self.repo), "status"],
            [sys.executable, str(LOCK_SCRIPT), "--repo", str(self.repo)]
            + ["release", *ME],
            [sys.executable, str(LOCK_SCRIPT), "--repo", str(self.repo)]
            + ["--lock-path", LOCK_PATH + "/inner.lock", "status"],
        )
        for command in commands:
            done = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertNotIn("Traceback", done.stderr)
        self.assertIn("OWNER: human", self.banner())

    def test_metadata_that_is_a_symbolic_link_is_not_read(self) -> None:
        self.acquire()
        real = self.base / "elsewhere.json"
        real.write_text(self.metadata_path().read_text(encoding="utf-8"))
        self.metadata_path().unlink()
        self.metadata_path().symlink_to(real)
        self.assertEqual(self.set_phase("preflight").returncode, 6)
        self.assertIn("OWNER: human", self.banner())

    def test_metadata_write_does_not_follow_a_planted_link(self) -> None:
        self.acquire()
        target = self.base / "target.txt"
        target.write_text("untouched\n", encoding="utf-8")
        (self.repo / LOCK_PATH / ".metadata.json.tmp").symlink_to(target)
        self.assertEqual(self.set_phase("preflight").returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "untouched\n")


class OwnershipTests(Harness):
    def test_every_change_needs_owner_and_session(self) -> None:
        self.acquire()
        self.set_phase("prerequisite-gate")
        strangers = (
            ("--owner", "agent-b", "--session-id", "session-a"),
            ("--owner", "agent-a", "--session-id", "session-b"),
        )
        for who in strangers:
            self.assertEqual(self.set_phase("prerequisite-gate", who=who).returncode, 3)
            self.assertEqual(self.clear("prerequisite-go", who=who).returncode, 3)
            self.assertEqual(self.lock("release", *who).returncode, 3)
            self.assertEqual(self.lock("release", "--abandon", *who).returncode, 3)
        self.assertEqual(self.status()["pending_gate"], "prerequisite-go")
        self.assertEqual(self.metadata()["cleared_gates"], [])


class StateMachineTests(Harness):
    def test_the_model_matches_the_steps_document(self) -> None:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import swe_day_lock

        steps = (SCRIPTS_DIR.parent / "references" / "steps.md").read_text(
            encoding="utf-8"
        )
        documented = []
        for line in steps.splitlines():
            if not line.startswith("### "):
                continue
            owner = line.split("`owner: ")[1].split("`")[0]
            gate = None
            if "`gate: " in line:
                gate = line.split("`gate: ")[1].split("`")[0]
            documented.append((owner, gate))
        modelled = [(e["owner"], e["gate"]) for e in swe_day_lock.PHASE_MODEL]
        self.assertEqual(modelled[-1], ("agent", None))
        self.assertEqual(documented, modelled[:-1])

    def test_a_gated_phase_is_blocked_from_the_moment_it_is_recorded(self) -> None:
        self.acquire()
        self.assertEqual(self.status()["pending_gate"], None)
        self.assertEqual(self.set_phase("prerequisite-gate").returncode, 0)
        self.assertEqual(self.status()["pending_gate"], "prerequisite-go")
        self.assertEqual(self.status()["next_owner"], "human")
        moved = self.set_phase("learn-scope")
        self.assertEqual(moved.returncode, 4)
        self.assertIn("only clear-gate removes it", moved.stderr)
        self.assertEqual(self.metadata()["phase"], "prerequisite-gate")

    def test_only_the_pending_gate_can_be_cleared(self) -> None:
        self.acquire()
        self.assertEqual(self.clear("prerequisite-go").returncode, 4)
        self.set_phase("prerequisite-gate")
        for wrong in ("wrong-gate", "interview-complete", "final-buyoff"):
            self.assertEqual(self.clear(wrong).returncode, 4, wrong)
        self.assertEqual(self.metadata()["cleared_gates"], [])
        self.assertEqual(self.clear("prerequisite-go").returncode, 0)
        self.assertEqual(self.metadata()["cleared_gates"], ["prerequisite-go"])
        self.assertEqual(self.clear("prerequisite-go").returncode, 4)
        self.assertEqual(self.set_phase("learn-scope").returncode, 0)

    def test_set_phase_refuses_names_outside_the_model(self) -> None:
        self.acquire()
        for phase in ("not-a-phase", "learn-scope\nOWNER: agent", "LEARN-SCOPE"):
            self.assertEqual(self.set_phase(phase).returncode, 4, phase)
        self.assertEqual(self.metadata()["phase"], "preflight")

    def test_an_unknown_phase_is_refused_before_the_lock_is_read(self) -> None:
        self.assertEqual(self.set_phase("not-a-phase").returncode, 4)
        self.assertEqual(self.set_phase("preflight").returncode, 2)

    def test_set_phase_does_not_move_backward(self) -> None:
        self.acquire(phase="implement")
        self.set_phase("fix-loop")
        back = self.set_phase("implement")
        self.assertEqual(back.returncode, 4)
        self.assertIn("does not move backward", back.stderr)
        self.assertEqual(self.set_phase("preflight").returncode, 4)
        self.assertEqual(self.metadata()["phase"], "fix-loop")

    def test_set_phase_cannot_skip_a_gate_further_on(self) -> None:
        self.acquire()
        skipped = self.set_phase("learn-scope")
        self.assertEqual(skipped.returncode, 4)
        self.assertIn("'prerequisite-go' of phase prerequisite-gate", skipped.stderr)
        self.assertEqual(self.metadata()["phase"], "preflight")

    def test_set_phase_cannot_enter_or_pass_the_operators_phase(self) -> None:
        self.acquire(phase="consolidated-plan")
        self.clear("plan-review")
        for phase in ("final-buyoff", "implement", "done"):
            refused = self.set_phase(phase)
            self.assertEqual(refused.returncode, 4, phase)
        self.assertEqual(self.metadata()["phase"], "consolidated-plan")

    def test_a_run_acquired_mid_way_is_not_held_to_earlier_gates(self) -> None:
        self.acquire(phase="implement")
        self.assertEqual(self.set_phase("fix-loop").returncode, 0)
        self.assertEqual(self.set_phase("coverage").returncode, 0)
        self.assertEqual(self.set_phase("mutation").returncode, 4)

    def test_plan_review_to_buyoff_to_implementation(self) -> None:
        self.acquire(phase="consolidated-plan")
        self.assertIn("gated behind 'plan-review'", self.banner())

        self.assertEqual(self.clear("plan-review").returncode, 0)
        waiting = self.banner()
        self.assertIn("NEXT: operator gives the final go on the plan", waiting)
        self.assertIn("OWNER: human", waiting)
        self.assertIn("gated behind 'final-buyoff'", waiting)
        self.assertEqual(self.set_phase("implement").returncode, 4)

        self.assertEqual(self.clear("final-buyoff").returncode, 0)
        self.assertEqual(self.metadata()["phase"], "final-buyoff")
        go = self.banner()
        self.assertIn("NEXT: implement the plan in the impl worktree", go)
        self.assertIn("OWNER: agent", go)
        self.assertEqual(self.set_phase("implement").returncode, 0)

    def test_a_run_acquired_in_the_operators_phase_can_be_cleared(self) -> None:
        self.acquire(phase="final-buyoff")
        banner = self.banner()
        self.assertIn("NEXT: operator gives the final go on the plan", banner)
        self.assertIn("OWNER: human", banner)
        self.assertNotIn("implement the plan", banner)
        self.assertEqual(self.set_phase("implement").returncode, 4)
        self.assertEqual(self.clear("final-buyoff").returncode, 0)
        self.assertIn("OWNER: agent", self.banner())
        self.assertEqual(self.set_phase("implement").returncode, 0)

    def test_the_whole_day_runs_only_through_its_gates(self) -> None:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import swe_day_lock

        self.acquire()
        for entry in swe_day_lock.PHASE_MODEL[1:]:
            if entry["owner"] == "human":
                self.assertEqual(self.set_phase(entry["key"]).returncode, 4)
                self.assertEqual(self.clear(entry["gate"]).returncode, 0)
                continue
            self.assertEqual(self.set_phase(entry["key"]).returncode, 0, entry["key"])
            if entry["gate"]:
                self.assertIn("OWNER: human", self.banner())
                self.assertEqual(self.clear(entry["gate"]).returncode, 0)
        self.assertEqual(self.metadata()["phase"], "done")
        self.assertIn("NEXT: release the lock; swe-day complete", self.banner())
        self.assertEqual(self.lock("release", *ME).returncode, 0)


class ReleaseTests(Harness):
    def test_release_refuses_while_a_gate_is_pending(self) -> None:
        self.acquire()
        self.set_phase("prerequisite-gate")
        refused = self.lock("release", *ME)
        self.assertEqual(refused.returncode, 4)
        self.assertIn("gate 'prerequisite-go' is pending", refused.stderr)
        self.assertTrue((self.repo / LOCK_PATH).exists())
        self.assertEqual(self.lock("release", "--abandon", *ME).returncode, 0)
        self.assertFalse((self.repo / LOCK_PATH).exists())

    def test_release_refuses_before_the_operators_phase(self) -> None:
        self.acquire(phase="consolidated-plan")
        self.clear("plan-review")
        self.assertEqual(self.lock("release", *ME).returncode, 4)

    def test_release_with_no_gate_pending(self) -> None:
        self.acquire()
        self.assertEqual(self.lock("release", *ME).returncode, 0)
        self.assertFalse((self.repo / LOCK_PATH).exists())
        again = self.lock("release", *ME)
        self.assertEqual(again.returncode, 0)
        self.assertEqual(json.loads(again.stdout)["reason"], "not_locked")


class BannerTests(Harness):
    def test_an_agent_phase_with_no_gate_is_the_agents(self) -> None:
        self.acquire()
        banner = self.banner()
        self.assertIn("phase preflight", banner)
        self.assertIn("OWNER: agent · BLOCKED-ON: none", banner)
        self.assertEqual(len(banner.splitlines()), 1)

    def test_a_pending_gate_offers_no_agent_action(self) -> None:
        self.acquire()
        self.set_phase("prerequisite-gate")
        banner = self.banner()
        self.assertIn("NEXT: operator clears gate 'prerequisite-go'", banner)
        self.assertIn("OWNER: human · BLOCKED-ON: operator", banner)
        self.assertNotIn("learn the work item's scope", banner)
        self.assertEqual(len(banner.splitlines()), 2)

    def test_the_banner_and_the_lock_agree_at_every_phase(self) -> None:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import swe_day_lock

        for entry in swe_day_lock.PHASE_MODEL:
            with self.subTest(phase=entry["key"]):
                self.acquire(phase=entry["key"])
                status = self.status()
                banner = self.banner()
                self.assertIn("OWNER: %s ·" % status["next_owner"], banner)
                blocked = status["pending_gate"] is not None
                self.assertEqual(blocked, status["next_owner"] == "human")
                self.assertEqual(blocked, "gated behind" in banner)
                index = swe_day_lock.PHASE_KEYS.index(entry["key"])
                if index + 1 < len(swe_day_lock.PHASE_KEYS):
                    following = swe_day_lock.PHASE_KEYS[index + 1]
                    moved = self.set_phase(following).returncode
                    self.assertEqual(moved, 4 if blocked else 0)
                self.lock("release", "--abandon", *ME)

    def test_a_note_that_cannot_be_encoded_still_renders(self) -> None:
        self.acquire()
        noted = subprocess.run(
            [sys.executable, str(LOCK_SCRIPT), "--repo", str(self.repo)]
            + ["set-phase", "--phase", "preflight", "--note", "caf\udcff", *ME],
            capture_output=True,
        )
        self.assertEqual(noted.returncode, 0, noted.stderr)
        for encoding in ("utf-8", "ascii"):
            rendered = subprocess.run(
                [sys.executable, str(NEXT_SCRIPT), "--repo", str(self.repo), "render"],
                capture_output=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": encoding},
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn(b"swe-day ACTIVE", rendered.stdout)
            self.assertEqual(len(rendered.stdout.splitlines()), 2)

    def test_rendering_writes_nothing_beside_the_programs(self) -> None:
        import shutil

        copy = self.base / "scripts"
        shutil.copytree(
            SCRIPTS_DIR, copy, ignore=shutil.ignore_patterns("__pycache__")
        )
        before = sorted(path.name for path in copy.iterdir())
        self.acquire()
        rendered = subprocess.run(
            [sys.executable, str(copy / "swe_day_next.py")]
            + ["--repo", str(self.repo), "render"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertIn("swe-day ACTIVE", rendered.stdout)
        self.assertEqual(sorted(path.name for path in copy.iterdir()), before)

    def test_a_note_stays_on_one_line(self) -> None:
        self.acquire()
        self.set_phase("preflight", "--note", "first\nsecond")
        lines = self.banner().splitlines()
        self.assertEqual(lines[1], "  note: first second")
        self.set_phase("preflight", "--note", "up\x1b[1Aand over")
        self.assertNotIn("\x1b", self.banner())
        self.assertEqual(len(lines), 2)
        self.set_phase("preflight")
        self.assertEqual(len(self.banner().splitlines()), 1)


class UnreadableLockTests(Harness):
    def damaged(self, content: str | None) -> None:
        self.acquire()
        if content is None:
            self.metadata_path().unlink()
        else:
            self.metadata_path().write_text(content, encoding="utf-8")

    def altered(self, **changes) -> str:
        record = {
            "owner": "agent-a",
            "session_id": "session-a",
            "phase": "preflight",
            "cleared_gates": [],
        }
        record.update(changes)
        return json.dumps(record)

    def test_a_lock_without_usable_metadata_is_still_an_active_run(self) -> None:
        cases = (
            None,
            "{not json",
            "[]",
            "\xff",
            self.altered(phase=[]),
            self.altered(phase="not-a-phase"),
            self.altered(phase="preflight\nOWNER: agent"),
            self.altered(cleared_gates="prerequisite-go"),
            self.altered(cleared_gates=["made-up-gate"]),
            self.altered(cleared_gates=[["prerequisite-go"]]),
            self.altered(cleared_gates=["prerequisite-go"]),
            self.altered(
                phase="consolidated-plan",
                cleared_gates=["plan-review", "final-buyoff"],
            ),
            self.altered(
                phase="prerequisite-gate",
                cleared_gates=["prerequisite-go", "prerequisite-go"],
            ),
            "[" * 5000 + "]" * 5000,
            self.altered(session_id=None),
            self.altered(owner=7),
        )
        for content in cases:
            with self.subTest(content=content):
                self.damaged(content)
                banner = self.banner()
                self.assertEqual(len(banner.splitlines()), 1)
                self.assertIn("swe-day ACTIVE", banner)
                self.assertIn("OWNER: human · BLOCKED-ON: operator", banner)
                status = self.lock("status")
                self.assertEqual(status.returncode, 0)
                self.assertEqual(status.stderr, "")
                self.assertEqual(json.loads(status.stdout)["metadata"], "unreadable")
                self.assertEqual(self.acquire().returncode, 2)
                self.assertEqual(self.set_phase("preflight").returncode, 6)
                self.assertEqual(self.clear("prerequisite-go").returncode, 6)
                for extra in ((), ("--abandon",)):
                    released = self.lock("release", *extra, *ME)
                    self.assertEqual(released.returncode, 6)
                    self.assertIn("needs human review", released.stderr)
                    self.assertNotIn("Traceback", released.stderr)
                self.assertTrue((self.repo / LOCK_PATH).exists())
                self.tearDown()
                self.setUp()

    def test_odd_but_harmless_fields_do_not_break_the_banner(self) -> None:
        self.acquire()
        record = self.metadata()
        record["acquired_at"] = "2026-10-04T00:00:00"
        record["phase_note"] = ["a", "b"]
        self.metadata_path().write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.lock("status").stderr, "")
        self.assertEqual(len(self.banner().splitlines()), 2)

    def test_a_file_where_the_lock_should_be_is_not_an_idle_run(self) -> None:
        (self.repo / ".agents" / "locks").mkdir(parents=True)
        (self.repo / LOCK_PATH).write_text("", encoding="utf-8")
        self.assertIn("OWNER: human", self.banner())
        self.assertEqual(self.acquire().returncode, 2)
        self.assertEqual(self.lock("release", *ME).returncode, 6)


if __name__ == "__main__":
    unittest.main()
