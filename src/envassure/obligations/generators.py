"""Proof-obligation generators from Environment IR (EAC-R14)."""

from __future__ import annotations

from envassure.canonical import canonical_hash
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import WorldDefinition
from envassure.obligations.ir import ProofObligation, ProofObligationBundle


def compile_proof_obligations(world: WorldDefinition) -> ProofObligationBundle:
    """Compile backend-neutral proof obligations for *world*.

    Generators are soundness-oriented (what must be evidenced) and deliberately
    do not claim formal discharge. Unsupported conditions are recorded explicitly.
    """
    obligations: list[ProofObligation] = []
    obligations.extend(generate_authorization_preservation(world))
    obligations.extend(generate_resource_conservation(world))
    obligations.extend(generate_deterministic_reset_replay(world))
    obligations.extend(generate_observation_separation(world))
    obligations.extend(generate_reward_trace_binding(world))
    obligations.extend(generate_idempotency_safety(world))
    return ProofObligationBundle(
        environment_id=world.environment_id,
        ir_digest=canonical_hash(world.content_dict()),
        obligations=obligations,
        metadata={
            "generator": "envassure.obligations.generators",
            "obligation_count": len(obligations),
            "claim_kinds": sorted({o.claim_kind for o in obligations}),
        },
    )


def generate_authorization_preservation(world: WorldDefinition) -> list[ProofObligation]:
    """Denied / unauthorized actions must not mutate authoritative state."""
    out: list[ProofObligation] = []
    for action in world.actions:
        if not action.authorization and not action.failure_ids:
            continue
        unsupported: list[str] = []
        status = "generated"
        if action.authorization and "unsupported" in action.authorization.lower():
            unsupported.append(f"authorization expression unsupported: {action.authorization}")
            status = "unsupported"
        out.append(
            ProofObligation(
                id=f"obl.auth.preserve.{action.id}",
                claim=(
                    f"Action {action.id!r} preserves authorization: when authorization "
                    "fails or is denied, authoritative state and external effects remain unchanged."
                ),
                claim_kind="authorization_preservation",
                source_elements=[
                    f"action:{action.id}",
                    *(f"failure:{f}" for f in action.failure_ids),
                ],
                assumptions=[
                    "Runtime uses fail-closed authorization compilation.",
                    "Audit/denial events may append; authoritative entity state must not.",
                ],
                domains=["authorization", "runtime", "audit"],
                backend_requirements=[
                    "runtime_engine_event_sourced",
                    "authorization_ast_fail_closed",
                ],
                expected_evidence=[
                    "denial_audit_event",
                    "pre_post_state_digest_equal_on_deny",
                    "differential.authorization",
                ],
                unsupported_conditions=unsupported,
                status=status,  # type: ignore[arg-type]
                mechanism_strength="runtime_checkable",
            )
        )
    if not out and world.actors:
        out.append(
            ProofObligation(
                id="obl.auth.preserve.world",
                claim=(
                    "World declares actors but no authorization-bearing actions; "
                    "authorization preservation is vacuously open pending action contracts."
                ),
                claim_kind="authorization_preservation",
                source_elements=[f"actor:{a.id}" for a in world.actors],
                assumptions=["No action.authorization compiled yet."],
                domains=["authorization"],
                backend_requirements=["ir_action_authorization"],
                expected_evidence=["action_authorization_declarations"],
                unsupported_conditions=["no_authorized_actions"],
                status="deferred",
                mechanism_strength="syntactic",
            )
        )
    return out


def generate_resource_conservation(world: WorldDefinition) -> list[ProofObligation]:
    """Resource counters / budgets must conserve under declared transitions."""
    resources = [
        s
        for s in world.state
        if s.type in {"resource_counter", "budget", "inventory"} or "resource" in s.type
    ]
    if not resources:
        return [
            ProofObligation(
                id="obl.resource.conservation.na",
                claim="No resource-typed state variables; conservation obligation not applicable.",
                claim_kind="resource_conservation",
                source_elements=[],
                assumptions=[],
                domains=["resources"],
                backend_requirements=[],
                expected_evidence=[],
                unsupported_conditions=["no_resource_state"],
                status="deferred",
                mechanism_strength="syntactic",
                notes="Not a discharged proof — absence of resources only.",
            )
        ]
    writers = sorted({auth for s in resources for auth in (s.mutation_authority or [])})
    unsupported: list[str] = []
    if world.transaction_model in {"none", ""}:
        unsupported.append("transaction_model=none; conservation checks are best-effort")
    return [
        ProofObligation(
            id="obl.resource.conservation",
            claim=(
                "Resource-typed state variables conserve under successful transitions: "
                "net change equals declared effects; failed/denied steps do not consume."
            ),
            claim_kind="resource_conservation",
            source_elements=[f"state:{s.id}" for s in resources] + [f"action:{a}" for a in writers],
            assumptions=[
                "Effects are compiled through the expression/runtime pipeline.",
                "External side effects that mint/burn resources are declared.",
            ],
            domains=["resources", "transitions", "transactions"],
            backend_requirements=["runtime_effect_accounting", "transition_postconditions"],
            expected_evidence=[
                "resource_balance_traces",
                "differential.state",
                "mutation_reset_integrity",
            ],
            unsupported_conditions=unsupported,
            status="unsupported"
            if unsupported and world.determinism == "externally_nondeterministic"
            else "generated",
            mechanism_strength="runtime_checkable",
        )
    ]


