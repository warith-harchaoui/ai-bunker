// The one thing the gateway structurally cannot do.
//
// Everything else ai-bunker enforces, it enforces at the endpoint: secrets,
// injection, dangerous commands, the session budget, the charter. None of that
// needs a plugin, and none of it can be disabled by editing a file.
//
// A file read is different. The gateway never sees the read -- it sees the
// result, already inside the request, with the tokens already spent. So the
// only place a read can be bounded is here, before it happens.
//
// This is the whole plugin. If it grows, something has been put in the wrong
// place: ask whether the gateway could see it instead.
//
// Measured stake: an agent holding ~32k of live context per session fits
// roughly twice as many concurrent sessions on the same GPU as one holding
// ~64k. Bounded reads are the single largest contributor to which of those a
// session is, so this file is worth about half a machine.

const DEFAULT_LINES = 80
const MAX_LINES = 120

function envInt(name, fallback) {
  const raw = process.env[name]
  if (!raw) return fallback
  const value = Number.parseInt(raw, 10)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

export const BoundedReadsPlugin = async () => ({
  "tool.execute.before": async (input, output) => {
    if (!input || input.tool !== "read" || !output?.args) return
    const args = output.args
    const dflt = envInt("AI_BUNKER_READ_LINES", DEFAULT_LINES)
    const cap = envInt("AI_BUNKER_READ_MAX_LINES", MAX_LINES)
    // `offset` stays entirely under the model's control: the point is to make
    // reading incremental, not to make part of a file unreachable.
    if (args.limit == null) args.limit = dflt
    if (typeof args.limit === "number" && args.limit > cap) args.limit = cap
  },

  "experimental.session.compacting": async (_input, output) => {
    if (!Array.isArray(output?.context)) return
    // Compaction is client-side too, and what survives it decides what the
    // next turns cost. Keeping a path instead of a file body is the same
    // economy as the charter's index.
    output.context.push(`
## Compaction rules
- Keep only: the goal, decisions taken, active files, edits already made, next action.
- Never carry forward long tool output, logs, diffs, or whole files.
- For large files keep the path and the useful line ranges, then reread in slices.
- Truncated output is not an error: ask for the next slice.
- Keep the PATH of charter pages already read, never their text.
`)
  },
})
