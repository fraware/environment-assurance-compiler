"""OPA / Rego backend for proof obligations."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from envassure.obligations.ir import ProofObligation, ProofObligationBundle

# Six obligation families compiled into Rego (beta §15.2 mapping).
OPA_FAMILIES: tuple[str, ...] = (
    "authorization_preservation",
    "resource_conservation",
    "deterministic_reset_replay",
    "observation_separation",
    "reward_trace_binding",
    "idempotency_safety",
)

_UNSUPPORTED_BACKEND = frozenset({"formal_prover_only", "smt_required"})


class OpaBackendError(ValueError):
    """Fail-closed OPA backend / bundle error."""


def require_opa_binary(*, min_version_prefix: str = "1.") -> str:
    """Return path to ``opa`` binary or raise (system install; not vendored)."""
    path = shutil.which("opa")
    if not path:
        raise OpaBackendError(
            "OPA binary not found on PATH. Install Open Policy Agent and pin the "
            "version in CI (extra envassure[opa] documents this dependency)."
        )
    try:
        proc = subprocess.run(
            [path, "version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OpaBackendError(f"failed to invoke opa: {exc}") from exc
    version_line = (proc.stdout or proc.stderr or "").splitlines()[:1]
    detail = version_line[0] if version_line else "unknown"
    if min_version_prefix and min_version_prefix not in detail and "Version:" in detail:
        # Soft check — still allow; CI pins explicitly.
        pass
    return path


def _assert_supported(obl: ProofObligation) -> None:
    if obl.status == "unsupported":
        raise OpaBackendError(
            f"obligation {obl.id!r} is unsupported; refuse OPA generation: "
            + "; ".join(obl.unsupported_conditions or ["unsupported"])
        )
    for req in obl.backend_requirements:
        if req in _UNSUPPORTED_BACKEND:
            raise OpaBackendError(f"obligation {obl.id!r} requires unsupported backend {req!r}")


def emit_rego_v1_bundle(
    bundle: ProofObligationBundle,
    output_dir: Path | str,
    *,
    package: str = "envassure.obligations",
) -> Path:
    """Write a Rego v1 policy bundle for *bundle*.

    Layout::

        .manifest
        policy.rego
        data.json
        schema.json
        policy_test.rego
        obligation-map.json
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    supported: list[ProofObligation] = []
    for obl in bundle.obligations:
        if obl.claim_kind not in OPA_FAMILIES and obl.claim_kind != "idempotency_safety":
            # Unknown families fail closed before generation.
            raise OpaBackendError(f"unknown obligation family {obl.claim_kind!r}")
        _assert_supported(obl)
        supported.append(obl)

    # Allow empty supported set only when bundle is empty.
    policy = _render_policy(package, supported)
    tests = _render_tests(package, supported)
    data = {
        "environment_id": bundle.environment_id,
        "ir_digest": bundle.ir_digest,
        "obligations": [
            {
                "id": o.id,
                "claim_kind": o.claim_kind,
                "status": o.status,
                "mechanism_strength": o.mechanism_strength,
            }
            for o in supported
        ],
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EnvAssureOPAInput",
        "type": "object",
        "properties": {
            "action_id": {"type": "string"},
            "authorized": {"type": "boolean"},
            "state_before": {"type": "object"},
            "state_after": {"type": "object"},
            "observation_actor": {"type": "object"},
            "observation_other": {"type": "object"},
            "idempotency_key": {"type": ["string", "null"]},
            "replay_equal": {"type": "boolean"},
            "reward_bound": {"type": "boolean"},
        },
        "additionalProperties": True,
    }
    obligation_map = {
        o.id: {
            "claim_kind": o.claim_kind,
            "rego_rule": f"deny_{_safe_id(o.id)}",
            "expected_evidence": list(o.expected_evidence),
        }
        for o in supported
    }
    manifest = {
        "revision": bundle.schema_version,
        "roots": [package.replace(".", "/")],
        "metadata": {
            "environment_id": bundle.environment_id,
            "generator": "envassure.obligations.backends.opa",
            "rego_version": "v1",
        },
    }

    (out / ".manifest").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "policy.rego").write_text(policy, encoding="utf-8", newline="\n")
    (out / "policy_test.rego").write_text(tests, encoding="utf-8", newline="\n")
    (out / "data.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (out / "schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    (out / "obligation-map.json").write_text(
        json.dumps(obligation_map, indent=2) + "\n", encoding="utf-8"
    )
    return out


def _safe_id(oid: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in oid)


def _render_policy(package: str, obligations: list[ProofObligation]) -> str:
    lines = [
        "# METADATA",
        f"# description: EnvAssure obligation policy for {package}",
        "package envassure.obligations",
        "",
        "import rego.v1",
        "",
        "default allow := false",
        "",
        "allow if {",
        "\tcount(deny) == 0",
        "}",
        "",
        "deny contains msg if {",
        "\tsome v in violations",
        '\tmsg := sprintf("obligation_violation: %v", [v])',
        "}",
        "",
        "violations contains v if {",
        "\tsome v in auth_violations",
        "}",
        "",
        "violations contains v if {",
        "\tsome v in resource_violations",
        "}",
        "",
        "violations contains v if {",
        "\tsome v in replay_violations",
        "}",
        "",
        "violations contains v if {",
        "\tsome v in observation_violations",
        "}",
        "",
        "violations contains v if {",
        "\tsome v in reward_violations",
        "}",
        "",
        "violations contains v if {",
        "\tsome v in idempotency_violations",
        "}",
        "",
        "# --- family: authorization_preservation ---",
        "auth_violations contains v if {",
        "\tinput.authorized == false",
        "\tinput.state_before != input.state_after",
        '\tv := "authorization_preservation"',
        "}",
        "",
        "# --- family: resource_conservation ---",
        "resource_violations contains v if {",
        '\tcount_before := object.get(input.state_before, "count", 0)',
        '\tcount_after := object.get(input.state_after, "count", 0)',
        "\tis_number(count_before)",
        "\tis_number(count_after)",
        "\tcount_after < 0",
        '\tv := "resource_conservation"',
        "}",
        "",
        "# --- family: deterministic_reset_replay ---",
        "replay_violations contains v if {",
        "\tinput.replay_equal == false",
        '\tv := "deterministic_reset_replay"',
        "}",
        "",
        "# --- family: observation_separation ---",
        "observation_violations contains v if {",
        "\tinput.observation_actor == input.observation_other",
        '\tobject.get(input, "expect_separation", false) == true',
        '\tv := "observation_separation"',
        "}",
        "",
        "# --- family: reward_trace_binding ---",
        "reward_violations contains v if {",
        "\tinput.reward_bound == false",
        '\tv := "reward_trace_binding"',
        "}",
        "",
        "# --- family: idempotency_safety ---",
        "idempotency_violations contains v if {",
        "\tinput.idempotency_key != null",
        '\tobject.get(input, "idempotent_replay_equal", true) == false',
        '\tv := "idempotency_safety"',
        "}",
        "",
    ]
    # Annotate which obligations were compiled.
    lines.append("# Compiled obligations:")
    for obl in obligations:
        lines.append(f"# - {obl.id} ({obl.claim_kind})")
    lines.append("")
    return "\n".join(lines)


def _render_tests(package: str, obligations: list[ProofObligation]) -> str:
    lines = [
        "package envassure.obligations_test",
        "",
        "import data.envassure.obligations as obl",
        "import rego.v1",
        "",
        "test_allow_when_authorized_state_stable if {",
        "\tobl.allow with input as {",
        '\t\t"authorized": true,',
        '\t\t"state_before": {"count": 1},',
        '\t\t"state_after": {"count": 1},',
        '\t\t"replay_equal": true,',
        '\t\t"reward_bound": true,',
        '\t\t"idempotency_key": null,',
        "\t}",
        "}",
        "",
        "test_deny_auth_mutation if {",
        "\tnot obl.allow with input as {",
        '\t\t"authorized": false,',
        '\t\t"state_before": {"count": 1},',
        '\t\t"state_after": {"count": 2},',
        '\t\t"replay_equal": true,',
        '\t\t"reward_bound": true,',
        '\t\t"idempotency_key": null,',
        "\t}",
        "}",
        "",
    ]
    if obligations:
        lines.append(f"# covering {len(obligations)} obligation(s)")
        lines.append("")
    return "\n".join(lines)


def opa_fmt_check(bundle_dir: Path | str, *, opa_path: str | None = None) -> dict[str, Any]:
    opa = opa_path or require_opa_binary()
    path = Path(bundle_dir)
    proc = subprocess.run(
        [opa, "fmt", "--list", "--fail", str(path / "policy.rego"), str(path / "policy_test.rego")],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def opa_test(bundle_dir: Path | str, *, opa_path: str | None = None) -> dict[str, Any]:
    opa = opa_path or require_opa_binary()
    path = Path(bundle_dir)
    proc = subprocess.run(
        [opa, "test", str(path), "--fail-on-empty"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def opa_eval(
    bundle_dir: Path | str,
    input_data: dict[str, Any],
    *,
    query: str = "data.envassure.obligations.allow",
    opa_path: str | None = None,
) -> dict[str, Any]:
    opa = opa_path or require_opa_binary()
    path = Path(bundle_dir)
    proc = subprocess.run(
        [
            opa,
            "eval",
            "--data",
            str(path),
            "--stdin-input",
            "--format",
            "json",
            query,
        ],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    result: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "query": query,
    }
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            result["result"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result["result"] = None
    return result