def generate_deterministic_reset_replay(world: WorldDefinition) -> list[ProofObligation]:
    """Reset + replay must reproduce digests for deterministic worlds."""
    unsupported: list[str] = []
    strength: str = "runtime_checkable"
    status = "generated"
    if world.determinism in {"statistical", "externally_nondeterministic"}:
        unsupported.append(
            f"determinism={world.determinism}; exact replay replaced by statistical bounds"
        )
        strength = "differential_evidence"
        if world.determinism == "externally_nondeterministic":
            status = "unsupported"
    return [
        ProofObligation(
            id="obl.reset.replay",
            claim=(
                "Given identical seed/config digests, reset followed by the same action "
                "sequence yields identical snapshot digests (or declared statistical bounds)."
            ),
            claim_kind="deterministic_reset_replay",
            source_elements=[
                f"environment:{world.environment_id}",
                f"reset:{world.reset_semantics}",
                f"determinism:{world.determinism}",
            ],
            assumptions=[
                "Snapshot v2 persists RNG, event heads, and policy digests.",
                "Non-strict mutate_state paths are excluded from release profile.",
            ],
            domains=["runtime", "snapshots", "replay"],
            backend_requirements=["snapshot_v2", "event_sourced_engine"],
            expected_evidence=[
                "snapshot_digest_equality",
                "replay_trace_hash",
                "differential.success",
            ],
            unsupported_conditions=unsupported,
            status=status,  # type: ignore[arg-type]
            mechanism_strength=strength,  # type: ignore[arg-type]
        )
    ]


def generate_observation_separation(world: WorldDefinition) -> list[ProofObligation]:
    """Policy observations must not leak evaluator-only / omitted paths."""
    if not world.observations:
        return [
            ProofObligation(
                id="obl.obs.separation.missing",
                claim="No observation projections declared; separation cannot be evidenced.",
                claim_kind="observation_separation",
                source_elements=[],
                assumptions=[],
                domains=["observations", "info_flow"],
                backend_requirements=["observation_projection_compiler"],
                expected_evidence=["observation_projection_declarations"],
                unsupported_conditions=["no_observation_projections"],
                status="unsupported",
                mechanism_strength="syntactic",
            )
        ]
    hidden = [s.id for s in world.state if s.evaluator_visible and not s.policy_visible]
    omitted = sorted({p for obs in world.observations for p in (obs.omitted_paths or [])})
    return [
        ProofObligation(
            id="obl.obs.separation",
            claim=(
                "Actor observation projections omit evaluator-only and declared omitted "
                "paths; leakage probes must not observe hidden fields."
            ),
            claim_kind="observation_separation",
            source_elements=[f"observation:{o.id}" for o in world.observations]
            + [f"state:{s}" for s in hidden],
            assumptions=[
                "compile_observation() rejects unsupported semantics (fail closed).",
                "project_state / observe() empty-on-deny (access deny => {}).",
                "Missing or unknown projection => empty observation (never full-state leak).",
            ],
            domains=["observations", "confidentiality", "info_flow"],
            backend_requirements=[
                "observation_projection_compiler",
                "compile_observation",
                "leakage_probes",
            ],
            expected_evidence=[
                "compile_observation",
                "observe.empty_on_deny",
                "observe.no_full_state_leak",
                "leakage_probe_results",
                "differential.observation",
                "benchmark.leakage",
            ],
            unsupported_conditions=[]
            if omitted or hidden
            else ["no_explicit_omitted_or_hidden_paths"],
            status="generated",
            mechanism_strength="differential_evidence",
            metadata={"omitted_paths": omitted, "hidden_state": hidden},
        )
    ]


