"""Pydantic models for Environment Assurance IR (§10)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.ir.primitives import (
    IR_VERSION,
    AmbiguityStatus,
    ConstraintExpr,
    DeterminismClass,
    FailureCategory,
    ProvenanceRef,
    StateTypeName,
    VerifierStatus,
)


class StateVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: StateTypeName
    constraints: list[ConstraintExpr] = Field(default_factory=list)
    owning_aggregate: str | None = None
    initial_generator: str | None = None
    persistence: Literal["ephemeral", "session", "durable"] = "session"
    reset_class: Literal["reset_on_episode", "carry_forward", "external"] = "reset_on_episode"
    mutation_authority: list[str] = Field(default_factory=list)
    mutability: Literal["immutable", "mutable", "append_only"] = "mutable"
    confidentiality: Literal["public", "internal", "confidential", "restricted"] = "internal"
    policy_visible: bool = True
    evaluator_visible: bool = False
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)
    uncertainty: str | None = None
    derived_expression: str | None = None
    enum_values: list[str] | None = None
    record_fields: dict[str, str] | None = None


class ObservationProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    target_actor_class: str
    visible_paths: list[str] = Field(default_factory=list)
    omitted_paths: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    aggregation: str | None = None
    delay: str | None = None
    noise: str | None = None
    staleness: str | None = None
    access_control: str | None = None
    information_flow_labels: list[str] = Field(default_factory=list)
    error_policy: str | None = None
    side_channel_policy: str | None = None
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class ActorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    actor_class: str
    identity_model: str = "named"
    roles: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    credentials: list[str] = Field(default_factory=list)
    authority_source: str | None = None
    delegation_rules: list[str] = Field(default_factory=list)
    revocation_rules: list[str] = Field(default_factory=list)
    observation_projection_id: str | None = None
    available_actions: list[str] = Field(default_factory=list)
    lifecycle: str = "episode"
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class FailureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: FailureCategory
    description: str
    changes_authoritative_state: bool = False
    retryable: bool = False
    exposes_evidence: bool = True
    transaction_effect: Literal["none", "abort", "partial", "commit"] = "none"
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class ActionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str = "1"
    actor_classes: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[ConstraintExpr] = Field(default_factory=list)
    authorization: str | None = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    intended_effects: list[str] = Field(default_factory=list)
    external_side_effects: list[str] = Field(default_factory=list)
    resource_effects: list[str] = Field(default_factory=list)
    evidence_emitted: list[str] = Field(default_factory=list)
    success_outcomes: list[str] = Field(default_factory=list)
    failure_ids: list[str] = Field(default_factory=list)
    timeout_behavior: str | None = None
    retry_behavior: str | None = None
    idempotency: str | None = None
    transaction_boundary: str | None = None
    compensation_action: str | None = None
    concurrency: str | None = None
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)
    unsupported_semantics: list[str] = Field(default_factory=list)


class TransitionBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    probability: float | None = None
    probability_source: str | None = None
    events: list[str] = Field(default_factory=list)
    side_effect_intents: list[str] = Field(default_factory=list)
    observation: str | None = None
    terminal: bool = False


class TransitionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    action_id: str
    guard: ConstraintExpr | None = None
    priority: int = 0
    conflict_semantics: str = "priority"
    kind: Literal["deterministic", "stochastic"] = "deterministic"
    branches: list[TransitionBranch] = Field(default_factory=list)
    emitted_evidence: list[str] = Field(default_factory=list)
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)
    unsupported_assumptions: list[str] = Field(default_factory=list)


class VerifierClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    required_evidence: list[str] = Field(default_factory=list)
    mechanism: Literal[
        "predicate",
        "execution",
        "temporal",
        "authority",
        "solver",
        "model_judged",
    ] = "predicate"
    decision_rule: str
    abstention_conditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    applicability: str | None = None
    false_positive_risks: list[str] = Field(default_factory=list)
    status: VerifierStatus = "candidate"
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class TaskTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    family: str
    initial_constraints: list[ConstraintExpr] = Field(default_factory=list)
    actor_assignment: dict[str, str] = Field(default_factory=dict)
    intent: str
    goal_claims: list[str] = Field(default_factory=list)
    prohibited_behavior: list[str] = Field(default_factory=list)
    process_requirements: list[str] = Field(default_factory=list)
    horizon: int | None = None
    resource_budget: dict[str, Any] = Field(default_factory=dict)
    permitted_tools: list[str] = Field(default_factory=list)
    verifier_claim_ids: list[str] = Field(default_factory=list)
    solvability_method: str | None = None
    difficulty_factors: list[str] = Field(default_factory=list)
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class EvidenceObligation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    trigger: str
    evidence_class: str
    producer: str
    consumer: str
    generation_time: str = "on_action"
    integrity: str = "hash_chained"
    retention: str = "pack_lifetime"
    failure_behavior: str = "fail_closed"
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class AmbiguityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subject: str
    source_excerpts: list[str] = Field(default_factory=list)
    conflict_class: str
    candidate_interpretations: list[str] = Field(default_factory=list)
    default_prohibition: str
    affected_actions: list[str] = Field(default_factory=list)
    affected_tasks: list[str] = Field(default_factory=list)
    affected_verifiers: list[str] = Field(default_factory=list)
    affected_analyses: list[str] = Field(default_factory=list)
    operational_consequence: str
    required_expert_role: str
    status: AmbiguityStatus = "open"
    decision_id: str | None = None
    residual_uncertainty: str | None = None
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)


class WorldDefinition(BaseModel):
    """Top-level Environment Assurance IR document."""

    model_config = ConfigDict(extra="forbid")

    ir_version: str = IR_VERSION
    environment_id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    domain: str = "generic"
    # IR 0.2.0 additive field: named assurance profile for packs/reports.
    assurance_profile: str = "baseline"
    task_families: list[str] = Field(default_factory=list)
    semantic_sources: list[str] = Field(default_factory=list)
    # IR 0.2.0 normalized default (was ``"1"`` in 0.1.0).
    state_model_version: str = "1.0"
    clock_model: str = "discrete_steps"
    stochasticity_model: str = "none"
    reset_semantics: str = "full_reset"
    termination_semantics: str = "goal_or_horizon"
    truncation_semantics: str = "horizon"
    concurrency_model: str = "single_actor"
    transaction_model: str = "none"
    external_dependencies: list[str] = Field(default_factory=list)
    confidentiality_boundaries: list[str] = Field(default_factory=list)
    declared_fidelity_level: str = "EF-0"
    known_unsupported_behavior: list[str] = Field(default_factory=list)
    permissible_uses: list[str] = Field(default_factory=list)
    determinism: DeterminismClass = "fully_deterministic"
    state: list[StateVariable] = Field(default_factory=list)
    actors: list[ActorDefinition] = Field(default_factory=list)
    observations: list[ObservationProjection] = Field(default_factory=list)
    actions: list[ActionContract] = Field(default_factory=list)
    failures: list[FailureDefinition] = Field(default_factory=list)
    transitions: list[TransitionRule] = Field(default_factory=list)
    tasks: list[TaskTemplate] = Field(default_factory=list)
    verifiers: list[VerifierClaim] = Field(default_factory=list)
    evidence_obligations: list[EvidenceObligation] = Field(default_factory=list)
    ambiguities: list[AmbiguityRecord] = Field(default_factory=list)
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)

    def index_actions(self) -> dict[str, ActionContract]:
        return {a.id: a for a in self.actions}

    def index_state(self) -> dict[str, StateVariable]:
        return {s.id: s for s in self.state}

    def index_actors(self) -> dict[str, ActorDefinition]:
        return {a.id: a for a in self.actors}

    def content_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
