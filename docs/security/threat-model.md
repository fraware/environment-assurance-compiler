# Threat model

**Status:** Living document  
**Scope:** Local EnvAssure compiler (`envassure` / `eac`), workspaces, generated
code, Environment Packs, plugins, and optional connectors  
**Repository:** [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)

## Assets

- Authoring workspace (sources, decisions, IR, secrets accidentally present)
- Lock and digests (reproducibility / integrity)
- Generated runtime and tests (executable)
- Environment Packs (`.eap`) — portable archives of IR and related artifacts
- Plugin packages and entry points
- Developer machine credentials and network access

## Threat actors

| Actor | Motivation |
| ----- | ---------- |
| Malicious source author | Code exec / misrepresentation |
| Compromised plugin publisher | Supply-chain backdoor |
| Pack consumer | Unwitting execution of pack / generated code |
| Prompt-injection via docs or proposals | Model-assisted path pollution |
| Network attacker | MITM when network features are enabled |

## Threats and controls

| Threat | Control |
| ------ | ------- |
| Malformed / hostile source files | Fail-closed parsers; digests; size/streaming bounds on traces |
| Generated-code execution | Never auto-run untrusted packs; consumers must isolate |
| Secret leakage into packs | Secret-scan gates on `eac package` / `eac verify-pack` (`EAC8006`) |
| Plugin supply chain | Allowlists in release mode; pinned `.eac/plugin-lock.json`; `eac plugins doctor` |
| Compromised PyPI / CI artifacts | Blocking `pip-audit`, Gitleaks, CycloneDX SBOM, GitHub build-provenance attestations ([supply chain](supply-chain.md)) |
| Pack-as-untrusted | Document packs as executable evidence; checksum verification |
| Prompt injection (model-assisted) | Explicit `model_proposal` origin; non-authoritative until decided |
| Path traversal / archive extraction | Safe extract APIs; reject absolute / `..` paths |
| DoS via huge schemas / traces | Streaming trace ingestion; bounded probes |
| Model proposals as facts | Taint / authority class `model_proposal` |
| Compromised or live connectors | Network and subprocess **opt-in**; prefer fixtures / simulators |
| Silent IR rewrite | Migrations only via `eac migrate`; verify never migrates |

## Trust boundaries

1. **Workspace sources** — untrusted until digested and reviewed.
2. **Expert decisions** — trusted within declared scope only.
3. **Generated code / packs** — untrusted until inspected and verified.
4. **Plugins** — untrusted unless allowlisted and locked.
5. **Reference connectors** — trust only what you configured; CI should default
   to recorded fixtures.

## Non-goals (security)

EnvAssure is not a sandbox hypervisor. Pack consumers must apply their own
execution isolation when running third-party packs or generated code.

## Related

- [Supply chain (SBOM / attestations / CI gates)](supply-chain.md)
- [SECURITY.md](https://github.com/fraware/environment-assurance-compiler/blob/main/SECURITY.md)
- [Plugin API](../reference/plugin-api.md)
- [Package and publish](../guides/package-and-publish.md)
