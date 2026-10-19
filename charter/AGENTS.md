# How to work here

This deployment serves a model behind a bounded context window. Work in small,
self-contained steps by default: the floor of a session is paid on every
request, and what is left is the only room you have.

## Operating rules

1. Never load a large file, log, diff, dependency tree, or command output in
   one shot. Read in slices of about eighty lines and continue only when the
   next slice is actually needed.
2. Discover before you read: `grep`, `rg`, `find`, `git diff --stat`, a narrow
   `sed -n`. A targeted search costs a fraction of a file.
3. Bound noisy commands explicitly (`head`, `tail`, `sed -n`, a precise grep).
4. Do not reread unchanged files. Keep a short working map instead: goal,
   relevant files, decisions taken, next action.
5. A truncated output is not an error. Ask for the next slice; do not try to
   recover the whole thing.
6. Keep each step narrow: inspect, decide, edit, verify. No repository-wide
   scan once the relevant files are known.
7. Before a broad refactor, build the file list first, then process it one
   file at a time.
8. On compaction, keep the goal, the decisions, the active files and the next
   action. Keep paths and line ranges, never raw transcripts.

## The charter

`packs/**` holds this team's written standards. Only an index of those pages is
in your prompt; read the page for the domain you are working in, once, and keep
the conclusion rather than the text. On compaction, keep the path.

## Rules are enforced, not suggested

Tool output is screened before it reaches you: secrets are redacted and a short
`[rules]` note names what fired. A redacted value is gone on purpose.

A refused command comes back as `[rules] <id> refuses this command`. That is a
decision, not a transient failure: reformulate with a narrower target or a
bounded range. Never retry it unchanged.
