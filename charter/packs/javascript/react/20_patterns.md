# React patterns

- Components are functions. No classes in new code.
- State lives as high as it must and no higher.
- An effect synchronises with something external. If it only derives a value,
  it should not be an effect.
- Keys are stable identities, never array indices.
