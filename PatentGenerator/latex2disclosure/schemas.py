from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class EvidenceSpan(BaseModel):
    evidence_id: str
    source_file: str
    section: str
    text: str
    locator: str


class FigureRecord(BaseModel):
    label: str = ""
    caption: str
    source_file: str
    asset_path: str | None = None


class LatexPaper(BaseModel):
    root_file: str
    title: str
    abstract: str = ""
    sections: dict[str, str] = Field(default_factory=dict)
    equations: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    algorithms: list[str] = Field(default_factory=list)
    figures: list[FigureRecord] = Field(default_factory=list)
    bibliography: list[str] = Field(default_factory=list)
    plain_text: str
    source_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PaperUnderstanding(BaseModel):
    technical_field: str
    research_objective: str
    method_summary: str
    inputs: list[str] = Field(default_factory=list)
    workflow_steps: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    experimental_findings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TechnicalFeature(BaseModel):
    name: str
    description: str
    solved_problem: str
    technical_effect: str
    essential: bool = True
    evidence_ids: list[str] = Field(default_factory=list)


class InventionDisclosure(BaseModel):
    proposed_title: str
    technical_problem: list[str]
    inventive_concept: str
    features: list[TechnicalFeature]
    alternatives: list[str] = Field(default_factory=list)
    inventor_questions: list[str] = Field(default_factory=list)


class TechnicalSolution(BaseModel):
    system_boundary: str
    components: list[str]
    method_steps: list[str]
    data_flow: list[str]
    parameters_and_constraints: list[str] = Field(default_factory=list)
    alternative_paths: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    embodiments: list[str]
    experimental_support: list[str]
    figure_plan: list[str]
    evidence_mapping: dict[str, list[str]]
    unsupported_items: list[str] = Field(default_factory=list)


class TechnicalDisclosure(BaseModel):
    invention_title: str
    technical_field: str
    background: list[str]
    prior_art_defects: list[str]
    technical_problem: list[str]
    overall_solution: str
    detailed_steps: list[str]
    key_innovations: list[str]
    beneficial_effects: list[str]
    embodiments: list[str]
    experimental_evidence: list[str]
    drawing_descriptions: list[str]
    terminology: list[str] = Field(default_factory=list)
    system_implementation: list[str] = Field(default_factory=list)
    data_and_interfaces: list[str] = Field(default_factory=list)
    implementation_boundaries: list[str] = Field(default_factory=list)
    alternatives: list[str]
    inventor_confirmation_items: list[str]


class ReviewFinding(BaseModel):
    severity: Literal["critical", "major", "minor", "note"]
    code: str
    message: str
    remediation: str


class ReviewReport(BaseModel):
    score: int = Field(ge=0, le=100)
    passed: bool
    findings: list[ReviewFinding]
    missing_support: list[str] = Field(default_factory=list)
    human_review_checklist: list[str] = Field(default_factory=list)


class PipelineEvent(BaseModel):
    stage: str
    agent: str
    status: Literal["started", "completed", "failed"]
    message: str
    timestamp: datetime = Field(default_factory=utc_now)


class PipelineJob(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    input_name: str
    paper: LatexPaper | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    understanding: PaperUnderstanding | None = None
    invention: InventionDisclosure | None = None
    solution: TechnicalSolution | None = None
    evidence_package: EvidencePackage | None = None
    disclosure: TechnicalDisclosure | None = None
    review: ReviewReport | None = None
    events: list[PipelineEvent] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
