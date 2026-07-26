"""Compile Environment IR into backend-neutral obligations and OPA bundles."""

from __future__ import annotations

from pathlib import Path

from envassure.ir.models import WorldDefinition
from envassure.obligations.backends.opa import OpaBackendError, emit_rego_v1_bundle
from envassure.obligations.generators import compile_proof_obligations
from envassure.obligations.ir import ProofObligationBundle


def compile_obligations(world: WorldDefinition) -> ProofObligationBundle:
    """Compile proof obligations for *world* (backend-neutral)."""
    return compile_proof_obligations(world)


def compile_opa_bundle(
    world: WorldDefinition,
    output_dir: Path | str,
    *,
    fail_on_unsupported: bool = True,
) -> tuple[ProofObligationBundle, Path]:
    """Compile obligations and emit a Rego v1 OPA bundle under *output_dir*.

    When *fail_on_unsupported* is true (default), any obligation marked
    ``unsupported`` aborts before writing files.
    """
    bundle = compile_obligations(world)
    if fail_on_unsupported:
        blocked = [o for o in bundle.obligations if o.status == "unsupported"]
        if blocked:
            raise OpaBackendError(
                "refusing OPA generation; unsupported obligations: "
                + ", ".join(o.id for o in blocked)
            )
    # Filter unsupported when fail_on_unsupported is False.
    if not fail_on_unsupported:
        bundle = bundle.model_copy(
            update={
                "obligations": [o for o in bundle.obligations if o.status != "unsupported"],
            }
        )
    path = emit_rego_v1_bundle(bundle, output_dir)
    return bundle, path
