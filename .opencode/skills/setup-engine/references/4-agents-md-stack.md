# /setup-engine — Section 4: Update AGENTS.md and opencode.jsonc

> Part of `/setup-engine`. `SKILL.md` names when to read this file; the settings it
> resolved and the rules under its later headings still apply here.

## 4. Update AGENTS.md Technology Stack

### Language Selection (Godot only)

If Godot was chosen, ask the user which language to use **before** showing the proposed Technology Stack:

> "Godot supports two primary languages:
>
>   **A) GDScript** — Python-like, Godot-native, fastest iteration. Best for beginners, solo devs, and teams coming from Python or Lua.
>   **B) C#** — .NET 8+, familiar to Unity developers, stronger IDE tooling (Rider / Visual Studio), slight performance advantage on heavy logic.
>   **C) Both** — GDScript for gameplay/UI scripting, C# for performance-critical systems. Advanced setup — requires .NET SDK alongside Godot.
>
> Which will this project primarily use?"

Record the choice. It determines the AGENTS.md template, naming conventions, specialist routing, and which agent is spawned for code files throughout the project.

### Primary Language (Unreal)

If Unreal was chosen, ask via `question`: "Will most gameplay logic live in
C++ or in Blueprints?" — `[A] C++ (Blueprints for tuning and prototyping)` /
`[B] Blueprint-primary (C++ only where needed)`. Default to C++ if the user has no
preference. The answer sets `engine.language` (`"C++"` or `"Blueprint"`).

---

Read `AGENTS.md` and show the user the proposed Technology Stack changes.
Ask: "May I write these engine settings to `AGENTS.md`?"

Wait for confirmation before making any edits.

Update the Technology Stack section, replacing the `[CHOOSE]` placeholders with the actual values:

**For Godot** — use the template matching the language chosen above. See `references/godot-language-config.md` (**A1**) for all three variants (GDScript, C#, Both).

**For Unity:**
```markdown
- **Engine**: Unity [version]
- **Language**: C#
- **Build System**: Unity Build Pipeline
- **Asset Pipeline**: Unity Asset Import Pipeline + Addressables
```

**For Unreal:**
```markdown
- **Engine**: Unreal Engine [version]
- **Language**: [C++ (primary), Blueprint (gameplay prototyping) | Blueprint (primary), C++ where needed]
- **Build System**: Unreal Build Tool (UBT)
- **Asset Pipeline**: Unreal Content Pipeline
```
The Language line follows the primary-language answer above: the first form for
`[A]` (`engine.language: "C++"`), the second for `[B]` (`"Blueprint"`).

### Engine reference instruction

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

---