def generate_reward_trace_binding(world: WorldDefinition) -> list[ProofObligation]:
    """Verifier / task rewards must bind to auditable traces, not free-floating scores."""
    verifiers = list(world.verifiers)
    tasks = list(world.tasks)
    if not verifiers and not tasks:
        return [
            ProofObligation(
                id="obl.reward.trace.na",
                claim="No tasks or verifiers; reward/trace binding not applicable.",
                claim_kind="reward_trace_binding",
                source_elements=[],
                assumptions=[],
                domains=["tasks", "verifiers"],
                backend_requirements=[],
                expected_evidence=[],
                unsupported_conditions=["no_tasks_or_verifiers"],
                status="deferred",
                mechanism_strength="syntactic",
            )
        ]
    unsupported: list[str] = []
    for v in verifiers:
        if not v.required_evidence:
            unsupported.append(f"verifier:{v.id} lacks required_evidence bindings")
    return [
        ProofObligation(
            id="obl.reward.trace.binding",
            claim=(
                "Task success and verifier accept/reject decisions bind to hash-linked "
                "action/audit traces; scores without trace digests are non-authoritative."
            ),
            claim_kind="reward_trace_binding",
            source_elements=[f"task:{t.id}" for t in tasks]
            + [f"verifier:{v.id}" for v in verifiers],
            assumptions=[
                "Pack claims cite trace digests, not model-judged scores alone.",
            ],
            domains=["tasks", "verifiers", "evidence", "packs"],
            backend_requirements=["audit_event_chain", "assurance_case_section_20"],
            expected_evidence=[
                "trace_digest",
                "verifier_evidence_refs",
                "assurance_case.claims",
            ],
            unsupported_conditions=unsupported,
            status="generated" if not unsupported else "open",
            mechanism_strength="differential_evidence",
        )
    ]


def generate_idempotency_safety(world: WorldDefinition) -> list[ProofObligation]:
    """Idempotent actions must not double-apply effects under replay."""
    out: list[ProofObligation] = []
    for action in world.actions:
        idem = (action.idempotency or "").strip().lower()
        if not idem or idem in {"none", "unsupported", "n/a"}:
            continue
        unsupported: list[str] = []
        status = "generated"
        if "unsupported" in idem:
            unsupported.append(f"idempotency mode unsupported: {action.idempotency}")
            status = "unsupported"
        out.append(
            ProofObligation(
                id=f"obl.idempotency.{action.id}",
                claim=(
                    f"Action {action.id!r} with idempotency={action.idempotency!r} "
                    "must yield equal authoritative state on keyed replay."
                ),
                claim_kind="idempotency_safety",
                source_elements=[f"action:{action.id}"],
                assumptions=[
                    "Clients supply stable idempotency keys when required by the mode.",
                    "Runtime records keyed receipts for replay comparison.",
                ],
                domains=["idempotency", "runtime", "differential"],
                backend_requirements=["runtime_engine_event_sourced", "opa_rego_v1"],
                expected_evidence=[
                    "idempotent_replay_equal",
                    "differential.idempotency",
                ],
                unsupported_conditions=unsupported,
                status=status,  # type: ignore[arg-type]
                mechanism_strength="runtime_checkable",
            )
        )
    if not out:
        out.append(
            ProofObligation(
                id="obl.idempotency.na",
                claim="No idempotent actions declared; idempotency safety not applicable.",
                claim_kind="idempotency_safety",
                source_elements=[],
                assumptions=[],
                domains=["idempotency"],
                backend_requirements=[],
                expected_evidence=[],
                unsupported_conditions=["no_idempotent_actions"],
                status="deferred",
                mechanism_strength="syntactic",
            )
        )
    return out


def validate_proof_obligations(
    bundle: ProofObligationBundle,
    *,
    world: WorldDefinition | None = None,
) -> DiagnosticReport:
    """Validate obligation bundle integrity (ids, kinds, overstatement guards).

    When *world* is provided, observation_separation obligations are checked
    against ``compile_observation`` / empty-on-deny / no full-state leak semantics.
    """
    report = DiagnosticReport(
        context={"environment_id": bundle.environment_id, "kind": "proof_obligations"}
    )
    seen: set[str] = set()
    for obl in bundle.obligations:
        if obl.id in seen:
            report.add(
                make_diagnostic(
                    "EAC3003",
                    reason=f"duplicate proof obligation id {obl.id!r}",
                    subject=obl.id,
                )
            )
        seen.add(obl.id)
        if obl.status == "discharged" and obl.mechanism_strength == "formal_unproven":
            report.add(
                make_diagnostic(
                    "EAC6003",
                    reason=(
                        f"obligation {obl.id!r} marked discharged with formal_unproven "
                        "strength — overstatement"
                    ),
                    subject=obl.id,
                )
            )
        if obl.mechanism_strength == "formal_unproven" and "formal_proof" in " ".join(
            obl.expected_evidence
        ):
            report.add(
                make_diagnostic(
                    "EAC6001",
                    reason=(
                        f"obligation {obl.id!r} expects formal_proof evidence but "
                        "mechanism_strength is formal_unproven"
                    ),
                    subject=obl.id,
                )
            )
    if world is not None and bundle.environment_id != world.environment_id:
        report.add(
            make_diagnostic(
                "EAC3002",
                reason=(
                    f"bundle environment_id {bundle.environment_id!r} != "
                    f"world {world.environment_id!r}"
                ),
                subject=bundle.environment_id,
            )
        )
    if world is not None and any(
        o.claim_kind == "observation_separation" for o in bundle.obligations
    ):
        report.extend(_assert_observation_separation_runtime(world).diagnostics)
    return report


