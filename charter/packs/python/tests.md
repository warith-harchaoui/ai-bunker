# Python tests

- `pytest`, no `unittest` classes.
- A test name is a sentence stating the claim: `test_a_refused_command_is_not_retried`.
- One claim per test. A test asserting five things reports one failure.
- Prefer a real object over a mock. Mock what you cannot afford to run.
- Parametrise over cases rather than writing a loop inside a test; a loop
  reports the first failure and hides the rest.
