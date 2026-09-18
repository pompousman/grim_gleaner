# Agent and Contributor Guide

This repository is intentionally tool- and model-neutral. Human contributors and
agents such as Gemini CLI, GitHub Copilot, Cursor, Aider, Continue, local models,
Claude, Codex, and future tools should all be able to work from the same contract.
No proprietary agent configuration is required.

## Fast path

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -q
```

The package requires Python 3.13 or 3.14. Run the GUI with
`grim-gleaner-ui` and inspect CLI commands with `grim-gleaner --help`.
For headless Qt tests on Linux, set `QT_QPA_PLATFORM=offscreen`.

## Architecture map

- `domain/`: stable user-facing data, especially `BuildProfile`
- `stats/registry.py`: canonical scoreable stat IDs and UI grouping
- `catalog/`: compilation and immutable runtime catalog models
- `scoring/`: deterministic relevance scoring; keep this free of UI concerns
- `output/`: localization-preserving in-game annotation
- `ui/`: PySide6 desktop application
- `automation.py`: provider-neutral machine contract and semantic validation
- `artifacts/catalog/`: checked-in compiled catalog used by development/tests
- `game_data/`: only redistributable localization inputs are tracked

## Guardrails

- Never commit proprietary extracted Grim Dawn DBR data.
- Keep scoring deterministic and offline. AI-generated profiles are untrusted
  input and must pass normal profile loading plus semantic validation.
- Persisted profile and catalog formats are versioned. Preserve backward reads
  when changing them and add migration tests.
- UI strings belong in `resources/i18n`, not inline in widgets.
- Add focused tests for behavior changes. Do not regenerate the large catalog
  unless the task explicitly updates game data.

## Universal automation contract

Do not scrape Python source to discover IDs. Use the public commands:

```bash
grim-gleaner profile-schema --output profile.schema.json
grim-gleaner profile-context --catalog-root artifacts/catalog
# Once the two class IDs are known:
grim-gleaner profile-context --catalog-root artifacts/catalog \
  --mastery playerclass05 --mastery playerclass08 --output context.json
grim-gleaner validate-profile --catalog-root artifacts/catalog \
  --profile-file candidate.json
grim-gleaner diff-profiles --before current.json --after candidate.json
grim-gleaner verify-profile-provenance --profile-file accepted.json
grim-gleaner serve-automation --catalog-root artifacts/catalog
```

The local HTTP API publishes `/openapi.json`, defaults to `127.0.0.1:8765`,
and rejects non-loopback binds until an authenticated mode exists.

`profile-context` is plain JSON and is the canonical discovery surface for any
model, script, editor extension, or web client. Integrations should not require
users to submit game data or API keys to Grim Gleaner.
