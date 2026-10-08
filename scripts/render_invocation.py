#!/usr/bin/env python3
"""Render an agent invocation's raw JSON-lines output as text.

    python3 scripts/render_invocation.py --client claude-code \
        --prompt prompt.txt --root <fixture> --plugin-root <clone> \
        --home <home> --hostname <name> raw.jsonl > transcript.txt

Writes a header (Claude Code: the client version and model from
the init event; Codex: the client name only), the prompt with
trailing newlines dropped, every tool call, each call's status
where the raw output records it, and the final message. A call
is written as its name and its arguments re-serialised as JSON
with sorted keys, each argument string cut at LIMIT characters
and marked "...[N more characters]". For Codex, a completed
item that is not a command, a message or reasoning is written
as its type and all its fields. Left out: tool output, the
agent's reasoning, every message but the final one, and every
other event. Once the text is assembled, after the cuts, these
replacements run over all of it, prompt and final message
included, in this order: each --plugin-root (the directory the
client loaded the skills from) becomes /plugin, the fixture's
absolute path /work, a client scratch directory
/private/tmp/claude-<uid>/<slug> /scratch, the home directory
~, and each --hostname host. The plugin, fixture and home
paths are replaced only where no letter, digit, underscore, dot
or hyphen comes before them and a slash, backslash, quote,
backtick, whitespace or the end of the text comes after them;
the scratch directory wherever it occurs; a hostname only where
no letter, digit, underscore, dot or hyphen comes before it and
no letter, digit, underscore, hyphen, or dot followed by a
letter, digit or underscore, comes after it.
Standard library only; output depends only on the inputs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

LIMIT = 300
# A path or name ends at a separator, a quote, whitespace or the end.
END = r"(?=[/\\\s\"'`]|$)"
SCRATCH = re.compile(r"/private/tmp/claude-[0-9]+/[^/\s\"'`]+" + END)


def prefix(text: str, path: str, replacement: str) -> str:
    """Replace `path` where it is a whole path prefix."""
    pattern = r"(?<![\w.-])" + re.escape(path.rstrip("/")) + END
    return re.sub(pattern, lambda match: replacement, text)


def cut(value):
    if isinstance(value, str):
        if len(value) > LIMIT:
            return value[:LIMIT] + "...[%d more characters]" % (len(value) - LIMIT)
        return value
    if isinstance(value, dict):
        return {key: cut(item) for key, item in value.items()}
    if isinstance(value, list):
        return [cut(item) for item in value]
    return value


def arguments(value) -> str:
    return json.dumps(cut(value), ensure_ascii=False, sort_keys=True)


def claude_code(events):
    calls, final, model, version = [], None, None, None
    results = {}
    for event in events:
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            model, version = event.get("model"), event.get("claude_code_version")
        elif kind in ("assistant", "user"):
            content = event["message"].get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use":
                    calls.append((block["id"], block["name"], block.get("input")))
                elif block.get("type") == "tool_result":
                    results[block["tool_use_id"]] = (
                        "error" if block.get("is_error") else "ok"
                    )
        elif kind == "result":
            final = event.get("result")
    header = ["client: Claude Code %s" % version, "model: %s" % model]
    lines = [
        "%s %s\n  status: %s" % (name, arguments(given), results.get(ident, "unknown"))
        for ident, name, given in calls
    ]
    return header, lines, final


def codex(events):
    lines, final = [], None
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event["item"]
        if item.get("type") == "command_execution":
            lines.append(
                "command_execution %s\n  status: %s, exit %s"
                % (arguments({"command": item["command"]}), item.get("status"), item.get("exit_code"))
            )
        elif item.get("type") == "agent_message":
            final = item["text"]
        elif item.get("type") not in ("reasoning",):
            lines.append("%s %s" % (item.get("type"), arguments(item)))
    return ["client: Codex"], lines, final


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", choices=("claude-code", "codex"), required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--plugin-root", action="append", default=[])
    parser.add_argument("--home", required=True)
    parser.add_argument("--hostname", action="append", default=[])
    parser.add_argument("raw")
    options = parser.parse_args(argv)
    with open(options.raw, encoding="utf-8") as stream:
        events = [json.loads(line) for line in stream if line.strip()]
    with open(options.prompt, encoding="utf-8") as stream:
        prompt = stream.read().rstrip("\n")
    render = claude_code if options.client == "claude-code" else codex
    header, lines, final = render(events)
    text = "\n".join(
        header
        + ["", "## prompt", "", prompt, "", "## tool calls", ""]
        + ["%d. %s" % (number, line) for number, line in enumerate(lines, 1)]
        + ["", "## final message", "", final if final is not None else "(none)", ""]
    )
    for path in options.plugin_root:
        text = prefix(text, path, "/plugin")
    text = prefix(text, options.root, "/work")
    text = SCRATCH.sub(lambda match: "/scratch", text)
    text = prefix(text, options.home, "~")
    for name in sorted(options.hostname, key=len, reverse=True):
        text = re.sub(
            r"(?<![\w.-])" + re.escape(name) + r"(?![\w-]|\.\w)",
            lambda match: "host",
            text,
        )
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
