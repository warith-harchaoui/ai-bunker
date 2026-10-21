# Style Python

- `ruff` décide du formatage et du lint. Ne discutez pas avec le formateur en
  revue.
- Les docstrings sont au format numpydoc. Une fonction publique sans docstring
  est incomplète.
- Typez toute signature publique. `from __future__ import annotations` en tête.
- Préférez une dataclass à un dictionnaire pour tout ce qui franchit une
  frontière de fonction plus d'une fois.
- Levez une exception sur une entrée invalide à la frontière ; ne renvoyez pas
  une valeur sentinelle en espérant que ça passe.
