# ADR-0004: Plugin Edges

- Status: Accepted
- Date: 2026-07-25

## Context

Domain-specific adapters, codegen targets, and connectors must extend the
compiler without forking the core. Plugins also expand the supply-chain attack
surface.

## Decision

Plugins load via documented entry points and scaffolds with a versioned plugin
API (`plugin_api_version`). Release mode uses allowlists. Plugin versions and
template digests are pinned in `.eac/plugin-lock.json` / `.eac/lock.json`.
Partner-specific semantics stay in packs and plugins, not the core IR.

## Consequences

- Core remains domain-neutral.
- `eac plugins create|test|package|doctor` verifies scaffolding, API
  compatibility, and optional allowlist enforcement (`EAC9006` on failure).
- Untrusted plugins cannot silently become default in release builds.
