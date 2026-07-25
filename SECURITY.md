# Security Policy

## Supported versions

Pre-alpha releases (`0.x` / `a` tags) receive security fixes on a best-effort
basis. Once a stable channel exists, only the latest stable package minor and
the IR-compatible prior minor will receive security patches. See
[Compatibility](docs/compatibility.md).

## Reporting a vulnerability

Do **not** open a public GitHub issue for undisclosed vulnerabilities.

Prefer GitHub's private vulnerability reporting / draft Security Advisory for
[`fraware/environment-assurance-compiler`](https://github.com/fraware/environment-assurance-compiler).

Include:

- Affected version or commit
- Reproduction steps or a non-destructive PoC
- Impact assessment (for example RCE via generated code, secret leakage into
  packs, plugin allowlist bypass, path traversal on extract)

You should receive an acknowledgment within **7 days**. We follow coordinated
disclosure; please allow reasonable time before public discussion.

## Threat surface (summary)

Environment Packs (`.eap`), generated code, plugins, and imported sources are
treated as **untrusted** until inspected and verified. Network and subprocess
connectors are opt-in. See the full
[threat model](docs/security/threat-model.md).
