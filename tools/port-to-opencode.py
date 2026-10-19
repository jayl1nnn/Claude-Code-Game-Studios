#!/usr/bin/env python3
"""Port the Claude Code Game Studios integration to OpenCode V2.

The original `.claude/` tree is left untouched so the same checkout still works
with Claude Code. This script generates an OpenCode-native tree in `.opencode/`
plus the root `AGENTS.md` and `opencode.jsonc`.

Run from the repository root:

    uv run --with pyyaml python tools/port-to-opencode.py

Re-running regenerates `.opencode/`; edit this script, not the generated files,
when the upstream `.claude/` definitions change.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".claude"
DST = ROOT / ".opencode"
BRAND = "Claude Code Game Studios"
MARKER = ".ported-from-claude"

# ---------------------------------------------------------------------------
# Text conversion
# ---------------------------------------------------------------------------

TOOL_RENAMES = [
    ("`AskUserQuestion`", "`question`"),
    ("AskUserQuestion", "question"),
    ("`Task` tool", "`subagent` tool"),
    ("Task tool", "subagent tool"),
    ("`Agent`", "`subagent`"),
    ("Agent tool", "subagent tool"),
    ("Agent calls", "subagent calls"),
    ("Agent delegation", "Subagent delegation"),
    ("`Read`", "`read`"),
    ("`Glob`", "`glob`"),
    ("`Grep`", "`grep`"),
    ("`Write`", "`write`"),
    ("`Edit`", "`edit`"),
    ("`Bash`", "`shell`"),
    ("`WebSearch`", "`websearch`"),
    ("`WebFetch`", "`webfetch`"),
    ("Read tool", "read tool"),
    ("Glob tool", "glob tool"),
    ("Grep tool", "grep tool"),
    ("Write tool", "write tool"),
    ("Edit tool", "edit tool"),
    ("Bash tool", "shell tool"),
    ("Bash command", "shell command"),
    ("Bash:", "Shell:"),
]


def port_text(text: str) -> str:
    """Rewrite Claude Code references for the OpenCode edition."""
    text = text.replace(BRAND, "\x00BRAND\x00")
    text = text.replace("CLAUDE_PROJECT_DIR", "OPENCODE_PROJECT_DIR")
    text = text.replace("CLAUDE.local.md", "AGENTS.local.md")
    text = text.replace("CLAUDE.md", "AGENTS.md")
    # Every remaining `.claude` is the support directory, including the
    # `[ -d ".claude" ]` and case-pattern checks in the shell hooks.
    text = text.replace(".claude", ".opencode")
    text = text.replace("Claude Code", "OpenCode")
    text = text.replace("Claude", "OpenCode")
    text = text.replace("\x00BRAND\x00", BRAND)
    for old, new in TOOL_RENAMES:
        text = text.replace(old, new)
    return text


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def copy_text_tree(src: Path, dst: Path) -> None:
    """Copy a tree, converting text files in place."""
    if not src.exists():
        return
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if item.suffix.lower() in {".md", ".sh", ".json", ".yaml", ".yml", ".gd", ".awk", ".txt"}:
            try:
                write_text(target, port_text(read_text(item)))
            except UnicodeDecodeError:
                shutil.copy2(item, target)
        else:
            shutil.copy2(item, target)


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
    if not match:
        return {}, text
    data = yaml.safe_load(match.group(1)) or {}
    body = text[match.end():]
    return data, body


def dump_frontmatter(data: dict) -> str:
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    return f"---\n{dumped}---\n\n"


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

COLORS = {
    "director": "#e63946",
    "design": "#f4a261",
    "programming": "#2a9d8f",
    "art": "#e76f51",
    "audio": "#9b5de5",
    "narrative": "#f15bb5",
    "qa": "#00bbf9",
    "production": "#457b9d",
    "engine": "#6a994e",
}

DIRECTORS = {"creative-director", "technical-director", "producer"}
DESIGN = {
    "game-designer", "systems-designer", "level-designer", "economy-designer",
    "live-ops-designer", "ux-designer", "world-builder", "writer",
}
PROGRAMMING = {
    "lead-programmer", "gameplay-programmer", "engine-programmer", "ai-programmer",
    "network-programmer", "tools-programmer", "ui-programmer", "prototyper",
    "devops-engineer", "analytics-engineer",
}
ART = {"art-director", "technical-artist", "accessibility-specialist"}
AUDIO = {"audio-director", "sound-designer"}
NARRATIVE = {"narrative-director", "localization-lead"}
QA = {"qa-lead", "qa-tester", "performance-analyst", "security-engineer"}
PRODUCTION = {"release-manager", "community-manager"}


def agent_color(name: str) -> str:
    if name in DIRECTORS:
        return COLORS["director"]
    if name in DESIGN:
        return COLORS["design"]
    if name in PROGRAMMING:
        return COLORS["programming"]
    if name in ART:
        return COLORS["art"]
    if name in AUDIO:
        return COLORS["audio"]
    if name in NARRATIVE:
        return COLORS["narrative"]
    if name in QA:
        return COLORS["qa"]
    if name in PRODUCTION:
        return COLORS["production"]
    return COLORS["engine"]


def build_permissions(meta: dict) -> list[dict]:
    """Build agent rules as deny-only.

    Agent rules are appended after global rules and the last match wins, so a
    broad agent-level `allow` would silently undo the global `.env` and
    destructive-command denies. The base policy already allows ordinary tools;
    this list only narrows each agent's grants.
    """
    tools = {t.strip() for t in str(meta.get("tools", "")).split(",") if t.strip()}
    perms: list[dict] = []
    if not ({"Write", "Edit"} & tools):
        perms.append({"action": "edit", "resource": "*", "effect": "deny"})
    # Agents without a shell grant are read/design reviewers: deny shell.
    # Agents with Bash deliberately inherit the global policy so the shared
    # destructive-command denies stay in force (agent rules are appended last).
    if "Bash" not in tools:
        perms.append({"action": "shell", "resource": "*", "effect": "deny"})
    if "WebSearch" not in tools:
        perms.append({"action": "websearch", "resource": "*", "effect": "deny"})
    if "WebFetch" not in tools:
        perms.append({"action": "webfetch", "resource": "*", "effect": "deny"})
    if "Agent" not in tools:
        perms.append({"action": "subagent", "resource": "*", "effect": "deny"})
    return perms


def generate_agents() -> int:
    out_dir = DST / "agents"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted((SRC / "agents").glob("*.md")):
        meta, body = split_frontmatter(read_text(src))
        name = meta.get("name") or src.stem
        body = port_text(body).strip() + "\n"

        notes: list[str] = []
        skills = meta.get("skills") or []
        if skills:
            quoted = ", ".join(f"`{s}`" for s in skills)
            notes.append(
                f"> **OpenCode:** Load the preloaded skill(s) {quoted} with the "
                "`skill` tool before starting."
            )
        if "Agent" in str(meta.get("tools", "")):
            notes.append(
                "> **OpenCode:** subagent nesting depth is one, so you cannot launch "
                "another subagent. When your instructions say to spawn an agent, return "
                "that request to the parent session, which launches it with the "
                "`subagent` tool."
            )
        if meta.get("memory"):
            notes.append(
                "> **OpenCode:** Automatic project memory is not available. Read and "
                f"append `.opencode/agent-memory/{name}.md` per "
                "`.opencode/rules/agent-memory.md`."
            )
        if notes:
            body = "\n\n".join(notes) + "\n\n" + body

        if meta.get("isolation") == "worktree":
            body += (
                "\n## OpenCode Worktree Note\n\n"
                "OpenCode subagents are not automatically isolated in a worktree. "
                "Create one before writing prototype files — run "
                "`git worktree add ../<project>-prototype -b prototype/<name>` or ask "
                "the parent session to call the `worktree_create` tool — and report "
                "the worktree path and branch when handing back.\n"
            )

        front = {
            "description": meta.get("description", ""),
            "mode": "subagent",
            "steps": int(meta.get("maxTurns", 20)),
            "permissions": build_permissions(meta),
            "color": agent_color(name),
        }
        write_text(out_dir / f"{name}.md", dump_frontmatter(front) + body)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Skills and commands
# ---------------------------------------------------------------------------


def generate_skills() -> int:
    count = 0
    src_root = SRC / "skills"
    for skill_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        dst_dir = DST / "skills" / skill_dir.name
        copy_text_tree(skill_dir, dst_dir)
        count += 1
    return count


def convert_skill_frontmatter() -> list[dict]:
    """Rewrite every generated SKILL.md frontmatter and collect metadata."""
    skills: list[dict] = []
    for path in sorted((DST / "skills").glob("*/SKILL.md")):
        meta, body = split_frontmatter(read_text(path))
        name = meta.get("name") or path.parent.name
        description = meta.get("description", "")
        hidden = bool(meta.get("disable-model-invocation"))
        front: dict = {"name": name, "description": description}
        if hidden:
            front["metadata"] = {"opencode/autoinvoke": False}
        # The body was already ported by copy_text_tree; port the frontmatter
        # values as well in case a description mentions Claude.
        front = {k: (port_text(v) if isinstance(v, str) else v) for k, v in front.items()}
        write_text(path, dump_frontmatter(front) + body.lstrip("\n"))
        skills.append(
            {
                "id": path.parent.name,
                "name": name,
                "description": port_text(str(description)),
                "hidden": hidden,
                "argument_hint": port_text(str(meta.get("argument-hint", ""))),
            }
        )
    return skills


def generate_commands(skills: list[dict]) -> int:
    out_dir = DST / "commands"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for skill in skills:
        front = {"description": skill["description"]}
        body = (
            f"Load the `{skill['id']}` skill with the `skill` tool and follow its "
            "instructions exactly.\n\n"
            "User input: $ARGUMENTS\n"
        )
        write_text(out_dir / f"{skill['id']}.md", dump_frontmatter(front) + body)
        count += 1
    return count


HELP_REF = re.compile(r"(?<![\w/-])/help(?![\w-])")


def rename_help_refs(text: str) -> str:
    """The studio `/help` would replace OpenCode's built-in `/help`.

    Keep the built-in and expose the studio skill as `/studio-help` instead.
    """
    return HELP_REF.sub("/studio-help", text)


def patch_help_command() -> None:
    help_cmd = DST / "commands" / "help.md"
    if help_cmd.exists():
        help_cmd.rename(DST / "commands" / "studio-help.md")
    for path in DST.rglob("*.md"):
        text = read_text(path)
        if HELP_REF.search(text):
            write_text(path, rename_help_refs(text))


# ---------------------------------------------------------------------------
# Root instructions and configuration
# ---------------------------------------------------------------------------


def generate_agents_md() -> None:
    text = port_text(read_text(ROOT / "CLAUDE.md"))

    # Claude Code `@path` imports do not exist in AGENTS.md. The same files are
    # listed under `instructions` in opencode.jsonc instead.
    text = text.replace(
        "@.opencode/docs/directory-structure.md",
        "Loaded automatically from `.opencode/docs/directory-structure.md` "
        "(listed under `instructions` in `opencode.jsonc`).",
    )
    text = text.replace(
        "@docs/engine-reference/godot/VERSION.md",
        "Loaded automatically from `docs/engine-reference/godot/VERSION.md` "
        "(listed under `instructions` in `opencode.jsonc`; `/setup-engine` "
        "updates that entry when the engine changes).",
    )
    text = text.replace(
        "@.opencode/docs/coordination-rules.md",
        "Loaded automatically from `.opencode/docs/coordination-rules.md`.",
    )
    text = text.replace(
        "@.opencode/docs/coding-standards.md",
        "Loaded automatically from `.opencode/docs/coding-standards.md`.",
    )
    text = text.replace(
        "# Claude Code Game Studios -- Game Studio Agent Architecture",
        "# Claude Code Game Studios — OpenCode Edition",
    )
    text = re.sub(
        r"<!-- ENGINE-REFERENCE-IMPORT.*?-->",
        "<!-- ENGINE-REFERENCE: engine-specific. /setup-engine replaces the\n"
        "     docs/engine-reference/<engine>/VERSION.md entry in the `instructions`\n"
        "     array of opencode.jsonc, so a Unity or Unreal project stops loading\n"
        "     the Godot reference every session. It defaults to Godot (the\n"
        "     template's example engine); skills that need the pinned version read\n"
        "     docs/engine-reference/<engine>/VERSION.md on demand. -->",
        text,
        flags=re.S,
    )
    text = text.replace(
        "Indie game development managed through 49 coordinated OpenCode subagents.",
        "Indie game development managed through 49 coordinated OpenCode subagents.\n"
        "This checkout also keeps the original `.claude/` integration for Claude Code.",
    )

    runtime = """
