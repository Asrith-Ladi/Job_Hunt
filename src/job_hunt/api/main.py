"""FastAPI composition root for the React job-hunt application."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from starlette.middleware.sessions import SessionMiddleware

from job_hunt.gmail.service import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_MESSAGES,
    DEFAULT_SOURCE_LABELS,
    GmailRunOptions,
    GmailWorkflowService,
    service_error_message,
)
from job_hunt.integrations.gmail import GmailApiError
from job_hunt.network.service import (
    DEFAULT_TARGET_ROLES,
    MAX_TARGET_ROLES_LENGTH,
    NetworkReviewService,
)
from job_hunt.intelligence.service import JobIntelligenceService
from job_hunt.discovery.adapters import supported_providers
from job_hunt.discovery.detection import detect_source
from job_hunt.discovery.models import DiscoveryFilters, SourceConfig
from job_hunt.discovery.service import (
    ATS_SOURCES,
    COMPANY_PORTALS,
    MAX_SOURCES_PER_RUN,
    DiscoveryRunOptions,
    DiscoveryWorkflowService,
)
from job_hunt.runtime.google import GoogleConnectionService
from job_hunt.runtime.application_queue import ApplicationQueueService
from job_hunt.runtime.paths import AppPaths
from job_hunt.runtime.search_progress import SearchProgressStore, validate_progress_id


def _project_root() -> Path:
    configured = os.environ.get("JOB_HUNT_PROJECT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = _project_root()


class GmailRunRequest(BaseModel):
    sources: list[Literal["linkedin", "naukri"]] = Field(
        default_factory=lambda: ["linkedin", "naukri"],
        min_length=1,
    )
    labels_by_source: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_SOURCE_LABELS))
    gmail_query: str = ""
    company_allowlist: list[str] = Field(default_factory=list)
    include_unmatched_companies: bool = True
    lookback_days: int = Field(DEFAULT_LOOKBACK_DAYS, ge=1, le=90)
    max_messages: int = Field(DEFAULT_MAX_MESSAGES, ge=1, le=5000)
    target_experience_min_years: float = Field(5.0, ge=0)
    target_experience_max_years: float = Field(8.0, ge=0)
    strict_experience_filter: bool = False

    @model_validator(mode="after")
    def validate_target_range(self):
        if self.target_experience_max_years < self.target_experience_min_years:
            raise ValueError("Target maximum experience must be at least the minimum.")
        return self

    def to_options(self) -> GmailRunOptions:
        return GmailRunOptions(
            sources=tuple(self.sources),
            labels_by_source=self.labels_by_source,
            gmail_query=self.gmail_query,
            company_allowlist=tuple(self.company_allowlist),
            include_unmatched_companies=self.include_unmatched_companies,
            lookback_days=self.lookback_days,
            max_messages=self.max_messages,
            target_experience_min_years=self.target_experience_min_years,
            target_experience_max_years=self.target_experience_max_years,
            strict_experience_filter=self.strict_experience_filter,
        )


class ReferralCandidateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    position: str = Field("", max_length=1000)
    profile_url: str = Field("", max_length=4096)
    message: str = Field("", max_length=10_000)


class ApplicationUpsertRequest(BaseModel):
    source: Literal["gmail", "company_portals", "ats_sources"]
    row: dict[str, Any]
    referral_candidates: list[ReferralCandidateRequest] = Field(
        default_factory=list,
        max_length=100,
    )


class DiscoveryFiltersRequest(BaseModel):
    keyword: str = Field("", max_length=500)
    capability_keywords: str = Field("", max_length=500)
    location: str = Field("", max_length=300)
    posted_within_days: int = Field(15, ge=1, le=90)
    include_unknown_dates: bool = True
    max_jobs_per_source: int = Field(100, ge=1, le=250)
    target_experience_min_years: float = Field(5.0, ge=0)
    target_experience_max_years: float = Field(8.0, ge=0)
    strict_experience_filter: bool = False

    @model_validator(mode="after")
    def validate_target_range(self):
        if self.target_experience_max_years < self.target_experience_min_years:
            raise ValueError("Target maximum experience must be at least the minimum.")
        return self

    def to_filters(self) -> DiscoveryFilters:
        return DiscoveryFilters(**self.model_dump())


class ManualAtsSourceRequest(BaseModel):
    company: str = Field(min_length=1, max_length=300)
    provider: Literal["greenhouse", "lever", "workable", "smartrecruiters"]
    identifier: str = Field(min_length=1, max_length=200)
    region: Literal["global", "eu"] = "global"
    careers_url: str = Field("", max_length=4096)

    def to_source(self) -> SourceConfig:
        return SourceConfig(
            company=self.company.strip(),
            provider=self.provider,
            identifier=self.identifier.strip(),
            region=self.region,
            careers_url=self.careers_url.strip(),
            category="Manual ATS",
            fallback="hosted ATS page, Gmail alert, or manual job link",
            source_type_label=f"Manual {self.provider}",
        )


class DiscoveryRunRequest(BaseModel):
    company_ids: list[str] = Field(default_factory=list, max_length=MAX_SOURCES_PER_RUN)
    manual_sources: list[ManualAtsSourceRequest] = Field(
        default_factory=list,
        max_length=MAX_SOURCES_PER_RUN,
    )
    filters: DiscoveryFiltersRequest = Field(default_factory=DiscoveryFiltersRequest)

    @model_validator(mode="after")
    def validate_source_count(self):
        total = len(self.company_ids) + len(self.manual_sources)
        if not 1 <= total <= MAX_SOURCES_PER_RUN:
            raise ValueError(f"Select between 1 and {MAX_SOURCES_PER_RUN} companies or sources.")
        return self

    def to_options(self, mode: str) -> DiscoveryRunOptions:
        return DiscoveryRunOptions(
            mode=mode,
            company_ids=tuple(self.company_ids),
            manual_sources=tuple(item.to_source() for item in self.manual_sources),
            filters=self.filters.to_filters(),
        )


class SourceDetectionRequest(BaseModel):
    careers_url: str = Field("", max_length=4096)
    portal_url: str = Field("", max_length=4096)
    public_feed_url: str = Field("", max_length=4096)
    source_type_label: str = Field("", max_length=200)
    identifier: str = Field("", max_length=200)


class JobFactsRequest(BaseModel):
    job_record_id: str = Field("", max_length=200)
    company: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    location: str = Field("", max_length=300)
    experience_text: str = Field("", max_length=500)
    official_url: str = Field("", max_length=4096)


class JobAnalysisRequest(BaseModel):
    job: JobFactsRequest
    refresh: bool = False


class ConfirmedSkillEvidenceRequest(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=20, max_length=1200)
    confirmed: bool = False


class ResumeGenerationRequest(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=100)
    official_job_id: str = Field(min_length=1, max_length=100)
    outputs: list[Literal["resume_docx", "resume_pdf", "cover_letter"]] = Field(
        default_factory=lambda: ["resume_docx"],
        min_length=1,
        max_length=3,
    )
    confirmed_skill_evidence: list[ConfirmedSkillEvidenceRequest] = Field(
        default_factory=list,
        max_length=20,
    )
    refresh_plan: bool = False


class ApplicationPackageRequest(ApplicationUpsertRequest):
    analysis_id: str = Field(min_length=1, max_length=100)
    official_job_id: str = Field(min_length=1, max_length=100)
    generation_id: str = Field(min_length=1, max_length=100)


def _frontend_origins() -> list[str]:
    configured = os.environ.get("JOB_HUNT_CORS_ORIGINS", "")
    values = [value.strip().rstrip("/") for value in configured.split(",") if value.strip()]
    if values:
        return values
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


def _service_http_error(exc: Exception) -> HTTPException:
    message = service_error_message(exc)
    if isinstance(exc, GmailApiError):
        return HTTPException(status_code=502, detail=message)
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=message)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=message)
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=500, detail="The operation could not be completed.")


def create_app(
    *,
    gmail_service: GmailWorkflowService | None = None,
    discovery_service: DiscoveryWorkflowService | None = None,
    google_connection: GoogleConnectionService | None = None,
    network_service: NetworkReviewService | None = None,
    job_intelligence_service: JobIntelligenceService | None = None,
    application_queue_service: ApplicationQueueService | None = None,
    search_progress_store: SearchProgressStore | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    paths = AppPaths.from_project_root(PROJECT_ROOT)
    connection = google_connection or GoogleConnectionService(paths)
    workflow = gmail_service or GmailWorkflowService(paths, connection)
    discovery = discovery_service or DiscoveryWorkflowService(paths, connection)
    network = network_service or NetworkReviewService(paths.registry_path)
    intelligence = job_intelligence_service or JobIntelligenceService(paths, connection)
    applications = application_queue_service or ApplicationQueueService(paths, connection)
    search_progress = search_progress_store or SearchProgressStore()

    application = FastAPI(
        title="Personal Job Hunt API",
        version="0.4.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    cookie_secret = os.environ.get("JOB_HUNT_SESSION_SECRET") or secrets.token_urlsafe(32)
    cookie_secure = os.environ.get("JOB_HUNT_COOKIE_SECURE", "").casefold() in {
        "1",
        "true",
        "yes",
    }
    application.add_middleware(
        SessionMiddleware,
        secret_key=cookie_secret,
        same_site="lax",
        https_only=cookie_secure,
        session_cookie="job_hunt_session",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Job-Hunt-Progress-ID"],
    )

    def request_progress_id(request: Request) -> str:
        raw = request.headers.get("X-Job-Hunt-Progress-ID", "").strip()
        if not raw:
            return ""
        try:
            return validate_progress_id(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def progress_callback(progress_id: str):
        if not progress_id:
            return None
        return lambda values: search_progress.update(progress_id, values)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/config")
    def config() -> dict[str, Any]:
        value = workflow.defaults()
        value["discovery_max_sources_per_run"] = MAX_SOURCES_PER_RUN
        value["supported_ats_providers"] = supported_providers()
        return value

    @application.get("/api/registry/companies")
    def registry_companies():
        try:
            snapshot = discovery.registry_snapshot()
        except Exception as exc:
            raise _service_http_error(exc) from exc
        snapshot["supported_ats_providers"] = supported_providers()
        return snapshot

    @application.get("/api/applications")
    def list_applications():
        try:
            return applications.list()
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.put("/api/applications")
    def save_application(payload: ApplicationUpsertRequest):
        try:
            return applications.upsert(
                payload.source,
                payload.row,
                [candidate.model_dump() for candidate in payload.referral_candidates],
            )
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.get("/api/network/connections")
    def network_connections(
        q: str = Query("", max_length=200),
        category: str = Query("", max_length=100),
        recommended_only: bool = True,
        leadership_only: bool = False,
        target_roles: str = Query(
            DEFAULT_TARGET_ROLES,
            max_length=MAX_TARGET_ROLES_LENGTH,
        ),
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
    ):
        try:
            return network.search(
                query=q,
                category=category,
                recommended_only=recommended_only,
                leadership_only=leadership_only,
                target_roles=target_roles,
                offset=offset,
                limit=limit,
            )
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.post("/api/sources/detect")
    def detect_public_source(payload: SourceDetectionRequest):
        result = detect_source(
            source_type_label=payload.source_type_label,
            identifier=payload.identifier,
            urls=(
                payload.portal_url,
                payload.careers_url,
                payload.public_feed_url,
            ),
        )
        return {"detection": result.to_dict()}

    @application.get("/api/job-intelligence/status")
    def job_intelligence_status():
        try:
            return intelligence.status()
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.get("/api/job-intelligence/usage")
    def job_intelligence_usage(limit: int = Query(20, ge=1, le=100)):
        try:
            return intelligence.ai_usage(limit=limit)
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.post("/api/job-intelligence/baseline-resume")
    async def upload_baseline_resume(file: UploadFile = File(...)):
        if not str(file.filename or "").casefold().endswith(".docx"):
            raise HTTPException(status_code=422, detail="Upload a Word .docx resume file.")
        try:
            content = await file.read(8 * 1024 * 1024 + 1)
            return intelligence.store_baseline_resume(content, str(file.filename or ""))
        except Exception as exc:
            raise _service_http_error(exc) from exc
        finally:
            await file.close()

    @application.post("/api/job-intelligence/reference-documents")
    async def upload_reference_documents(files: list[UploadFile] = File(...)):
        if not 1 <= len(files) <= 20:
            raise HTTPException(status_code=422, detail="Upload between 1 and 20 references.")
        prepared: list[tuple[str, bytes]] = []
        try:
            for file in files:
                name = str(file.filename or "")
                if Path(name).suffix.casefold() not in {".docx", ".md", ".txt"}:
                    raise HTTPException(
                        status_code=422,
                        detail="Reference files must be .docx, .md, or .txt files.",
                    )
                prepared.append((name, await file.read(8 * 1024 * 1024 + 1)))
            return intelligence.store_reference_documents(prepared)
        except HTTPException:
            raise
        except Exception as exc:
            raise _service_http_error(exc) from exc
        finally:
            for file in files:
                await file.close()

    @application.post("/api/job-intelligence/analyze")
    def analyze_job(payload: JobAnalysisRequest):
        try:
            return {
                "analysis": intelligence.analyze(
                    payload.job.model_dump(),
                    refresh=payload.refresh,
                )
            }
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.post("/api/job-intelligence/resumes")
    def generate_tailored_resume(payload: ResumeGenerationRequest):
        try:
            result = intelligence.generate_documents(
                payload.analysis_id,
                payload.official_job_id,
                outputs=payload.outputs,
                confirmed_skill_evidence=[
                    item.model_dump() for item in payload.confirmed_skill_evidence
                ],
                refresh_plan=payload.refresh_plan,
            )
            for artifact in result["artifacts"]:
                artifact["download_url"] = (
                    "/api/job-intelligence/artifacts/"
                    f"{artifact['artifact_id']}/download"
                )
            return {"generation": result}
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.post("/api/job-intelligence/apply")
    def archive_applied_job(payload: ApplicationPackageRequest):
        try:
            package = intelligence.archive_application_package(
                payload.analysis_id,
                payload.official_job_id,
                payload.generation_id,
                source_job=payload.row,
            )
            row = dict(payload.row)
            row["application_status"] = "applied"
            row["applied_at"] = package["applied_at"]
            if package.get("official_url"):
                row["official_url"] = package["official_url"]
            row["application_package_folder_url"] = package["folder_url"]
            row["application_package_folder_path"] = package["folder_path"]
            row["job_description_source"] = package["description_source"]
            row["job_description_completeness"] = package.get(
                "description_completeness", "summary_only"
            )
            row["job_description_capture_warning"] = package.get("capture_warning", "")
            for file in package.get("files") or []:
                if file.get("kind") == "job_description_document":
                    row["job_description_drive_url"] = file.get("drive_url") or ""
                elif (
                    file.get("kind") == "job_description"
                    and not row.get("job_description_drive_url")
                ):
                    row["job_description_drive_url"] = file.get("drive_url") or ""
                elif file.get("kind") == "application_details":
                    row["application_details_drive_url"] = file.get("drive_url") or ""
            application_result = applications.upsert(
                payload.source,
                row,
                [item.model_dump() for item in payload.referral_candidates],
            )
            return {"package": package, **application_result}
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.get("/api/job-intelligence/artifacts/{artifact_id}/download")
    def download_generated_document(artifact_id: str):
        try:
            path, metadata = intelligence.artifact(artifact_id)
        except Exception as exc:
            raise _service_http_error(exc) from exc
        return FileResponse(
            path,
            filename=str(metadata.get("file_name") or path.name),
            media_type=str(metadata.get("mime_type") or "application/octet-stream"),
        )

    @application.get("/api/auth/google/status")
    def google_status(request: Request) -> dict[str, Any]:
        request.session.setdefault("client_id", secrets.token_urlsafe(18))
        return connection.status()

    @application.post("/api/auth/google/start")
    def google_start(request: Request) -> dict[str, str]:
        request.session.setdefault("client_id", secrets.token_urlsafe(18))
        try:
            return connection.start()
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.get("/api/auth/google/callback")
    def google_callback(
        request: Request,
        code: str = "",
        state: str = "",
        error: str = "",
    ):
        if error:
            connection.discard_pending(state)
            query = urlencode({"google": "denied"})
            return RedirectResponse(f"{connection.frontend_url}/?{query}", status_code=303)
        try:
            connection.complete(code=code, state=state)
        except Exception:
            query = urlencode({"google": "error"})
            return RedirectResponse(f"{connection.frontend_url}/?{query}", status_code=303)
        request.session["google_connected"] = True
        query = urlencode({"google": "connected"})
        return RedirectResponse(f"{connection.frontend_url}/?{query}", status_code=303)

    @application.get("/api/drive/workspace")
    def drive_workspace() -> dict[str, str]:
        return workflow.workspace()

    @application.get("/api/gmail/runs/latest")
    def latest_gmail_run():
        try:
            artifact = workflow.latest()
        except Exception as exc:
            raise _service_http_error(exc) from exc
        return {"run": artifact}

    @application.get("/api/gmail/runs")
    def list_gmail_runs(limit: int = 50):
        try:
            return {"runs": workflow.history(limit=limit)}
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.get("/api/search/progress/{progress_id}")
    def get_search_progress(progress_id: str):
        try:
            snapshot = search_progress.get(progress_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Search progress is not available.")
        return {"progress": snapshot}

    @application.post("/api/search/gmail")
    def search_gmail(payload: GmailRunRequest, request: Request):
        progress_id = request_progress_id(request)
        if progress_id:
            search_progress.start(
                progress_id,
                source="gmail",
                message="Preparing the approved Gmail alert search.",
                total_items=len(payload.sources),
            )
        try:
            options = payload.to_options()
            run = (
                workflow.search(options, progress_callback=progress_callback(progress_id))
                if progress_id
                else workflow.search(options)
            )
        except Exception as exc:
            if progress_id:
                search_progress.finish(
                    progress_id,
                    status="failed",
                    message="Gmail search stopped. Review the visible error and try again.",
                )
            raise _service_http_error(exc) from exc
        final_progress = None
        if progress_id:
            final_progress = search_progress.finish(
                progress_id,
                status="completed",
                message=f"Gmail search completed with {len(run.get('rows') or [])} results.",
                matches_found=len(run.get("rows") or []),
            )
        return {"run": run, "progress": final_progress}

    @application.get("/api/gmail/runs/{run_id}")
    def get_gmail_run(run_id: str):
        try:
            return {"run": workflow.get(run_id)}
        except Exception as exc:
            raise _service_http_error(exc) from exc

    @application.get("/api/gmail/runs/{run_id}/download")
    def download_gmail_run(run_id: str):
        try:
            path = workflow.workbook_path(run_id)
        except Exception as exc:
            raise _service_http_error(exc) from exc
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def latest_discovery_run(mode: str):
        try:
            artifact = discovery.latest(mode)
        except Exception as exc:
            raise _service_http_error(exc) from exc
        return {"run": artifact}

    def search_discovery(mode: str, payload: DiscoveryRunRequest, request: Request):
        progress_id = request_progress_id(request)
        source_name = "company_portals" if mode == COMPANY_PORTALS else "ats_sources"
        source_label = "company portal" if mode == COMPANY_PORTALS else "ATS"
        total_items = len(payload.company_ids) + len(payload.manual_sources)
        if progress_id:
            search_progress.start(
                progress_id,
                source=source_name,
                message=f"Preparing {total_items} selected {source_label} source(s).",
                total_items=total_items,
            )
        try:
            options = payload.to_options(mode)
            run = (
                discovery.search(options, progress_callback=progress_callback(progress_id))
                if progress_id
                else discovery.search(options)
            )
        except Exception as exc:
            if progress_id:
                search_progress.finish(
                    progress_id,
                    status="failed",
                    message=f"{source_label.title()} search stopped. Review the visible error.",
                )
            raise _service_http_error(exc) from exc
        final_progress = None
        if progress_id:
            final_progress = search_progress.finish(
                progress_id,
                status="completed",
                message=f"{source_label.title()} search completed with {len(run.get('rows') or [])} results.",
                matches_found=len(run.get("rows") or []),
            )
        return {"run": run, "progress": final_progress}

    def get_discovery_run(mode: str, run_id: str):
        try:
            return {"run": discovery.get(mode, run_id)}
        except Exception as exc:
            raise _service_http_error(exc) from exc

    def download_discovery_run(mode: str, run_id: str):
        try:
            path = discovery.workbook_path(mode, run_id)
        except Exception as exc:
            raise _service_http_error(exc) from exc
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @application.get("/api/company-portals/runs/latest")
    def latest_company_portal_run():
        return latest_discovery_run(COMPANY_PORTALS)

    @application.post("/api/search/company-portals")
    def search_company_portals(payload: DiscoveryRunRequest, request: Request):
        if payload.manual_sources:
            raise HTTPException(
                status_code=422,
                detail="Manual ATS identifiers belong in the ATS Sources tab.",
            )
        return search_discovery(COMPANY_PORTALS, payload, request)

    @application.get("/api/company-portals/runs/{run_id}")
    def get_company_portal_run(run_id: str):
        return get_discovery_run(COMPANY_PORTALS, run_id)

    @application.get("/api/company-portals/runs/{run_id}/download")
    def download_company_portal_run(run_id: str):
        return download_discovery_run(COMPANY_PORTALS, run_id)

    @application.get("/api/ats-sources/runs/latest")
    def latest_ats_run():
        return latest_discovery_run(ATS_SOURCES)

    @application.post("/api/search/ats-sources")
    def search_ats_sources(payload: DiscoveryRunRequest, request: Request):
        return search_discovery(ATS_SOURCES, payload, request)

    @application.get("/api/ats-sources/runs/{run_id}")
    def get_ats_run(run_id: str):
        return get_discovery_run(ATS_SOURCES, run_id)

    @application.get("/api/ats-sources/runs/{run_id}/download")
    def download_ats_run(run_id: str):
        return download_discovery_run(ATS_SOURCES, run_id)

    frontend_dist = Path(static_dir or (PROJECT_ROOT / "frontend" / "dist"))
    assets = frontend_dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    if (frontend_dist / "index.html").is_file():

        @application.get("/", include_in_schema=False)
        def frontend_index():
            return FileResponse(frontend_dist / "index.html")

        @application.get("/{full_path:path}", include_in_schema=False)
        def frontend_route(full_path: str):
            candidate = (frontend_dist / full_path).resolve()
            try:
                candidate.relative_to(frontend_dist.resolve())
            except ValueError:
                candidate = frontend_dist / "index.html"
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return application


app = create_app()
