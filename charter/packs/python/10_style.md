# Python style

- `ruff` decides formatting and lint. Do not argue with the formatter in review.
- Docstrings are numpydoc. A public function without a docstring is incomplete.
- Type every public signature. `from __future__ import annotations` at the top.
- Prefer a dataclass over a dict for anything that crosses a function boundary
  more than once.
- Raise on invalid input at the boundary; do not return a sentinel and hope.