def _assert_observation_separation_runtime(world: WorldDefinition) -> DiagnosticReport:
    """Assert R08 observe semantics for observation_separation obligations."""
    from envassure.ir.models import ActorDefinition
    from envassure.runtime.observations import (
        compile_observation,
        observe_or_empty,
        probe_observation_leaks,
        project_state,
    )

    report = DiagnosticReport(
        context={
            "environment_id": world.environment_id,
            "kind": "observation_separation_runtime",
        }
    )
    projections = {o.id: o for o in world.observations}
    state = {s.id: (s.initial_generator or s.id) for s in world.state}
    # Ensure evaluator-only keys are present so leak probes are meaningful.
    for s in world.state:
        state.setdefault(s.id, s.id)
    hidden = [s.id for s in world.state if s.evaluator_visible and not s.policy_visible]

    for proj in world.observations:
        compiled = compile_observation(proj, strict_unsupported=True)
        if not compiled.ok or compiled.compiled is None:
            for msg in compiled.unsupported or [f"observation {proj.id!r} failed to compile"]:
                report.add(
                    make_diagnostic(
                        "EAC5004",
                        reason=msg,
                        subject=proj.id,
                        affected_artifacts=[f"observation:{proj.id}"],
                    )
                )
            continue
        visible_roots = {p.split(".", 1)[0] for p in compiled.compiled.visible_paths}
        omitted_roots = {p.split(".", 1)[0] for p in compiled.compiled.omitted_paths}
        overlap = sorted(visible_roots & omitted_roots)
        for root in overlap:
            report.add(
                make_diagnostic(
                    "EAC5001",
                    reason=(
                        f"observation {proj.id!r} lists {root!r} as both visible "
                        "and omitted (separation violated)"
                    ),
                    subject=proj.id,
                )
            )
        # Empty-on-deny: access_control that fails must return {}.
        if compiled.compiled.access_control is not None:
            deny_actor = ActorDefinition(
                id="__deny_probe__",
                actor_class="__deny__",
                roles=[],
                observation_projection_id=proj.id,
            )
            denied = project_state(
                state,
                compiled.compiled,
                actor=deny_actor,
                actor_view={},
                auth_context={},
            )
            if denied:
                report.add(
                    make_diagnostic(
                        "EAC5005",
                        reason=(
                            f"observation {proj.id!r} access_control deny must yield "
                            f"empty observation; got keys {sorted(denied)}"
                        ),
                        subject=proj.id,
                        affected_artifacts=[f"observation:{proj.id}"],
                    )
                )

    for actor in world.actors:
        missing = (
            not actor.observation_projection_id
            or actor.observation_projection_id not in projections
        )
        obs = observe_or_empty(state, actor=actor, projections=projections)
        if missing:
            leaked = probe_observation_leaks(obs, missing_or_unknown_projection=True)
            if leaked:
                report.add(
                    make_diagnostic(
                        "EAC5005",
                        reason=(
                            f"actor {actor.id!r} missing/unknown projection must observe "
                            f"empty; leaked keys {leaked}"
                        ),
                        subject=actor.id,
                        affected_artifacts=[f"actor:{actor.id}"],
                    )
                )
            continue
        assert actor.observation_projection_id is not None
        forbidden = list(hidden) + list(projections[actor.observation_projection_id].omitted_paths)
        leaked = probe_observation_leaks(obs, forbidden_paths=forbidden)
        for path in leaked:
            report.add(
                make_diagnostic(
                    "EAC5001",
                    reason=(f"actor {actor.id!r} observation leaks forbidden path {path!r}"),
                    subject=actor.id,
                    details={"path": path},
                    affected_artifacts=[
                        f"actor:{actor.id}",
                        f"observation:{actor.observation_projection_id}",
                    ],
                )
            )
    return report


def proof_obligation_pack_members(bundle: ProofObligationBundle) -> dict[str, str]:
    """Pack-relative path → text for embedding obligations without overstating strength."""
    import json

    return {
        "obligations/proof-obligations.json": json.dumps(bundle.model_dump(mode="json"), indent=2)
        + "\n",
    }