## OpenCode Runtime

- **Config:** `opencode.jsonc` at the repo root.
- **Agents:** `.opencode/agents/*.md` (49 subagents, `mode: subagent`).
- **Skills:** `.opencode/skills/*/SKILL.md` (74 skills). Load one with the `skill`
  tool, or run its slash command, e.g. `/start`, `/help`, `/design-system`.
- **Commands:** `.opencode/commands/*.md` (one command per skill).
- **Hooks:** `.opencode/plugins/studio-hooks.js` wraps the shell hooks in
  `.opencode/hooks/` (session context, write/read/commit/push guards, asset and
  skill validation, pre-compaction checkpoint). On Windows the hooks need Git
  Bash; set `CCGS_BASH` if it is not in a standard location.
- **Rules:** `.opencode/rules/*.md` are path-scoped references. OpenCode has no
  automatic path-scoped rules, so read the matching rule before editing that
  area (the list is in `.opencode/docs/directory-structure.md`).
- **Agent memory:** `.opencode/agent-memory/` (gitignored).
- **Original integration:** `.claude/` is unchanged and still works with Claude
  Code. Do not edit generated `.opencode/` files directly; edit `.claude/` and
  re-run `uv run --with pyyaml python tools/port-to-opencode.py`.
"""
    # Insert after the title block (before the technology stack) so it is the
    # first operational thing a model reads.
    marker = "## Technology Stack"
    if marker in text:
        text = text.replace(marker, runtime + "\n" + marker, 1)
    else:
        text += runtime
    write_text(ROOT / "AGENTS.md", rename_help_refs(text))


def normalize_path_glob(value: str) -> str:
    value = value.strip()
    value = value.replace("**/", "")
    value = value.lstrip("/")
    return value


def build_permission_rules() -> list[dict]:
    rules: list[dict] = []
    settings = json.loads(read_text(SRC / "settings.json"))
    deny = settings.get("permissions", {}).get("deny", [])

    # Sensitive reads/edits first, with the documented `.env.example` exception.
    rules.extend(
        [
            {"action": "read", "resource": "*.env", "effect": "deny"},
            {"action": "read", "resource": "*.env.*", "effect": "deny"},
            {"action": "read", "resource": "*.env.example", "effect": "allow"},
            {"action": "edit", "resource": "*.env", "effect": "deny"},
            {"action": "edit", "resource": "*.env.*", "effect": "deny"},
            {"action": "edit", "resource": "*.env.example", "effect": "allow"},
            {"action": "edit", "resource": "*.uasset", "effect": "deny"},
            {"action": "edit", "resource": "*.umap", "effect": "deny"},
        ]
    )

    seen = {(r["action"], r["resource"], r["effect"]) for r in rules}
    for entry in deny:
        match = re.match(r"^(?:Bash|PowerShell)\((.*)\)$", entry.strip())
        if match:
            resource = match.group(1).strip()
            key = ("shell", resource, "deny")
            if key not in seen:
                seen.add(key)
                rules.append({"action": "shell", "resource": resource, "effect": "deny"})
            continue
        match = re.match(r"^(Read|Edit)\((.*)\)$", entry.strip())
        if match:
            action = "read" if match.group(1) == "Read" else "edit"
            resource = normalize_path_glob(match.group(2))
            # `.env*` catch-all -> `.env` and `.env.*` already covered above.
            key = (action, resource, "deny")
            if key not in seen and resource not in {"*.env*", ".env*"}:
                seen.add(key)
                rules.append({"action": action, "resource": resource, "effect": "deny"})
    return rules


def generate_opencode_jsonc() -> None:
    instructions = [
        ".opencode/docs/directory-structure.md",
        ".opencode/docs/coordination-rules.md",
        ".opencode/docs/coding-standards.md",
        ".opencode/rules/agent-memory.md",
        "docs/engine-reference/godot/VERSION.md",
    ]
    rules = build_permission_rules()
    rules_json = ",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in rules)
    instructions_json = ",\n".join(f'    "{p}"' for p in instructions)
    content = f"""{{
  "$schema": "https://opencode.ai/config.json",

  // Project instructions loaded after AGENTS.md, in this order.
  "instructions": [
{instructions_json}
  ],

  // Ported from .claude/settings.json. OpenCode uses ordered rules: the last
  // matching rule wins, so the .env.example allow lines follow the .env denies.
  // Destructive shell commands are hard-denied; everything else keeps the
  // default allow policy and is still checked by the studio hooks.
  "permissions": [
{rules_json}
  ]
}}
"""
    write_text(ROOT / "opencode.jsonc", content)


# ---------------------------------------------------------------------------
# Plugin and docs
# ---------------------------------------------------------------------------

PLUGIN = r'''// OpenCode port of the Claude Code hooks in .claude/settings.json.
//
// The original shell hooks stay authoritative: this adapter locates Git Bash,
// feeds them Claude-compatible JSON on stdin, and maps their exit codes and
// JSON output onto OpenCode hooks. If bash or the scripts are unavailable the
// adapter fails open (no hook runs) so a missing shell never bricks a session.

import { existsSync } from "node:fs"
import { delimiter, join } from "node:path"
import { spawnSync } from "node:child_process"

const STUDIO = ".opencode"
const PRIMARY_AGENTS = new Set(["build", "plan"])

let cachedBash = null
let bashChecked = false

function findBash() {
  if (bashChecked) return cachedBash
  bashChecked = true

  const candidates = [
    process.env.CCGS_BASH,
    process.env.OPENCODE_BASH,
    process.platform === "win32" ? undefined : "bash",
    "C:\\Program Files\\Git\\bin\\bash.exe",
    "C:\\Program Files\\Git\\usr\\bin\\bash.exe",
    "C:\\Program Files (x86)\\Git\\bin\\bash.exe",
    process.platform === "win32" ? undefined : "/bin/bash",
    process.platform === "win32" ? undefined : "/usr/bin/bash",
  ].filter(Boolean)

  for (const candidate of candidates) {
    if (candidate === "bash") {
      const probe = spawnSync("bash", ["--version"], { encoding: "utf8" })
      if (!probe.error && probe.status === 0) {
        cachedBash = "bash"
        return cachedBash
      }
      continue
    }
    if (existsSync(candidate)) {
      cachedBash = candidate
      return cachedBash
    }
  }
  return undefined
}

function gitPathEntries() {
  const entries = [
    "C:\\Program Files\\Git\\cmd",
    "C:\\Program Files\\Git\\bin",
    "C:\\Program Files\\Git\\usr\\bin",
  ]
  return entries.filter((entry) => existsSync(entry))
}

function runHook(root, name, payload, timeout = 15000) {
  const bash = findBash()
  if (!bash) return null
  const script = join(root, STUDIO, "hooks", name).replace(/\\/g, "/")
  if (!existsSync(script)) return null

  const env = { ...process.env, OPENCODE_PROJECT_DIR: root, CLAUDE_PROJECT_DIR: root }
  const extra = gitPathEntries()
  if (extra.length) {
    env.PATH = [...extra, env.PATH || ""].filter(Boolean).join(delimiter)
  }

  try {
    const result = spawnSync(bash, [script], {
      cwd: root,
      input: JSON.stringify(payload),
      encoding: "utf8",
      timeout,
      maxBuffer: 4 * 1024 * 1024,
      env,
    })
    return {
      status: result.status,
      stdout: (result.stdout || "").trim(),
      stderr: (result.stderr || "").trim(),
      error: result.error,
    }
  } catch {
    return null
  }
}

function messageFrom(result) {
  const text = [result.stderr, result.stdout].filter(Boolean).join("\n").trim()
  if (!text) return "Blocked by a studio hook."
  return text.length > 6000 ? text.slice(0, 6000) + "\n...[truncated]" : text
}

// Claude hooks emit either plain text (SessionStart) or a JSON object with
// hookSpecificOutput.additionalContext / systemMessage (PreToolUse advice).
function contextFrom(result) {
  if (!result) return ""
  const text = [result.stdout, result.stderr].filter(Boolean).join("\n").trim()
  if (!text) return ""
  const lines = text.split(/\r?\n/).filter(Boolean)
  const out = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed.startsWith("{")) {
      out.push(line)
      continue
    }
    try {
      const data = JSON.parse(trimmed)
      const specific = data.hookSpecificOutput || {}
      const msg = specific.additionalContext || data.systemMessage
      if (msg) out.push(String(msg))
    } catch {
      out.push(line)
    }
  }
  return out.join("\n").trim()
}

function cap(text, limit = 12000) {
  return text.length > limit ? text.slice(0, limit) + "\n...[truncated]" : text
}

function payloadFor(action, resource, event, root) {
  const base = {
    hook_event_name: "PreToolUse",
    cwd: root,
    session_id: event.sessionID,
    agent_type: event.agent,
  }
  if (action === "shell") {
    return { ...base, tool_name: "Bash", tool_input: { command: resource } }
  }
  if (action === "read") {
    return { ...base, tool_name: "Read", tool_input: { file_path: resource } }
  }
  return { ...base, tool_name: "Write", tool_input: { file_path: resource } }
}

const PRE_HOOKS = {
  shell: ["validate-commit.sh", "validate-push.sh"],
  edit: ["validate-registry.sh", "validate-write.sh"],
  read: ["validate-read.sh"],
}

async function notify(ctx, sessionID, text) {
  if (!sessionID) return
  try {
    await ctx.session.synthetic({ sessionID, text })
  } catch {
    // Synthetic messages are best-effort; never break the tool call.
  }
}

function appendToResult(result, text) {
  if (!result || !text) return
  try {
    if (typeof result === "string") return
    if (typeof result.output === "string") {
      result.output += `\n\n${text}`
      return
    }
    if (Array.isArray(result.content)) {
      result.content.push({ type: "text", text })
    }
  } catch {
    // Unknown result shape; the synthetic message still carries the finding.
  }
}

export default {
  id: "claude-code-game-studios",
  async setup(ctx) {
    const root = ctx.location.directory

    // SessionStart -> inject the branch, stage, and checkpoint banner into the
    // first model request of each primary session.
    const started = new Set()
    await ctx.session.hook("context", async (event) => {
      if (!PRIMARY_AGENTS.has(event.agent)) return
      if (!event.sessionID || started.has(event.sessionID)) return
      started.add(event.sessionID)

      const base = {
        hook_event_name: "SessionStart",
        source: "startup",
        cwd: root,
        session_id: event.sessionID,
      }
      const parts = []
      for (const script of ["session-start.sh", "detect-gaps.sh"]) {
        const result = runHook(root, script, base, 10000)
        const text = contextFrom(result)
        if (text) parts.push(text)
      }
      if (!parts.length) return
      event.system.push({ type: "text", text: cap(parts.join("\n\n")) })

      // The original SessionStart hook also writes session logs; the model
      // does not need that output, so only stdout is injected.
      void event
    })

    // PreCompact -> persist the checkpoint before OpenCode summarizes.
    await ctx.session.hook("compaction", async (event) => {
      if (!PRIMARY_AGENTS.has(event.agent)) return
      runHook(
        root,
        "pre-compact.sh",
        {
          hook_event_name: "PreCompact",
          trigger: "auto",
          cwd: root,
          session_id: event.sessionID,
        },
        10000,
      )
    })

    // PreToolUse -> enforce the repo's read/write/commit/push guards.
    await ctx.permission.hook("evaluate", async (event) => {
      const scripts = PRE_HOOKS[event.action]
      if (!scripts) return
      if (!Array.isArray(event.resources) || !event.resources.length) return

      const notes = []
      // Patch calls can touch many files; cap the work per permission check.
      for (const resource of event.resources.slice(0, 10)) {
        const payload = payloadFor(event.action, resource, event, root)
        for (const script of scripts) {
          const result = runHook(root, script, payload, 15000)
          if (!result) continue
          if (result.status === 2) {
            event.effect = "deny"
            event.message = messageFrom(result)
            return
          }
          const advice = contextFrom(result)
          if (advice) notes.push(advice)
        }
      }
      if (notes.length) {
        await notify(ctx, event.sessionID, cap(notes.join("\n\n")))
      }
    })

    // PostToolUse -> validate assets and skill changes after a write.
    await ctx.tool.hook("execute.after", async (event) => {
      if (event.status !== "completed") return
      if (!["write", "edit", "patch"].includes(event.tool)) return

      const input = event.input || {}
      const paths = [input.file_path, input.path].filter((value) => typeof value === "string")
      if (!paths.length) return

      const notes = []
      for (const filePath of paths.slice(0, 10)) {
        const payload = {
          hook_event_name: "PostToolUse",
          cwd: root,
          session_id: event.sessionID,
          tool_name: event.tool === "write" ? "Write" : "Edit",
          tool_input: { file_path: filePath },
        }
        for (const script of ["validate-assets.sh", "validate-skill-change.sh"]) {
          const result = runHook(root, script, payload, 10000)
          if (!result) continue
          const text = [result.stdout, result.stderr].filter(Boolean).join("\n").trim()
          if (result.status === 2) {
            notes.push(messageFrom(result))
          } else if (text) {
            const advice = contextFrom(result)
            if (advice) notes.push(advice)
          }
        }
      }

      if (!notes.length) return
      const text = cap(notes.join("\n\n"))
      appendToResult(event.result, text)
      await notify(ctx, event.sessionID, text)
    })
  },
}
'''


def generate_plugin() -> None:
    write_text(DST / "plugins" / "studio-hooks.js", PLUGIN)


PORT_DOC = """# OpenCode Port

