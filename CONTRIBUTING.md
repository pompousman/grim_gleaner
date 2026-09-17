# Contributing to Grim Gleaner

Contributions from people and from any coding assistant are welcome. What
matters is a reviewable change, tests, and respect for the game's proprietary
data—not which tool produced it.

## Development setup

Use Python 3.13 or 3.14:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m pytest -q
```

Launch with `grim-gleaner-ui`. The checked-in catalog is sufficient for normal
UI, scoring, profile, export, and test work. Recompiling it requires DBRs
extracted from your own Grim Dawn installation; those files must not be
committed or shared.

## Good first contribution areas

- Add an interface translation under `resources/i18n`.
- Improve keyboard and screen-reader accessibility in the PySide UI.
- Add profile examples for underrepresented archetypes.
- Build against the provider-neutral profile JSON contract (web companion,
  editor extension, local-model workflow, or build-guide importer).
- Improve stat normalization with a fixture and regression test.

## Pull requests

1. Keep a change focused and explain user-visible behavior.
2. Add or update tests and run `python -m pytest -q`.
3. Never include extracted proprietary game databases or non-English archives.
4. Call out profile/catalog schema changes and preserve backward compatibility.
5. If AI assisted the work, review and own the result. Naming a vendor is not
   required; reproducibility and correctness are.

See [AGENTS.md](AGENTS.md) for the architecture map and repository guardrails.

## Integration philosophy

Grim Gleaner's core is deterministic and offline. Integrations exchange
versioned JSON rather than calling a specific hosted model. This keeps profile
generation open to hosted providers, local models, conventional programs, and
future tools while ensuring generated profiles are validated before use.
