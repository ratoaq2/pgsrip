---
paths:
  - "pyproject.toml"
  - ".pre-commit-config.yaml"
  - ".github/workflows/**"
  - "scripts/**"
---

# Tooling

These files define the commands and checks. When you change one, make sure that the commands in
`CONTRIBUTING.md` are still correct, and that `scripts/test.sh` still runs the same checks as CI.