This checkout contains two integrations over the same studio definitions:

| Path | Works with |
| --- | --- |
| `.claude/` | Claude Code (original, unchanged) |
| `.opencode/` + `AGENTS.md` + `opencode.jsonc` | OpenCode V2 |

`tools/port-to-opencode.py` generates the OpenCode side from `.claude/`. Edit the
Claude definitions and re-run:

```bash
uv run --with pyyaml python tools/port-to-opencode.py
```

## What was mapped

| Claude Code | OpenCode |
| --- | --- |
| `.claude/agents/*.md` | `.opencode/agents/*.md`, `mode: subagent` |
| `tools:` allow-list | `permissions` rules (missing grants become `deny`) |
| `maxTurns:` | `steps:` |
| `model: inherit/sonnet/opus` | omitted, so every agent inherits the session model |
| `.claude/skills/*/SKILL.md` | `.opencode/skills/*/SKILL.md` |
| skills as slash commands | `.opencode/commands/<skill-id>.md` |
| `CLAUDE.md` | `AGENTS.md` |
| `@file` imports | `instructions` in `opencode.jsonc` |
| `.claude/settings.json` deny list | `permissions` in `opencode.jsonc` |
| `.claude/hooks/*.sh` | bridged by `.opencode/plugins/studio-hooks.js` |
| `AskUserQuestion` | `question` tool |
| `Agent` / `Task` tool | `subagent` tool |

