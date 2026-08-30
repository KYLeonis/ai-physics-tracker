# .github/

GitHub-only repository automation lives here.

- `workflows/`: short kebab-case workflow files. Each workflow must run without secrets.
- Keep generated artifacts out of Git; CI artifacts are ephemeral and should have explicit retention.
- Remove obsolete workflows in the same change that replaces their checks.
