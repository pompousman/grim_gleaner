# Grim Gleaner: Open Ecosystem Roadmap

The long-term opportunity is bigger than an item grader: Grim Gleaner can become
an open, local-first build-intelligence layer for Grim Dawn. The deterministic
engine remains the authority; assistants are optional clients, never a required
backend.

## Foundation — shipped in this repository

- **Universal profile contract:** JSON Schema, catalog-aware discovery context,
  and semantic validation are available from the CLI.
- **Model-neutral onboarding:** the same workflow works with hosted assistants,
  local models, IDE agents, scripts, and hand-authored JSON.
- **Desktop integration center:** the Build Profile screen can save or copy a
  focused context, export the schema, validate candidate files, preview
  diagnostics, and import confirmed output as an unsaved draft.
- **Safe profile replacement:** manual and generated imports protect unsaved
  work; persisted profiles are checked for real stat/skill IDs and valid mastery
  relationships. One-rank transmuter skills are now selectable and valid.
- **Reviewable imports and provenance:** file or clipboard candidates receive a
  semantic before/after diff. Optional generator/source metadata and SHA-256
  bindings are saved in a separate provenance sidecar, never scoring data.
- **Local automation API:** a dependency-free, localhost-first HTTP service
  exposes health, schema, context, validation, semantic diff, bounded catalog
  search, and explainable per-slot ranking endpoints with a discoverable
  OpenAPI document.
- **Contributor runway:** documented setup/architecture and Linux + Windows CI.
- **Privacy boundary:** no API key handling and no proprietary DBR upload path.

## Next: make integrations delightful

1. **Richer provenance review**
   - Add a dedicated sidecar viewer, signature verification, and visual grouping
     for large semantic diffs.
   - Track subsequent user-edit history without polluting the scoring payload.
2. **GrimTools bridge**
   - Import a build URL or exported build document.
   - Infer masteries, active skills, damage channels, conversions, attack style,
     and defensive gaps into an editable *draft*, never an opaque final answer.
3. **Broaden the local automation server**
   - Shipped: explainable ranking endpoint (`POST /v1/ranking`) and the
     matching `grim-gleaner rank-profile` CLI command return per-slot matches
     with matched stat weights, unmatched stat IDs, coverage, and grade
     thresholds—the same deterministic engine as the Gear Grades screen.
   - Add a Model Context Protocol (MCP) stdio transport on top of the shipped
     localhost HTTP/OpenAPI service.
   - Add opt-in authentication before supporting any non-loopback bind or write
     operation.
4. **Provider adapters as separate plugins**
   - Optional adapters for OpenAI-compatible APIs, Anthropic, Gemini, Ollama,
     llama.cpp, and command-line subprocesses.
   - Keep adapters out of the core package; pass the same context and validate
     the same response. Capabilities, not vendor names, drive behavior.

## Next: improve the actual intelligence

- **Explainable grades:** the ranking API and Gear Grades view now share one
  deterministic engine and both expose matched stat weights, unmatched stat
  IDs, coverage, and grade thresholds. Remaining: surface positive signals and
  dilution costs inside the UI detail views, level-band assumptions, and
  "what would move this from A to S?" counterfactuals.
- **Cap-aware profiles:** optionally capture current resistances, speed caps, OA/DA,
  and conversion state so marginal value replaces static relevance.
- **Roll-aware evaluation:** where legally and technically feasible, accept an
  explicitly exported item snapshot and compare its actual roll with the catalog
  range. Keep memory/process inspection out of the default product.
- **Whole-loadout optimizer:** optimize combinations rather than isolated items,
  with constraints for slots, sets, resistance caps, skill points, and user locks.
  Present a Pareto frontier instead of pretending one score is universally best.
- **Confidence and provenance:** every inferred weight records why it exists and
  whether it came from the user, an importer, a heuristic, or an assistant.

## Expansion: community platform without lock-in

- A signed, versioned **profile pack** format containing profiles, descriptions,
  screenshots, source links, supported game versions, and checksums.
- A decentralized profile index hosted as ordinary Git repositories; the app can
  subscribe to any index, not only an official service.
- Reproducible catalog-update automation that reports game-data diffs for human
  review after patches.
- Translation kits generated from stable message IDs, Weblate-compatible files,
  locale completeness checks, and right-to-left layout testing.
- Accessible keyboard-first UX, high-contrast themes, screen-reader labels, and
  portable packages for Windows first, then Linux via Flatpak/AppImage.

## Moonshots

- **Build laboratory:** ask “what changes if this conversion becomes 100%?” and
  rerun rankings in a sandboxed scenario without editing the base profile.
- **Drop-plan graph:** turn desired items/components into a route by faction,
  reputation, vendor, monster, and crafting dependencies.
- **Collaborative profile diffs:** review build changes like code, with semantic
  output such as “Fire moved 3 → 4; casting speed removed; target level 80–89.”
- **Offline companion PWA:** compile the pure scoring domain to a service usable
  by a web UI while desktop-only extraction/export remains in the native app.
- **Benchmark suite for build assistants:** publish anonymized prompts and expert
  profiles, then score every model or heuristic against one open benchmark. This
  makes quality measurable without making any provider the gatekeeper.

## Architectural rules

1. Deterministic features work with networking disabled.
2. User data and game files stay local unless the user explicitly exports them.
3. All generated data enters through versioned schemas and validation.
4. Core capabilities are callable from Python, CLI, and documented protocols.
5. Provider-specific code is optional and replaceable.
6. Explanations and user control are more important than confident automation.