## Hooks

`studio-hooks.js` bridges the shell hooks rather than rewriting them:

| Claude hook | OpenCode hook |
| --- | --- |
| `SessionStart` | `session.hook("context")`, first request per primary session |
| `PreToolUse` (Bash/PowerShell) | `permission.hook("evaluate")` with `shell` resources |
| `PreToolUse` (Write/Edit) | `permission.hook("evaluate")` with `edit` resources |
| `PreToolUse` (Read) | `permission.hook("evaluate")` with `read` resources |
| `PostToolUse` (Write/Edit) | `tool.hook("execute.after")` |
| `PreCompact` | `session.hook("compaction")` |

Not bridged: `Notification`, `Stop`, `SubagentStart`, `SubagentStop`, and the
status line. Their scripts only log or notify; OpenCode has no equivalent
notification surface, and the agent log is not needed for correctness.

### Requirements

- OpenCode V2 (`opencode --version` should report 2.x).
- A POSIX shell to run the original hooks and helper scripts. On Windows install
  Git for Windows (Git Bash) or set `CCGS_BASH` to a `bash.exe` path. If no bash
  is found the plugin fails open: the session still works, but no hook runs.
- `git` on `PATH` for the session banner and git-related helpers.

## Notes and intentional behavior changes

- **`/help`:** the studio skill is exposed as `/studio-help` so OpenCode's
  built-in `/help` keeps working. Every other skill keeps its original command
  name (`/start`, `/design-system`, …).
