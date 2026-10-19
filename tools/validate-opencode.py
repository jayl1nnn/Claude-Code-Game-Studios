#!/usr/bin/env python3
"""Validate the generated OpenCode integration.

    uv run --with pyyaml python tools/validate-opencode.py

Checks the shapes OpenCode V2 expects, that every skill has a command, and that
no Claude-only frontmatter or tool names leaked into the generated files.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DST = ROOT / ".opencode"
FAILS: list[str] = []
WARNS: list[str] = []


def fail(message: str) -> None:
    FAILS.append(message)


def warn(message: str) -> None:
    WARNS.append(message)


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
    if not match:
        return {}, text
    return yaml.safe_load(match.group(1)) or {}, text[match.end():]


def strip_jsonc(text: str) -> str:
    # Comments in this file always occupy their own lines, so only strip those;
    # a naive `//` strip would eat the `https://` in the $schema value.
    return re.sub(r"^\s*//[^\n]*", "", text, flags=re.M)


def check_config() -> None:
    path = ROOT / "opencode.jsonc"
    if not path.exists():
        fail("opencode.jsonc is missing")
        return
    try:
        config = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        fail(f"opencode.jsonc does not parse: {exc}")
        return
    instructions = config.get("instructions", [])
    for entry in instructions:
        if not entry.startswith(("http://", "https://")) and not (ROOT / entry).exists():
            fail(f"instructions entry does not exist: {entry}")
    for rule in config.get("permissions", []):
        if set(rule) != {"action", "resource", "effect"}:
            fail(f"permission rule has unexpected keys: {rule}")
        if rule["effect"] not in {"allow", "ask", "deny"}:
            fail(f"permission rule has invalid effect: {rule}")
    for required in ("*.env", "*.env.*"):
        if not any(r["action"] == "read" and r["resource"] == required for r in config.get("permissions", [])):
            fail(f"missing .env read deny for {required}")


def check_agents() -> None:
    files = sorted((DST / "agents").glob("*.md"))
    if len(files) != 49:
        fail(f"expected 49 agents, found {len(files)}")
    allowed = {"description", "mode", "steps", "permissions", "color", "hidden"}
    allowed_actions = {
        "read", "glob", "grep", "edit", "shell", "subagent", "skill",
        "websearch", "webfetch", "question", "external_directory", "execute",
    }
    for path in files:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        extra = set(meta) - allowed
        if extra:
            fail(f"{path.name}: unexpected frontmatter keys {sorted(extra)}")
        if meta.get("mode") != "subagent":
            fail(f"{path.name}: mode must be subagent")
        if not isinstance(meta.get("steps"), int) or meta["steps"] <= 0:
            fail(f"{path.name}: steps must be a positive integer")
        if not meta.get("description"):
            fail(f"{path.name}: description is required for subagent discovery")
        for rule in meta.get("permissions", []):
            if rule.get("action") not in allowed_actions:
                fail(f"{path.name}: unknown permission action {rule.get('action')}")
            if rule.get("effect") not in {"allow", "ask", "deny"}:
                fail(f"{path.name}: invalid effect {rule.get('effect')}")
            if rule.get("resource") is None:
                fail(f"{path.name}: permission rule missing resource")
        if not body.strip():
            fail(f"{path.name}: empty system prompt")


def check_skills() -> dict[str, dict]:
    files = sorted((DST / "skills").glob("*/SKILL.md"))
    if len(files) != 74:
        fail(f"expected 74 skills, found {len(files)}")
    skills: dict[str, dict] = {}
    for path in files:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        skill_id = path.parent.name
        if skill_id in skills:
            fail(f"duplicate skill id {skill_id}")
        skills[skill_id] = meta
        if not meta.get("description"):
            fail(f"{skill_id}: skills need a description to be advertised")
        if not body.strip():
            fail(f"{skill_id}: empty skill body")
        for banned in ("allowed-tools", "user-invocable", "argument-hint", "model"):
            if banned in meta:
                fail(f"{skill_id}: Claude-only frontmatter field '{banned}' was not removed")
    return skills


def check_commands(skills: dict[str, dict]) -> None:
    files = sorted((DST / "commands").glob("*.md"))
    names = {p.stem for p in files}
    if len(files) != 74:
        fail(f"expected 74 commands, found {len(files)}")
    if "help" in names:
        fail("help command must be renamed to studio-help to keep the built-in /help")
    if "studio-help" not in names:
        fail("studio-help command is missing")
    for path in files:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        if not meta.get("description"):
            fail(f"command {path.stem}: missing description")
        if "$ARGUMENTS" not in body:
            fail(f"command {path.stem}: body must pass $ARGUMENTS")
    for skill_id in skills:
        expected = "studio-help" if skill_id == "help" else skill_id
        if expected not in names:
            fail(f"skill {skill_id}: no matching command {expected}")


def check_plugin() -> None:
    path = DST / "plugins" / "studio-hooks.js"
    if not path.exists():
        fail("studio-hooks.js is missing")
        return
    text = path.read_text(encoding="utf-8")
    for needle in (
        'export default',
        'ctx.session.hook("context"',
        'ctx.session.hook("compaction"',
        'ctx.permission.hook("evaluate"',
        'ctx.tool.hook("execute.after"',
        "session-start.sh",
    ):
        if needle not in text:
            fail(f"studio-hooks.js is missing {needle}")


BANNED = [
    "AskUserQuestion",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE.md",
    "`Agent`",
    "`Read`",
    "`Bash`",
]


def check_leftovers() -> None:
    # Docs and the meta skills legitimately discuss Claude Code fields; only
    # the generated agents, skills, and commands must be fully ported.
    roots = [DST / "agents", DST / "skills", DST / "commands"]
    for base in roots:
        for path in base.rglob("*.md"):
            rel = path.relative_to(DST).as_posix()
            text = path.read_text(encoding="utf-8")
            for banned in BANNED:
                if banned in text:
                    warn(f"{rel}: still contains '{banned}'")


def main() -> int:
    if not DST.exists():
        print("error: .opencode/ not found; run tools/port-to-opencode.py first", file=sys.stderr)
        return 1
    check_config()
    check_agents()
    skills = check_skills()
    check_commands(skills)
    check_plugin()
    check_leftovers()

    for message in WARNS:
        print(f"warn: {message}")
    for message in FAILS:
        print(f"FAIL: {message}")
    if FAILS:
        print(f"\n{len(FAILS)} failure(s)")
        return 1
    print(
        "ok: 49 agents, 74 skills, 74 commands, config, plugin"
        + (f" ({len(WARNS)} warning(s))" if WARNS else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
