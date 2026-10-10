# Contributing

This repository is primarily a learning and portfolio project. Contributions should preserve the dry-run-first and fail-closed safety posture.

## Before opening a pull request

- Run `python -m unittest discover -s tests -v`.
- Run Python compilation for changed files.
- Update documentation when behavior or permissions change.
- Add or update tests for lifecycle decisions.
- Confirm no real tenant data or credentials are included.
- Redact screenshots and sample output.

## Coding expectations

- Prefer deterministic planning.
- Keep tenant-specific values out of committed templates.
- Do not add destructive operations without an explicit design review.
- Keep managed-group changes allowlisted.
- Preserve secret-safe audit logging.
- Explain permission changes in `docs/PERMISSIONS-MATRIX.md`.

## Commit examples

```text
feat: add read-only Graph connectivity check
fix: reject unresolved group identifiers in apply mode
docs: explain managed identity authentication
test: cover termination safety limit
```