- **Models:** the original pinned Opus/Sonnet for some agents. All OpenCode
  agents inherit the session model; choose a model per session or per command
  instead.
- **Path-scoped rules:** OpenCode has no `.claude/rules` equivalent. The rules
  are in `.opencode/rules/` and referenced by skills and `AGENTS.md`; read the
  matching one before editing that area.
- **Agent memory:** no automatic memory. Agents write
  `.opencode/agent-memory/<name>.md` (gitignored) when their instructions say so.
- **Worktree isolation:** OpenCode has no `isolation: worktree`. The
  `prototyper` agent is told to create a worktree explicitly.
- **Skill preloading:** `skills: [...]` in Claude agent frontmatter becomes a
  body note telling the agent to load those skills with the `skill` tool.
- **`.claude/` is kept** so both harnesses can use the checkout. OpenCode gives
  `.opencode/skills` precedence over the compatibility `.claude/skills` source,
  so the ported copies win.
"""


def generate_port_doc() -> None:
    write_text(DST / "docs" / "opencode-port.md", PORT_DOC)


# ---------------------------------------------------------------------------
# Targeted fixes for engine setup
# ---------------------------------------------------------------------------


def patch_setup_engine() -> None:
    """Teach /setup-engine to update opencode.jsonc instead of @imports."""
    skill_dir = DST / "skills" / "setup-engine" / "references"
    old = skill_dir / "4-claude-md-stack.md"
    new = skill_dir / "4-agents-md-stack.md"
    if old.exists():
        old.rename(new)

    if old.exists() or new.exists():
        path = new
        text = read_text(path)
        text = text.replace("# /setup-engine — Section 4: Update AGENTS.md Technology Stack",
                            "# /setup-engine — Section 4: Update AGENTS.md and opencode.jsonc")
        text = text.replace("## 4. Update AGENTS.md Technology Stack",
                            "## 4. Update AGENTS.md Technology Stack")
        start = text.find("### Engine reference import")
        end = text.find("---", start)
        if start != -1 and end != -1:
            replacement = """### Engine reference instruction

