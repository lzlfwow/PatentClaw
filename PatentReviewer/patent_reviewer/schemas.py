from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Severity(str, Enum):
    critical = "critical"
    major = "major"
    minor = "minor"
    note = "note"


class ReviewMode(str, Enum):
    offline = "offline"
    online = "online"


class ReviewDimension(str, Enum):
    evidence_traceability = "证据可追溯性"
    factual_consistency = "事实一致性"
    unsupported_expansion = "无依据扩写"
    completeness_form = "完整性与形式"
    technical_logic = "技术逻辑闭环"
    enablement = "充分公开"
    claim_support = "保护范围支撑"
    eligible_subject = "可专利客体"
    unity = "单一性"
    consistency = "一致性"
    drawings = "附图一致性"
    patent_style = "专利文体"
    ai_algorithm = "AI算法专项"


class CheckStatus(str, Enum):
    passed = "pass"
    failed = "fail"
    needs_human_review = "needs_human_review"
    not_applicable = "not_applicable"
    not_assessed = "not_assessed"


class EvidenceSpan(BaseModel):
    evidence_id: str
    source_file: str
    section: str = ""
    text: str
    locator: str = ""
    origin: Literal["generator", "latex", "derived"] = "generator"


class SourceDocument(BaseModel):
    root_file: str
    title: str = ""
    abstract: str = ""
    sections: dict[str, str] = Field(default_factory=dict)
    equations: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    algorithms: list[str] = Field(default_factory=list)
    figures: list[dict[str, Any]] = Field(default_factory=list)
    bibliography: list[str] = Field(default_factory=list)
    plain_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class PatentFigureAsset(BaseModel):
    """A regenerated Generator figure carried through the review pipeline."""

    figure_no: int = Field(ge=1)
    title: str = ""
    kind: str = "flowchart"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    image_path: str | None = None
    mermaid_path: str | None = None


class TechnicalDisclosure(BaseModel):
    invention_title: str = ""
    technical_field: str = ""
    background: list[str] = Field(default_factory=list)
    prior_art_defects: list[str] = Field(default_factory=list)
    technical_problem: list[str] = Field(default_factory=list)
    overall_solution: str = ""
    detailed_steps: list[str] = Field(default_factory=list)
    key_innovations: list[str] = Field(default_factory=list)
    beneficial_effects: list[str] = Field(default_factory=list)
    embodiments: list[str] = Field(default_factory=list)
    experimental_evidence: list[str] = Field(default_factory=list)
    drawing_descriptions: list[str] = Field(default_factory=list)
    terminology: list[str] = Field(default_factory=list)
    system_implementation: list[str] = Field(default_factory=list)
    data_and_interfaces: list[str] = Field(default_factory=list)
    implementation_boundaries: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    inventor_confirmation_items: list[str] = Field(default_factory=list)


class ReviewInput(BaseModel):
    generator_job_path: str
    source_path: str
    generator_schema_version: str = "patent-generator/0.1"
    source: SourceDocument
    evidence: list[EvidenceSpan]
    disclosure: TechnicalDisclosure
    patent_figures: list[PatentFigureAsset] = Field(default_factory=list)
    generator_metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewFinding(BaseModel):
    finding_id: str
    check_id: str
    dimension: ReviewDimension
    severity: Severity
    code: str
    legal_basis: list[str] = Field(default_factory=list)
    target_section: str
    target_path: str
    original_text: str = ""
    issue: str
    risk: str
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_revision: str = ""
    auto_fixable: bool = False
    requires_inventor_confirmation: bool = False
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: Literal["rule", "llm", "verification"] = "rule"


class DimensionScore(BaseModel):
    dimension: ReviewDimension
    score: int = Field(ge=0, le=100)
    finding_count: int = 0


class ChecklistEvaluation(BaseModel):
    check_id: str
    dimension: ReviewDimension
    title: str
    severity: Severity
    status: CheckStatus
    evaluator: Literal["rule", "llm"]
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    resolution: Literal["unchanged", "resolved", "regressed", "new_failure"] | None = None


class ReviewReport(BaseModel):
    legal_baseline: str
    score: int = Field(ge=0, le=100)
    passed: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    checklist: list[ChecklistEvaluation] = Field(default_factory=list)
    dimensions: list[DimensionScore] = Field(default_factory=list)
    human_review_checklist: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RevisionAction(BaseModel):
    action_id: str
    finding_ids: list[str]
    operation: Literal["replace", "add", "delete", "move", "retain", "confirm"]
    target_path: str
    before: str = ""
    after: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str
    applied: bool = False


class RevisionPlan(BaseModel):
    actions: list[RevisionAction] = Field(default_factory=list)
    blocked_actions: list[RevisionAction] = Field(default_factory=list)


class ChangeRecord(BaseModel):
    action_id: str
    target_path: str
    before: str
    after: str
    finding_ids: list[str]


class IssueRevisionAttempt(BaseModel):
    round_number: int = Field(ge=1)
    check_id: str
    finding_ids: list[str] = Field(default_factory=list)
    allowed_target_paths: list[str] = Field(default_factory=list)
    outcome: Literal["modified", "blocked", "no_change", "rejected"]
    reason: str = ""
    requested_materials: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    changes: list[ChangeRecord] = Field(default_factory=list)


class ReviewJob(BaseModel):
    job_id: str
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    mode: ReviewMode = ReviewMode.offline
    input: ReviewInput
    initial_report: ReviewReport | None = None
    revision_plan: RevisionPlan | None = None
    final_disclosure: TechnicalDisclosure | None = None
    final_report: ReviewReport | None = None
    changes: list[ChangeRecord] = Field(default_factory=list)
    revision_attempts: list[IssueRevisionAttempt] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
