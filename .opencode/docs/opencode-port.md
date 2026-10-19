# OpenCode Port

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
