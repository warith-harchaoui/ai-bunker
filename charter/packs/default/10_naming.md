# Naming

A name is read far more often than it is written. Optimise for the reader who
arrives in six months with no context.

- Say what a thing *is*, not what type it has: `deadline`, not `date_field`.
- Prefer the domain's word over a generic one. If the business says "tender",
  the code says `tender`, not `opportunity`.
- Booleans read as assertions: `is_expired`, `has_quorum`.
- A function name is a verb phrase; a class name is a noun phrase.
- Abbreviate only what the domain already abbreviates. `vat` is fine; `amt`
  is not.
- A name that needs a comment to be understood is the wrong name.
