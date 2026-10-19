# Claude Code Game Studios — OpenCode Edition

Indie game development managed through 49 coordinated OpenCode subagents.
This checkout also keeps the original `.claude/` integration for Claude Code.
Each agent owns a specific domain, enforcing separation of concerns and quality.


## OpenCode Runtime

- **Config:** `opencode.jsonc` at the repo root.
- **Agents:** `.opencode/agents/*.md` (49 subagents, `mode: subagent`).
- **Skills:** `.opencode/skills/*/SKILL.md` (74 skills). Load one with the `skill`
  tool, or run its slash command, e.g. `/start`, `/studio-help`, `/design-system`.
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

## Technology Stack

- **Engine**: [CHOOSE: Godot 4 / Unity / Unreal Engine 5]
- **Language**: [CHOOSE: GDScript / C# / C++ / Blueprint]
- **Version Control**: Git with trunk-based development
- **Build System**: [SPECIFY after choosing engine]
- **Asset Pipeline**: [SPECIFY after choosing engine]

> **Note**: Engine-specialist agents exist for Godot, Unity, and Unreal with
> dedicated sub-specialists. Use the set matching your engine.

## Project Structure

Loaded automatically from `.opencode/docs/directory-structure.md` (listed under `instructions` in `opencode.jsonc`).

## Engine Version Reference

<!-- ENGINE-REFERENCE: engine-specific. /setup-engine replaces the
     docs/engine-reference/<engine>/VERSION.md entry in the `instructions`
     array of opencode.jsonc, so a Unity or Unreal project stops loading
     the Godot reference every session. It defaults to Godot (the
     template's example engine); skills that need the pinned version read
     docs/engine-reference/<engine>/VERSION.md on demand. -->
Loaded automatically from `docs/engine-reference/godot/VERSION.md` (listed under `instructions` in `opencode.jsonc`; `/setup-engine` updates that entry when the engine changes).


## Technical Preferences

`project.yaml` at the repo root is the primary config store — engine, specialists,
naming, platform, performance, modes. Skills resolve it via `resolve_config`
(see `.opencode/docs/config-resolution.md`).

`.opencode/docs/technical-preferences.md` is the **legacy fallback**, read on demand
when a key is absent from `project.yaml`. It is not imported here: before
`/setup-engine` runs it is almost entirely `[TO BE CONFIGURED]` placeholders, and
after it runs `project.yaml` holds the real values.

## Coordination Rules

Loaded automatically from `.opencode/docs/coordination-rules.md`.

## Collaboration Protocol

**User-driven collaboration, not autonomous execution.**
Every task follows: **Question -> Options -> Decision -> Draft -> Approval**

- Agents MUST ask "May I write this to [filepath]?" before using Write/edit tools
  (exempt: `active.md` appends, agent memory, a subagent's new file at the path
  its orchestrating skill named; see `.opencode/rules/agent-memory.md`)
- Agents MUST show drafts or summaries before requesting approval
- Multi-file changes require explicit approval for the full changeset
- No commits without user instruction
- A skipped or dismissed question is not an answer: act on nothing, re-ask in
  plain text and wait
- Started outside this file's folder? Warn first: hooks, deny rules and the
  ask-first mode load only when OpenCode starts here

See `docs/COLLABORATIVE-DESIGN-PRINCIPLE.md` for full protocol and examples.

> **First session?** If the project has no engine configured and no game concept,
> run `/start` to begin the guided onboarding flow.

## Coding Standards

Loaded automatically from `.opencode/docs/coding-standards.md`.

## Context Management

Read `.opencode/docs/context-management.md` on demand — it is a reference, not
session context. Two of its conventions are load-bearing and cited by name
elsewhere in the repo, so they are restated here rather than lost:

- **`production/session-state/active.md` is the session checkpoint.** The file is
  the memory, not the conversation. Read it first after any compaction, crash, or
  `/clear`.
- **Helpers in `.opencode/scripts/` emit observations, never verdicts.** A script
  that scores or judges will eventually contradict a mode or override it cannot
  see. (Cited by `artifact-check.sh` and `adr-dep-graph.sh`.)
