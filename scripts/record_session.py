#!/usr/bin/env python3
"""Record the lock session again and refresh the evidence manifest.

    python3 scripts/record_session.py

The commands are the ones listed in ``evidence/demo-manifest.json``.
They run in a throwaway directory that holds a copy of ``skills/`` and
an empty git repository named ``ops-repo``. The transcript is what a
shell would show: each command line, the programs' output, and the exit
status. Two edits are made before it is written: the throwaway directory's
absolute path is replaced with ``/work``, and the recording machine's
hostname with ``host``.

The manifest's hashes of ``SKILL.md``, the two programs and the
transcript are then rewritten, with the date and the interpreter. Run
``make demo`` afterwards to rebuild the images.

Set ``RECORD_RAW_DIR`` to also keep the unedited capture and the
replaced path, outside the repository. The process id and timestamps
are published as recorded.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evidence" / "demo-manifest.json"
PLACEHOLDER = "/work"
HOSTNAME_LINE = '  "hostname": %s,'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(commands: list[str], workdir: Path, bindir: Path) -> str:
    define, steps = commands[0], commands[1:]
    environment = {"PATH": "%s:/usr/bin:/bin" % bindir, "PYTHONDONTWRITEBYTECODE": "1"}
    lines = ["$ " + define]
    for step in steps:
        result = subprocess.run(
            ["bash", "-c", define + "\n" + step],
            cwd=workdir,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines.append("$ " + step)
        lines.extend(result.stdout.splitlines())
        lines.append('$ echo "exit status: $?"')
        lines.append("exit status: %d" % result.returncode)
    return "\n".join(lines) + "\n"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commands = manifest["invocation"]["commands"]
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(scratch).resolve()
        workdir = base / "capture"
        bindir = base / "bin"
        bindir.mkdir()
        (bindir / "python3").symlink_to(sys.executable)
        shutil.copytree(
            ROOT / "skills",
            workdir / "skills",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        subprocess.run(
            ["git", "init", "--quiet", str(workdir / "ops-repo")], check=True
        )
        raw = record(commands, workdir, bindir)
        capture_root = str(workdir)

    raw_dir = os.environ.get("RECORD_RAW_DIR")
    if raw_dir:
        Path(raw_dir, "lock-session.source.txt").write_text(raw, encoding="utf-8")
        Path(raw_dir, "lock-session.capture-root.txt").write_text(
            capture_root + "\n", encoding="utf-8"
        )

    transcript = ROOT / manifest["output"]["path"]
    edited = raw.replace(capture_root, PLACEHOLDER).replace(
        HOSTNAME_LINE % json.dumps(socket.gethostname()),
        HOSTNAME_LINE % json.dumps("host"),
    )
    transcript.write_text(edited, encoding="utf-8")

    manifest["date"] = datetime.date.today().isoformat()
    manifest["invocation"]["interpreter"] = "Python " + platform.python_version()
    manifest["skill"]["sha256"] = sha256(ROOT / manifest["skill"]["path"])
    for program in manifest["programs"]:
        program["sha256"] = sha256(ROOT / program["path"])
    manifest["output"]["sha256"] = sha256(transcript)
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("wrote %s" % transcript.relative_to(ROOT))
    print("wrote %s" % MANIFEST.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
