// OpenCode port of the Claude Code hooks in .claude/settings.json.
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
