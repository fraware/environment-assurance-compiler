"""IR semantic validation (pipeline v2 entrypoint — EAC-R09)."""

from __future__ import annotations

from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import WorldDefinition
from envassure.ir.pipeline import (
    PIPELINE_PASSES,
    PipelineResult,
    ReleaseProfile,
    apply_profile_blocking,
    parse_release_profile,
    run_validation_pipeline,
)

__all__ = [
    "PIPELINE_PASSES",
    "PipelineResult",
    "ReleaseProfile",
    "apply_profile_blocking",
    "parse_release_profile",
    "run_validation_pipeline",
    "validate_world",
]


def validate_world(
    world: WorldDefinition,
    *,
    profile: str | ReleaseProfile = ReleaseProfile.AUTHORING,
    bfs_bound: int = 64,
) -> DiagnosticReport:
    """
    Validate a WorldDefinition under a release profile.

    Default profile is ``authoring`` (schema/refs/types) for backward-compatible
    SDK checks. Use ``executable`` / ``research_release`` for lint and pack gates.
    """
    return run_validation_pipeline(
        world,
        profile=profile,
        bfs_bound=bfs_bound,
    ).report
