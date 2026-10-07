# Changelog

All notable changes to this plugin are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version is the one in
`.claude-plugin/plugin.json`, which every skill's `metadata.version` must match.

## Versioning

Bumping `version` in `plugin.json` is the release: it decides when anyone who
installed from a marketplace receives the update. For a skill, the parts mean:

- **Major** — something that worked before stops working or behaves differently
  without being asked: a removed or renamed skill, agent or reference; a change to
  the shape of `discovery-state.json` or the generated spec that an earlier
  interview or stack cannot be resumed from; a wider `allowed-tools` grant.
- **Minor** — something new that leaves existing use untouched: a new domain,
  regime, provider or question; a new agent; new reference material.
- **Patch** — the same behaviour, done better: wording, trigger descriptions,
  corrected references, fixes to scripts and checks.

## [1.0.0] - 2026-10-07

### Added

- `discover` skill: structured architecture discovery interview that emits an
  infrastructure spec, Mermaid diagrams, ADRs and an open-questions log as a
  branch and pull request.
- `iac` skill: turns an approved specification into a Terragrunt and Terraform,
  OpenTofu or plain Terraform stack with pinned versions, gated by fmt and validate.
- `iac-planner`, `iac-builder` and `iac-validator` agents.
- Guardrail hook and repository selftest (`scripts/check_repo.py`).
