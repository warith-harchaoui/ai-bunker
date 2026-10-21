# Tests Python

- `pytest`, pas de classes `unittest`.
- Un nom de test est une phrase qui énonce l'affirmation :
  `test_a_refused_command_is_not_retried`.
- Une affirmation par test. Un test qui en vérifie cinq rapporte une seule
  défaillance.
- Préférez un objet réel à un mock. Simulez ce que vous ne pouvez pas vous
  permettre d'exécuter.
- Paramétrez sur les cas plutôt que d'écrire une boucle dans un test ; une
  boucle rapporte la première défaillance et cache les autres.
