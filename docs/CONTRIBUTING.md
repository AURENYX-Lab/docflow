docflow prioritizes deterministic behavior and strict contracts.

Guidelines:

- avoid implicit defaults
- maintain reproducibility
- prefer deterministic heuristics over AI solutions
- never introduce silent file operations

Before submitting PRs:

- run tests
- ensure CLI help works without settings
- ensure suggestions remain schema-valid
