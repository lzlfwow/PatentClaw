from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agents import (
    DisclosureWriterAgent,
    EmbodimentEvidenceAgent,
    IndependentReviewAgent,
    InventionMiningAgent,
    PaperUnderstandingAgent,
    TechnicalSolutionAgent,
)
from .agents.base import AgentContext, ModelGateway, SubAgent
from .config import Settings
from .exporter import export_job
from .latex_parser import parse_latex_project
from .schemas import JobStatus, PipelineEvent, PipelineJob
from .storage import JobStore


def default_agents(enable_review: bool = False) -> tuple[SubAgent, ...]:
    agents: tuple[SubAgent, ...] = (
        PaperUnderstandingAgent(),
        InventionMiningAgent(),
        TechnicalSolutionAgent(),
        EmbodimentEvidenceAgent(),
        DisclosureWriterAgent(),
    )
    return (*agents, IndependentReviewAgent()) if enable_review else agents


class DisclosurePipeline:
    def __init__(self, settings: Settings, store: JobStore, agents: tuple[SubAgent, ...] | None = None):
        self.settings = settings
        self.store = store
        self.agents = agents or default_agents(settings.enable_review)
        self.gateway = ModelGateway(settings)

    def create(self, input_name: str, input_path: Path) -> PipelineJob:
        job = PipelineJob(
            job_id=f"l2d-{uuid4().hex[:12]}",
            input_name=input_name,
            metadata={
                "input_path": str(input_path.resolve()),
                "offline_mode": self.settings.offline_mode,
                "model": self.settings.model,
                "review_model": self.settings.review_model,
                "enable_review": self.settings.enable_review,
                "agent_sequence": [agent.name for agent in self.agents],
            },
        )
        self.store.save(job)
        return job

    async def run(self, job_id: str) -> PipelineJob:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        input_path = Path(str(job.metadata["input_path"]))
        workspace = self.settings.data_dir / job.job_id
        job.status = JobStatus.running
        job.updated_at = datetime.now(timezone.utc)
        self.store.save(job)
        try:
            job.events.append(PipelineEvent(
                stage="stage0_latex_ingestion", agent="latex_parser_tool", status="started", message="解析LaTeX工程并建立证据账本"
            ))
            self.store.save(job)
            job.paper, job.evidence = parse_latex_project(
                input_path,
                workspace,
                max_expanded_bytes=self.settings.max_expanded_mb * 1024 * 1024,
                max_chars=self.settings.max_latex_chars,
            )
            job.events.append(PipelineEvent(
                stage="stage0_latex_ingestion", agent="latex_parser_tool", status="completed", message="LaTeX解析与证据账本完成"
            ))
            self.store.save(job)

            context = AgentContext(job=job, settings=self.settings, gateway=self.gateway)
            for agent in self.agents:
                job.events.append(PipelineEvent(stage=agent.stage, agent=agent.name, status="started", message=agent.label))
                self.store.save(job)
                await agent.run(context)
                job.events.append(PipelineEvent(stage=agent.stage, agent=agent.name, status="completed", message=f"{agent.label}完成"))
                job.updated_at = datetime.now(timezone.utc)
                self.store.save(job)

            job.events.append(PipelineEvent(stage="stage7_export", agent="export_tool", status="started", message="导出技术交底书"))
            job.events.append(PipelineEvent(stage="stage7_export", agent="export_tool", status="completed", message="技术交底书导出完成"))
            job.status = JobStatus.completed
            job.updated_at = datetime.now(timezone.utc)
            job.artifacts = export_job(job, self.settings.data_dir)
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = f"{type(exc).__name__}: {exc}"
            job.events.append(PipelineEvent(
                stage=job.events[-1].stage if job.events else "pipeline",
                agent=job.events[-1].agent if job.events else "pipeline",
                status="failed",
                message=job.error,
            ))
        job.updated_at = datetime.now(timezone.utc)
        self.store.save(job)
        return job