In the same write, update the engine reference entry in `opencode.jsonc`.
OpenCode does not support `@path` imports in `AGENTS.md`; the reference file is
listed under `instructions` instead. Replace the existing
`docs/engine-reference/<engine>/VERSION.md` entry with the chosen engine:

- Godot → `docs/engine-reference/godot/VERSION.md`
- Unity → `docs/engine-reference/unity/VERSION.md`
- Unreal → `docs/engine-reference/unreal/VERSION.md`

This keeps a Unity or Unreal project from loading the Godot reference in every
session. It is idempotent — re-running `/setup-engine` for a different engine
replaces the same entry. Also update the `## Engine Version Reference` section
in `AGENTS.md` to name the same path.

"""
            text = text[:start] + replacement + text[end:]
        write_text(path, text)

    verify = skill_dir / "8-verify.md"
    if verify.exists():
        text = read_text(verify)
        text = text.replace("## 8. Verify the AGENTS.md Import",
                            "## 8. Verify the Engine Reference Instruction")
        text = text.replace("**This import was already written in Section 4",
                            "**This instruction was already written in Section 4")
        text = text.replace("Read `AGENTS.md` and confirm the line under the marker reads:",
                            "Read `opencode.jsonc` and confirm the `instructions` array contains:")
        text = text.replace("""```markdown
@docs/engine-reference/<engine>/VERSION.md
```""", """```jsonc
"docs/engine-reference/<engine>/VERSION.md"
```""")
        text = text.replace("engine, Section 4 did not complete",
                            "engine, Section 4 did not complete")
        text = text.replace("the `## Engine Version Reference` heading",
                            "the `## Engine Version Reference` section")
        write_text(verify, text)

    # Rename references and update the SKILL.md pointer.
    skill = DST / "skills" / "setup-engine" / "SKILL.md"
    if skill.exists():
        text = read_text(skill)
        text = text.replace("references/4-claude-md-stack.md", "references/4-agents-md-stack.md")
        text = text.replace("## 4. Update AGENTS.md Technology Stack",
                            "## 4. Update AGENTS.md Technology Stack")
        write_text(skill, text)


META_SKILL_NOTE = (
    "> **OpenCode:** this skill also audits Claude Code frontmatter. OpenCode reads "
    "only `name`, `description`, and `metadata[\"opencode/autoinvoke\"]`; tool access "
    "comes from the agent's `permissions`, not `allowed-tools`. Treat the checks for "
    "`allowed-tools`, `argument-hint`, `user-invocable`, `model`, and `context: fork` "
    "as Claude Code compatibility checks, not OpenCode requirements.\n\n"
)


def patch_meta_skills() -> None:
    """Note the OpenCode/Claude frontmatter split in the skill-authoring skills."""
    for skill_id in ("skill-improve", "skill-test"):
        path = DST / "skills" / skill_id / "SKILL.md"
        if not path.exists():
            continue
        text = read_text(path)
        meta, body = split_frontmatter(text)
        write_text(path, dump_frontmatter(meta) + META_SKILL_NOTE + body.lstrip("\n"))


def patch_local_template() -> None:
    old = DST / "docs" / "CLAUDE-local-template.md"
    new = DST / "docs" / "AGENTS-local-template.md"
    if old.exists():
        old.rename(new)
    if not new.exists():
        return
    text = read_text(new)
    text = text.replace("CLAUDE-local-template.md", "AGENTS-local-template.md")
    text = text.replace(
        "Copy this template to your project root: `cp .opencode/docs/AGENTS-local-template.md AGENTS.local.md`",
        "OpenCode reads `AGENTS.md` and the global `~/.config/opencode/AGENTS.md`. "
        "Keep personal overrides in the global file instead of a project-local copy.",
    )
    write_text(new, text)
    for doc in (DST / "docs").rglob("*.md"):
        text = read_text(doc)
        if "CLAUDE-local-template.md" in text:
            write_text(doc, text.replace("CLAUDE-local-template.md", "AGENTS-local-template.md"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not SRC.exists():
        print(f"error: {SRC} not found", file=sys.stderr)
        return 1
    if DST.exists():
        if not (DST / MARKER).exists():
            print(
                f"error: {DST} exists and was not generated by this script; refusing to overwrite",
                file=sys.stderr,
            )
            return 1
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    copy_text_tree(SRC / "docs", DST / "docs")
    copy_text_tree(SRC / "rules", DST / "rules")
    copy_text_tree(SRC / "scripts", DST / "scripts")
    copy_text_tree(SRC / "hooks", DST / "hooks")
    if (SRC / "statusline.sh").exists():
        write_text(DST / "statusline.sh", port_text(read_text(SRC / "statusline.sh")))

    agents = generate_agents()
    skills = generate_skills()
    skill_meta = convert_skill_frontmatter()
    commands = generate_commands(skill_meta)
    patch_help_command()

    generate_agents_md()
    generate_opencode_jsonc()
    generate_plugin()
    generate_port_doc()
    patch_setup_engine()
    patch_meta_skills()
    patch_local_template()

    # Agent memory is runtime state, never release material.
    memory_dir = DST / "agent-memory"
    memory_dir.mkdir(exist_ok=True)
    write_text(memory_dir / ".gitkeep", "")

    write_text(
        DST / MARKER,
        "Generated by tools/port-to-opencode.py from .claude/ on "
        + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        + "\n",
    )

    print(f"agents:   {agents}")
    print(f"skills:   {skills}")
    print(f"commands: {commands}")
    print(f"output:   {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
