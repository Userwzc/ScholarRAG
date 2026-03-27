# Problems - Necessary Features Roadmap

## Open Problem 1: LSP Environment Drift

- Pyright diagnostics still report missing SQLAlchemy imports for changed files.
- Runtime path is valid (`pytest` passes), so this is tooling-environment mismatch rather than code breakage.
- Follow-up: align LSP interpreter/venv with test runtime to restore clean diagnostics gate.
