# Contributing

Thank you for improving the Azure Product Growth Intelligence Platform.

## Development Workflow

1. Create a virtual environment with Python 3.11 or later.
2. Run `make install`.
3. Make focused changes that preserve local-first reproducibility.
4. Run `make quality` before opening a pull request.

## Standards

- Keep runtime dependencies minimal until a milestone needs them.
- Do not commit generated datasets, model binaries, local virtual environments, caches, temporary outputs, or secrets.
- Prefer typed Python and deterministic behaviour.
- Keep Azure-specific code behind planned adapters rather than embedding cloud assumptions in domain logic.
- Update documentation and tests with behaviour changes.

