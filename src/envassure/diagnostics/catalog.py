"""Diagnostic family documentation and catalog registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from envassure.diagnostics.models import Severity


@dataclass(frozen=True, slots=True)
class DiagnosticDefinition:
    """Catalog entry for a diagnostic code. Every shipped code must be listed."""

    code: str
    severity: Severity
    summary_template: str
    family: str
    documentation: str
    consequence: str | None = None
    suggested_repair: str | None = None


def _def(
    code: str,
    severity: Severity,
    summary_template: str,
    family: str,
    documentation: str,
    *,
    consequence: str | None = None,
    suggested_repair: str | None = None,
) -> DiagnosticDefinition:
    return DiagnosticDefinition(
        code=code,
        severity=severity,
        summary_template=summary_template,
        family=family,
        documentation=documentation,
        consequence=consequence,
        suggested_repair=suggested_repair,
    )


# Family overview (always documented even when empty of concrete codes).
FAMILY_DOCS: Mapping[str, str] = {
    "EAC1xxx": "Source ingestion and SourceArtifact validation.",
    "EAC2xxx": "Semantic conflicts between sources and facts.",
    "EAC3xxx": "IR validation and reference integrity.",
    "EAC4xxx": "State and transition analysis.",
    "EAC5xxx": "Observation and information-flow analysis.",
    "EAC6xxx": "Task and verifier generation.",
    "EAC7xxx": "Differential validation.",
    "EAC8xxx": "Packaging, workspace, lock, and reproducibility.",
    "EAC9xxx": "Plugin, CLI, compatibility, and toolchain issues.",
}


DIAGNOSTIC_CATALOG: dict[str, DiagnosticDefinition] = {
    # --- EAC1xxx source ingestion ---
    "EAC1001": _def(
        "EAC1001",
        Severity.ERROR,
        "Source artifact `{source_id}` is invalid: {reason}",
        "EAC1xxx",
        "Raised when a SourceArtifact fails schema or authority vocabulary checks.",
        consequence="The source cannot be ingested or locked.",
        suggested_repair="Fix sources.yml / SourceArtifact fields and re-run import.",
    ),
    "EAC1002": _def(
        "EAC1002",
        Severity.ERROR,
        "Unknown source authority class `{authority}`",
        "EAC1xxx",
        "Authority must be one of the controlled vocabulary values.",
        consequence="Source is rejected.",
        suggested_repair="Use a documented authority class (e.g. api_contract).",
    ),
    "EAC1003": _def(
        "EAC1003",
        Severity.WARNING,
        "Source `{source_id}` declares completeness `{completeness}`",
        "EAC1xxx",
        "Informational warning when a source is marked incomplete or unknown.",
        consequence="Downstream facts may be partial.",
        suggested_repair="Update completeness when additional evidence is available.",
    ),
    "EAC1004": _def(
        "EAC1004",
        Severity.ERROR,
        "Failed to parse source `{path}`: {reason}",
        "EAC1xxx",
        "A source adapter could not parse the artifact (syntax, schema, or unsupported form).",
        consequence="No facts are emitted from this source; import fails closed.",
        suggested_repair="Fix the source artifact or choose the correct adapter kind.",
    ),
    "EAC1005": _def(
        "EAC1005",
        Severity.ERROR,
        "Unknown source adapter kind `{kind}`",
        "EAC1xxx",
        "import_source was called with a kind that has no registered adapter.",
        consequence="Import aborted.",
        suggested_repair="Use one of: openapi, database, policy, procedure, traces.",
    ),
    "EAC1006": _def(
        "EAC1006",
        Severity.WARNING,
        "Unsupported OpenAPI feature `{feature}` on `{subject}`: {reason}",
        "EAC1xxx",
        "The OpenAPI adapter detected a construct outside its supported matrix.",
        consequence=(
            "Facts for the supported subset are still emitted; unsupported "
            "constructs are not projected into authoritative semantics."
        ),
        suggested_repair=(
            "Simplify the construct, supply complementary sources, or record "
            "an expert decision for the unsupported semantics."
        ),
    ),
    # --- EAC2xxx semantic conflicts ---
    "EAC2001": _def(
        "EAC2001",
        Severity.WARNING,
        "Open ambiguity `{ambiguity_id}` remains unresolved",
        "EAC2xxx",
        "An AmbiguityRecord is still open; release builds should fail, development may warn.",
        consequence="Release-grade packs are blocked until decided.",
        suggested_repair="Run `eac decide` and record an expert decision.",
    ),
    "EAC2002": _def(
        "EAC2002",
        Severity.ERROR,
        "Semantic conflict on `{subject}`: {reason}",
        "EAC2xxx",
        "Reconciliation detected conflicting facts that require an expert decision.",
        consequence="IR projection is incomplete for the conflicting subject.",
        suggested_repair="Inspect ambiguities and record a decision.",
    ),
    "EAC2003": _def(
        "EAC2003",
        Severity.WARNING,
        "Alias detected for `{subject}`: {reason}",
        "EAC2xxx",
        "Multiple subject identifiers appear to name the same entity.",
        consequence="Downstream IR may duplicate or miss bindings until aliases are resolved.",
        suggested_repair="Record a decision consolidating aliases, or add an alias fact.",
    ),
    "EAC2004": _def(
        "EAC2004",
        Severity.ERROR,
        "Unknown or closed ambiguity `{ambiguity_id}`",
        "EAC2xxx",
        "A decision was applied to an ambiguity that does not exist or is not open.",
        consequence="Decision is rejected; ambiguity state unchanged.",
        suggested_repair="List open ambiguities and choose a valid ambiguity id.",
    ),
    # --- EAC3xxx IR validation ---
    "EAC3001": _def(
        "EAC3001",
        Severity.ERROR,
        "Invalid world definition: {reason}",
        "EAC3xxx",
        "Top-level WorldDefinition failed basic integrity checks.",
        consequence="IR cannot be compiled.",
        suggested_repair="Fix the world metadata and re-validate.",
    ),
    "EAC3002": _def(
        "EAC3002",
        Severity.ERROR,
        "Broken IR reference: {reason}",
        "EAC3xxx",
        "An IR element references an unknown id.",
        consequence="Static analysis and codegen are unsafe.",
        suggested_repair="Add the missing element or fix the reference.",
    ),
    "EAC3003": _def(
        "EAC3003",
        Severity.ERROR,
        "Duplicate IR identifier: {reason}",
        "EAC3xxx",
        "Two IR elements share the same id within a collection.",
        consequence="Indexes and digests are ambiguous.",
        suggested_repair="Rename one of the colliding identifiers.",
    ),
    "EAC3004": _def(
        "EAC3004",
        Severity.ERROR,
        "Unsupported IR version `{version}` (compiler writes `{current}`)",
        "EAC3xxx",
        "IR document version is outside the supported read window for this compiler.",
        consequence="Load/migrate fails closed; verify never silently rewrites IR.",
        suggested_repair="Run `eac migrate` with a compiler that supports this version, or regenerate IR.",
    ),
    "EAC3005": _def(
        "EAC3005",
        Severity.NOTE,
        "IR migrate status: `{version}`",
        "EAC3xxx",
        "Explicit migrate completed as a no-op (already current) or wrote an upgraded document.",
        consequence="No silent rewrite occurred outside `eac migrate`.",
        suggested_repair="Re-run lint/analyze after a non-trivial migration.",
    ),
    "EAC3006": _def(
        "EAC3006",
        Severity.ERROR,
        "IR migrate transform `{from_version}` -> `{to_version}` failed: {reason}",
        "EAC3xxx",
        "An explicit cross-minor transform could not be applied or produced an invalid document path.",
        consequence="No IR rewrite is written; caller must fix the source document or upgrade the compiler.",
        suggested_repair="Inspect the document against the 0.1.0→0.2.0 delta and re-run `eac migrate`.",
    ),
    "EAC3007": _def(
        "EAC3007",
        Severity.ERROR,
        "Release readiness gate failed ({profile}): {reason}",
        "EAC3xxx",
        "Validation pipeline v2 rejected the world under the selected release profile.",
        consequence="Lint/pack gates fail closed; the IR must not be treated as release-ready.",
        suggested_repair="Resolve blocking diagnostics or choose a weaker profile for authoring only.",
    ),
    # --- EAC4xxx state/transition ---
    "EAC4001": _def(
        "EAC4001",
        Severity.ERROR,
        "Transition analysis failure: {reason}",
        "EAC4xxx",
        "A transition rule is incomplete or inconsistent.",
        consequence="Runtime generation cannot proceed for this rule.",
        suggested_repair="Add branches or fix the guard/action binding.",
    ),
    "EAC4002": _def(
        "EAC4002",
        Severity.WARNING,
        "Reachability/solvability issue: {reason}",
        "EAC4xxx",
        "Bounded action-graph BFS could not establish solvability for a task or action.",
        consequence="Release-grade tasks may be unsolvable or overconstrained.",
        suggested_repair="Widen available actions, relax guards, or raise the BFS bound.",
    ),
    "EAC4003": _def(
        "EAC4003",
        Severity.WARNING,
        "Reset integrity issue: {reason}",
        "EAC4xxx",
        "State reset_class disagrees with world reset_semantics or episode boundaries.",
        consequence="Episode resets may leave residual or drop required carry-forward state.",
        suggested_repair="Align reset_class on state variables with reset_semantics.",
    ),
    "EAC4004": _def(
        "EAC4004",
        Severity.ERROR,
        "Authority/delegation issue: {reason}",
        "EAC4xxx",
        "Action authorization cannot be discharged by any actor's authority or delegation.",
        consequence="Permissioned actions may be unreachable or incorrectly authorized.",
        suggested_repair="Set actor authority_source / delegation_rules or fix authorization.",
    ),
    "EAC4005": _def(
        "EAC4005",
        Severity.NOTE,
        "Resource conservation hint: {reason}",
        "EAC4xxx",
        "resource_counter mutations lack an explicit conservation or budget declaration.",
        consequence="Resource invariants are unchecked without further evidence.",
        suggested_repair="Add resource_effects or a conservation verifier claim.",
    ),
    "EAC4006": _def(
        "EAC4006",
        Severity.WARNING,
        "Transaction/retry consistency: {reason}",
        "EAC4xxx",
        "Timeout, retry, compensation, or transaction_boundary fields are inconsistent.",
        consequence="Failure recovery semantics are ambiguous.",
        suggested_repair="Align timeout_behavior, retry_behavior, and transaction_boundary.",
    ),
    "EAC4007": _def(
        "EAC4007",
        Severity.WARNING,
        "Termination integrity: {reason}",
        "EAC4xxx",
        "Task horizon / termination_semantics disagree with terminal transition branches.",
        consequence="Episodes may never terminate or terminate without declared semantics.",
        suggested_repair="Mark terminal branches or adjust horizon / termination_semantics.",
    ),
    "EAC4008": _def(
        "EAC4008",
        Severity.ERROR,
        "Mutation scope violation: {reason}",
        "EAC4xxx",
        "An action writes state outside the declared mutation_authority surface, "
        "or mutates an immutable variable.",
        consequence="State ownership and authority invariants are violated.",
        suggested_repair="Add the action to mutation_authority or remove the write path.",
    ),
    "EAC4009": _def(
        "EAC4009",
        Severity.WARNING,
        "Unreachable action: {reason}",
        "EAC4xxx",
        "An action is declared but never reachable from actor seeds under the "
        "bounded action/transition graph (dataflow + availability edges).",
        consequence="Dead actions inflate the environment surface without solvability.",
        suggested_repair="Wire available_actions / actor_classes or remove the dead action.",
    ),
    "EAC4010": _def(
        "EAC4010",
        Severity.ERROR,
        "Precondition/guard reference issue: {reason}",
        "EAC4xxx",
        "Action preconditions or transition guards reference unknown state variables "
        "or are otherwise unsatisfiable given declared writers.",
        consequence="Runtime evaluation of guards/preconditions is undefined.",
        suggested_repair="Fix constraint expressions to reference known state ids.",
    ),
    "EAC4027": _def(
        "EAC4027",
        Severity.ERROR,
        "Retry semantics are undefined for action `{action_id}`",
        "EAC4xxx",
        "Timeout behavior is declared without retry semantics.",
        consequence="Timeout/retry tasks and verifiers are unsafe.",
        suggested_repair="Define retry_behavior or remove timeout_behavior.",
    ),
    # --- EAC5xxx observation ---
    "EAC5001": _def(
        "EAC5001",
        Severity.ERROR,
        "Observation/information-flow issue: {reason}",
        "EAC5xxx",
        "Observation projections reference invalid state or leak evaluator paths.",
        consequence="Partial observability guarantees are invalid.",
        suggested_repair="Fix visible_paths or observation bindings.",
    ),
    "EAC5002": _def(
        "EAC5002",
        Severity.ERROR,
        "Information-flow leak: evaluator_visible state `{state_id}` appears in "
        "policy observation `{observation_id}`",
        "EAC5xxx",
        "A state variable marked evaluator_visible (and not policy_visible) is exposed "
        "via a policy-facing observation projection.",
        consequence="Agents may observe hidden-oracle state; verifiers and tasks are tainted.",
        suggested_repair="Remove the path from visible_paths or mark the state policy_visible.",
    ),
    "EAC5003": _def(
        "EAC5003",
        Severity.WARNING,
        "Declared information-flow mapping issue: {reason}",
        "EAC5xxx",
        "Observation visible/omitted paths or information_flow_labels disagree with "
        "state visibility/confidentiality declarations.",
        consequence="Partial-observability claims are inconsistent with declared mappings.",
        suggested_repair="Align visible_paths, omitted_paths, labels, and access_control.",
    ),
    "EAC5004": _def(
        "EAC5004",
        Severity.ERROR,
        "Unsupported observation semantic: {reason}",
        "EAC5xxx",
        "An ObservationProjection declares delay, noise, staleness, side-channel, "
        "aggregation, transformation, or related semantics that the runtime cannot execute.",
        consequence=(
            "Executable/release profiles reject the IR; runtime observe() never "
            "silently ignores unsupported fields."
        ),
        suggested_repair=(
            "Remove the unsupported field, replace with a supported form, or mark "
            "the behavior in known_unsupported_behavior and use a non-executable profile."
        ),
    ),
    "EAC5005": _def(
        "EAC5005",
        Severity.ERROR,
        "Observation projection missing or unsafe: {reason}",
        "EAC5xxx",
        "An actor lacks a bound observation projection, references an unknown "
        "projection, or would otherwise observe unrestricted authoritative state.",
        consequence=(
            "Fail-closed observe() returns an empty projection; release gates block "
            "full-state leakage."
        ),
        suggested_repair=(
            "Bind every policy actor to a declared ObservationProjection with an "
            "explicit visible_paths allow-list."
        ),
    ),
    # --- EAC6xxx tasks/verifiers ---
    "EAC6001": _def(
        "EAC6001",
        Severity.WARNING,
        "Task/verifier generation note: {reason}",
        "EAC6xxx",
        "Task or verifier construction produced a soft issue.",
        consequence="Generated tasks may need review.",
        suggested_repair="Inspect the task/verifier and adjust templates.",
    ),
    "EAC6002": _def(
        "EAC6002",
        Severity.ERROR,
        "Hidden-oracle leakage in verifier `{verifier_id}`: {reason}",
        "EAC6xxx",
        "A verifier that claims policy-only evidence references evaluator_visible state.",
        consequence="Verifier status cannot advance beyond draft for release packs.",
        suggested_repair="Restrict the decision_rule to policy_visible evidence paths.",
    ),
    "EAC6003": _def(
        "EAC6003",
        Severity.NOTE,
        "Solve-verify asymmetry: {reason}",
        "EAC6xxx",
        "Task solvability method uncertainty is mirrored by the attached verifier.",
        consequence="Passing verification may not imply independent confirmation.",
        suggested_repair="Use an independent verifier mechanism or lower claim status.",
    ),
    # --- EAC7xxx differential ---
    "EAC7001": _def(
        "EAC7001",
        Severity.ERROR,
        "Differential validation failure: {reason}",
        "EAC7xxx",
        "Reference connector comparison found a dimension mismatch.",
        consequence="Pack cannot claim differential validation.",
        suggested_repair="Inspect the counterexample and refine IR or connector tolerances.",
    ),
    "EAC7002": _def(
        "EAC7002",
        Severity.NOTE,
        "Stochastic comparison uses statistical conformance: {reason}",
        "EAC7xxx",
        "Binary equality is inappropriate for stochastic transition rules on small samples.",
        consequence="Differential results report confidence intervals, not exact match.",
        suggested_repair="Increase sample size or tighten declared distribution tolerances.",
    ),
    "EAC7003": _def(
        "EAC7003",
        Severity.WARNING,
        "Counterexample minimized: {reason}",
        "EAC7xxx",
        "Delta-debugging reduced a failing probe sequence while preserving the mismatch.",
        consequence="Refinement should target the minimized counterexample.",
        suggested_repair="Feed the minimized CE into reconciliation (CEGR).",
    ),
    "EAC7004": _def(
        "EAC7004",
        Severity.WARNING,
        "CEGR intake skipped proposals: {reason}",
        "EAC7xxx",
        "Counterexample intake did not preserve the failure; refinement proposals are withheld.",
        consequence="No corrected facts or transition patches are emitted from this intake.",
        suggested_repair="Re-minimize with a predicate that preserves the failure, then re-run refine.",
    ),
    "EAC7005": _def(
        "EAC7005",
        Severity.NOTE,
        "CEGR refinement applied: {reason}",
        "EAC7xxx",
        "Counterexample-guided reconciliation produced ambiguities and optional corrections.",
        consequence="Open ambiguities block release-grade differential claims until decided.",
        suggested_repair="Review generation under validation/refinements/ and run eac decide.",
    ),
    "EAC7006": _def(
        "EAC7006",
        Severity.WARNING,
        "Differential dimension indeterminate: {reason}",
        "EAC7xxx",
        "A required comparison dimension lacks evidence or is underpowered.",
        consequence=(
            "Overall differential pass is blocked; missing or underpowered "
            "evidence is never treated as a match."
        ),
        suggested_repair=(
            "Supply the missing dimension evidence, increase sample size, or "
            "declare the dimension not applicable for the probe."
        ),
    ),
    "EAC7007": _def(
        "EAC7007",
        Severity.NOTE,
        "CEGR closed on evidence: {reason}",
        "EAC7xxx",
        "CEGR v2 closed a refinement generation only after replay evidence matched.",
        consequence="Generation is immutable; residual expert decisions remain auditable.",
        suggested_repair="Verify accepted_facts and pack claims cite this generation digest.",
    ),
    "EAC7008": _def(
        "EAC7008",
        Severity.WARNING,
        "CEGR remains open: {reason}",
        "EAC7xxx",
        "CEGR v2 did not close; indeterminate or mismatched evidence blocks closure.",
        consequence="Release IR must not absorb preferred_facts; expert decide() required.",
        suggested_repair="Replay both systems, resolve ambiguities, or mark unsupported semantics.",
    ),
    "EAC8007": _def(
        "EAC8007",
        Severity.NOTE,
        "Incremental rebuild skipped unchanged sources: {reason}",
        "EAC8xxx",
        "Source digests match build-state; IR rebuild was a no-op.",
        consequence="Existing IR artifacts are reused.",
        suggested_repair="Pass --force to rebuild regardless of digests.",
    ),
    "EAC8008": _def(
        "EAC8008",
        Severity.NOTE,
        "Incremental lint skipped unchanged IR: {reason}",
        "EAC8xxx",
        "IR file digest matches the last successful lint recorded in build-state.",
        consequence="Prior lint result is reused without reprocessing.",
        suggested_repair="Pass --force to lint regardless of digests.",
    ),
    # --- EAC8xxx workspace / packaging ---
    "EAC8001": _def(
        "EAC8001",
        Severity.ERROR,
        "Not an EnvAssure workspace: missing `{path}`",
        "EAC8xxx",
        "The current directory (or --path) does not contain required workspace files.",
        consequence="Workspace commands cannot proceed.",
        suggested_repair="Run `eac init` or pass the correct workspace path.",
    ),
    "EAC8002": _def(
        "EAC8002",
        Severity.ERROR,
        "Workspace already exists at `{path}`",
        "EAC8xxx",
        "Refusing to overwrite an existing eac.toml unless --force is set.",
        consequence="Init aborted.",
        suggested_repair="Choose another directory or pass --force carefully.",
    ),
    "EAC8003": _def(
        "EAC8003",
        Severity.ERROR,
        "Invalid workspace configuration: {reason}",
        "EAC8xxx",
        "eac.toml or sources.yml failed validation.",
        consequence="Workspace cannot be loaded.",
        suggested_repair="Fix the configuration according to the schema.",
    ),
    "EAC8004": _def(
        "EAC8004",
        Severity.ERROR,
        "Lock inconsistency: {reason}",
        "EAC8xxx",
        "`.eac/lock.json` digests or versions disagree with workspace state.",
        consequence="Reproducible builds cannot be trusted.",
        suggested_repair="Regenerate the lock after intentional changes, or restore sources.",
    ),
    "EAC8005": _def(
        "EAC8005",
        Severity.ERROR,
        "Failed to write workspace file `{path}`: {reason}",
        "EAC8xxx",
        "Filesystem error while creating or updating workspace artifacts.",
        consequence="Workspace may be partial.",
        suggested_repair="Check permissions and disk space, then retry.",
    ),
    "EAC8006": _def(
        "EAC8006",
        Severity.ERROR,
        "Pack verification failed: {reason}",
        "EAC8xxx",
        "Environment Pack checksums, schema, or secret scan failed.",
        consequence="Pack must not be trusted or published.",
        suggested_repair="Rebuild the pack after fixing the reported issue.",
    ),
    # --- EAC9xxx toolchain / CLI ---
    "EAC9001": _def(
        "EAC9001",
        Severity.ERROR,
        "Command `{command}` is not implemented yet",
        "EAC9xxx",
        "Fail-closed stub for a registered CLI command that has no implementation.",
        consequence="The process exits non-zero; no partial success is implied.",
        suggested_repair="Upgrade envassure when the feature ships, or track the EAC PR.",
    ),
    "EAC9002": _def(
        "EAC9002",
        Severity.ERROR,
        "Unsupported Python version {version}; require >= {minimum}",
        "EAC9xxx",
        "Doctor / runtime gate for unsupported interpreters.",
        consequence="Toolchain checks fail.",
        suggested_repair="Install Python 3.11 or 3.12.",
    ),
    "EAC9003": _def(
        "EAC9003",
        Severity.WARNING,
        "Optional extra `{extra}` is not installed",
        "EAC9xxx",
        "Optional dependency group missing; related features unavailable.",
        consequence="Features behind that extra cannot run.",
        suggested_repair="Install with `pip install 'envassure[{extra}]'`.",
    ),
    "EAC9004": _def(
        "EAC9004",
        Severity.NOTE,
        "Network checks skipped (opt-in only)",
        "EAC9xxx",
        "Doctor does not contact the network unless --network is passed.",
        consequence="Remote availability is unverified.",
        suggested_repair="Pass --network only on trusted networks when needed.",
    ),
    "EAC9005": _def(
        "EAC9005",
        Severity.ERROR,
        "Internal error: {reason}",
        "EAC9xxx",
        "Unexpected failure; indicates a bug or environmental fault.",
        consequence="Command aborted.",
        suggested_repair="Retry; if persistent, file a bug with the diagnostic JSON.",
    ),
    "EAC9006": _def(
        "EAC9006",
        Severity.ERROR,
        "Plugin error: {reason}",
        "EAC9xxx",
        "Plugin load, API compatibility, or allowlist failure.",
        consequence="Plugin features are unavailable.",
        suggested_repair="Update the plugin lock or allowlist.",
    ),
}


def get_definition(code: str) -> DiagnosticDefinition:
    try:
        return DIAGNOSTIC_CATALOG[code]
    except KeyError as exc:
        raise KeyError(f"Undocumented diagnostic code: {code}") from exc


def iter_catalog() -> Iterable[DiagnosticDefinition]:
    return DIAGNOSTIC_CATALOG.values()


def require_documented(code: str) -> None:
    """Raise if a code is used without a catalog entry (100% documentation rule)."""
    if code not in DIAGNOSTIC_CATALOG:
        raise KeyError(
            f"Diagnostic code {code} is not in DIAGNOSTIC_CATALOG. "
            "Every shipped code must be documented."
        )


def family_of(code: str) -> str:
    if len(code) != 7 or not code.startswith("EAC"):
        raise ValueError(f"Invalid diagnostic code: {code}")
    return f"EAC{code[3]}xxx"
