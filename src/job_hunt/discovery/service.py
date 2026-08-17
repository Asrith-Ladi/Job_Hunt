"""Application service for manual company-portal and public-ATS runs."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from job_hunt.discovery.adapters import adapter_for, supported_providers
from job_hunt.discovery.generic import GenericPublicDiscovery
from job_hunt.discovery.http_client import (
    AccessStoppedError,
    PublicSourceError,
    SafeHttpClient,
)
from job_hunt.discovery.models import (
    DiscoveryFilters,
    DiscoveryJob,
    SourceCheck,
    SourceConfig,
    canonical_public_url,
    clean_text,
)
from job_hunt.discovery.registry import CompanyRegistryEntry, load_company_registry
from job_hunt.discovery.state import (
    classify_discovery_rows,
    normalize_discovery_state,
    update_discovery_state,
    update_user_fields,
)
from job_hunt.discovery.workbook import (
    APPLICATION_STATUSES,
    DISCOVERY_JOB_COLUMNS,
    EDITABLE_DISCOVERY_COLUMNS,
    read_discovery_workbook,
    validate_discovery_rows,
    verify_discovery_workbook,
    write_discovery_workbook,
)
from job_hunt.gmail_service import AppPaths, GoogleConnectionService, TIME_ZONE
from job_hunt.integrations.drive_storage import (
    build_drive_service,
    download_drive_file,
    drive_file_url,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.local_state import load_local_state, save_local_state
from job_hunt.private_io import read_json, write_json_atomic


COMPANY_PORTALS = "company_portals"
ATS_SOURCES = "ats_sources"
DISCOVERY_MODES = {COMPANY_PORTALS, ATS_SOURCES}
MAX_SOURCES_PER_RUN = 10
STATE_FILES = {
    COMPANY_PORTALS: "company_portal_seen_state.json",
    ATS_SOURCES: "ats_seen_state.json",
}
STATE_KEYS = {
    COMPANY_PORTALS: "last_company_portal_run",
    ATS_SOURCES: "last_ats_run",
}
FILE_PREFIXES = {
    COMPANY_PORTALS: "company_portals",
    ATS_SOURCES: "ats_sources",
}


@dataclass(frozen=True)
class DiscoveryRunOptions:
    """Validated inputs for one explicit discovery run."""

    mode: str
    company_ids: tuple[str, ...] = ()
    manual_sources: tuple[SourceConfig, ...] = ()
    filters: DiscoveryFilters = DiscoveryFilters()

    def validate(self) -> None:
        if self.mode not in DISCOVERY_MODES:
            raise ValueError("An unsupported discovery mode was supplied.")
        total = len(self.company_ids) + len(self.manual_sources)
        if not 1 <= total <= MAX_SOURCES_PER_RUN:
            raise ValueError(
                f"Select between 1 and {MAX_SOURCES_PER_RUN} companies or sources per run."
            )
        if len(self.company_ids) != len(set(self.company_ids)):
            raise ValueError("The same registry company cannot be selected twice.")
        if self.mode == COMPANY_PORTALS and self.manual_sources:
            raise ValueError("Manual ATS identifiers belong in the ATS Sources tab.")
        if self.mode == ATS_SOURCES:
            allowed = set(supported_providers())
            for source in self.manual_sources:
                if clean_text(source.provider).casefold() not in allowed:
                    raise ValueError(
                        "Manual ATS sources support Greenhouse, Lever, Workable, or SmartRecruiters."
                    )
                if not clean_text(source.company) or not clean_text(source.identifier):
                    raise ValueError("A manual ATS source requires a company and identifier.")
        self.filters.validate()


def _safe_warning(exc: Exception) -> str:
    if isinstance(exc, (PublicSourceError, ValueError, RuntimeError, OSError)):
        return clean_text(exc, limit=1000)
    return type(exc).__name__


def _deduplicate_jobs(jobs: Iterable[DiscoveryJob]) -> list[DiscoveryJob]:
    """Prefer the richest official row when a URL appears more than once."""

    selected: dict[str, DiscoveryJob] = {}
    for job in jobs:
        key = canonical_public_url(job.official_url) or job.job_record_id
        existing = selected.get(key)
        if existing is None:
            selected[key] = job
            continue
        existing_rank = (
            existing.source_type == "official_public_api",
            bool(existing.description),
            len(existing.description),
            bool(existing.posted_at),
        )
        candidate_rank = (
            job.source_type == "official_public_api",
            bool(job.description),
            len(job.description),
            bool(job.posted_at),
        )
        if candidate_rank > existing_rank:
            selected[key] = job
    return sorted(
        selected.values(),
        key=lambda job: (
            job.company.casefold(),
            job.title.casefold(),
            job.location.casefold(),
            job.official_url,
        ),
    )


class DiscoveryWorkflowService:
    """Run, load, edit, and download the two non-Gmail phases."""

    def __init__(
        self,
        paths: AppPaths,
        google_connection: GoogleConnectionService,
        *,
        registry_loader: Callable[[Path], list[CompanyRegistryEntry]] = load_company_registry,
        http_client_factory: Callable[[], SafeHttpClient] = SafeHttpClient,
        drive_service_factory: Callable[[Any], Any] = build_drive_service,
    ) -> None:
        self.paths = paths
        self.google_connection = google_connection
        self.registry_loader = registry_loader
        self.http_client_factory = http_client_factory
        self.drive_service_factory = drive_service_factory
        self._mutation_lock = threading.Lock()

    def registry(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.registry_loader(self.paths.registry_path)]

    def _entries(self, company_ids: Iterable[str]) -> list[CompanyRegistryEntry]:
        registry = self.registry_loader(self.paths.registry_path)
        by_id = {entry.company_id: entry for entry in registry}
        output: list[CompanyRegistryEntry] = []
        for company_id in company_ids:
            entry = by_id.get(str(company_id))
            if entry is None:
                raise ValueError("A selected company is no longer present in the registry.")
            output.append(entry)
        return output

    def _output_root(self, mode: str) -> Path:
        suffix = "company_portal_runs" if mode == COMPANY_PORTALS else "ats_runs"
        return self.paths.project_root / "outputs" / suffix

    def _state_path(self, mode: str) -> Path:
        return self.paths.secrets_root / STATE_FILES[mode]

    def _workbook_path(self, mode: str, run_started_at: datetime) -> Path:
        date_text = run_started_at.date().isoformat()
        timestamp = run_started_at.strftime("%Y-%m-%d_%H%M%S")
        return self._output_root(mode) / date_text / f"{FILE_PREFIXES[mode]}_{timestamp}.xlsx"

    def _load_seen_state(
        self,
        mode: str,
        drive_service,
        source_folder_id: str,
    ) -> tuple[dict[str, Any], str]:
        state_path = self._state_path(mode)
        local_value = read_json(state_path)
        remote = find_child_file(
            drive_service,
            STATE_FILES[mode],
            parent_id=source_folder_id,
            mime_type="application/json",
        )
        if local_value is None and remote:
            download_drive_file(drive_service, str(remote["id"]), state_path)
            local_value = read_json(state_path)
        return normalize_discovery_state(local_value), str((remote or {}).get("id") or "")

    def _sync_registry(
        self,
        drive_service,
        source_folder_id: str,
        app_state: dict[str, Any],
    ) -> None:
        if not self.paths.registry_path.is_file():
            return
        source_ids = dict(app_state.get("drive_source_file_ids") or {})
        uploaded = upload_or_update_file(
            drive_service,
            self.paths.registry_path,
            parent_id=source_folder_id,
            existing_file_id=source_ids.get(self.paths.registry_path.name),
        )
        source_ids[self.paths.registry_path.name] = str(uploaded["id"])
        app_state["drive_source_file_ids"] = source_ids

    def _sync_seen_state(
        self,
        mode: str,
        state: Mapping[str, Any],
        drive_service,
        source_folder_id: str,
        app_state: dict[str, Any],
        *,
        existing_file_id: str = "",
    ) -> None:
        state_path = self._state_path(mode)
        write_json_atomic(state_path, dict(state))
        source_ids = dict(app_state.get("drive_source_file_ids") or {})
        uploaded = upload_or_update_file(
            drive_service,
            state_path,
            parent_id=source_folder_id,
            existing_file_id=(existing_file_id or source_ids.get(STATE_FILES[mode]) or None),
            mime_type="application/json",
        )
        source_ids[STATE_FILES[mode]] = str(uploaded["id"])
        app_state["drive_source_file_ids"] = source_ids

    @staticmethod
    def _check(
        source: SourceConfig,
        *,
        strategy: str,
        source_url: str,
        status: str,
        jobs_found: int,
        warning: str,
        checked_at: str,
    ) -> SourceCheck:
        return SourceCheck(
            company=source.company,
            category=source.category,
            provider=source.provider or "generic",
            source_identifier=source.identifier,
            strategy=strategy,
            source_url=canonical_public_url(source_url),
            status=status,
            jobs_found=jobs_found,
            jobs_exported=0,
            warning=clean_text(warning, limit=1000),
            fallback=clean_text(
                source.fallback
                or "official sitemap, permitted static HTML, Gmail alert, or manual link",
                limit=1000,
            ),
            checked_at=checked_at,
        )

    def _company_source(
        self,
        source: SourceConfig,
        filters: DiscoveryFilters,
        http: SafeHttpClient,
        checked_at: str,
    ) -> tuple[list[DiscoveryJob], SourceCheck]:
        warning = ""
        if source.provider in supported_providers() and source.identifier:
            adapter = adapter_for(source.provider, http)
            try:
                jobs = adapter.fetch(source, filters)
            except AccessStoppedError as exc:
                return [], self._check(
                    source,
                    strategy="official_public_api",
                    source_url=adapter.endpoint(source),
                    status="access_stopped",
                    jobs_found=0,
                    warning=_safe_warning(exc),
                    checked_at=checked_at,
                )
            except PublicSourceError as exc:
                warning = _safe_warning(exc)
            else:
                return jobs, self._check(
                    source,
                    strategy="official_public_api",
                    source_url=adapter.endpoint(source),
                    status="success" if jobs else "no_matching_jobs",
                    jobs_found=len(jobs),
                    warning="",
                    checked_at=checked_at,
                )

        generic = GenericPublicDiscovery(http)
        jobs, strategy, generic_warning = generic.discover(
            source,
            filters,
            discovered_at=checked_at,
        )
        warnings = "; ".join(value for value in [warning, generic_warning] if value)
        if jobs:
            status = "success_with_fallback" if warning else "success"
        elif warnings:
            status = "manual_review_required"
        elif source.portal_url or source.careers_url or source.public_feed_url:
            status = "no_matching_jobs"
        else:
            status = "manual_review_required"
            warnings = "No usable official public URL is configured for this company."
        return jobs, self._check(
            source,
            strategy=strategy,
            source_url=(source.public_feed_url or source.portal_url or source.careers_url),
            status=status,
            jobs_found=len(jobs),
            warning=warnings,
            checked_at=checked_at,
        )

    def _ats_source(
        self,
        source: SourceConfig,
        filters: DiscoveryFilters,
        http: SafeHttpClient,
        checked_at: str,
    ) -> tuple[list[DiscoveryJob], SourceCheck]:
        if source.provider not in supported_providers() or not source.identifier:
            return [], self._check(
                source,
                strategy="detection_only",
                source_url=source.portal_url or source.careers_url,
                status="manual_review_required",
                jobs_found=0,
                warning=(
                    "This provider has no enabled documented public adapter; "
                    "company-specific endpoints are not treated as official APIs."
                ),
                checked_at=checked_at,
            )
        adapter = adapter_for(source.provider, http)
        try:
            jobs = adapter.fetch(source, filters)
        except AccessStoppedError as exc:
            return [], self._check(
                source,
                strategy="official_public_api",
                source_url=adapter.endpoint(source),
                status="access_stopped",
                jobs_found=0,
                warning=_safe_warning(exc),
                checked_at=checked_at,
            )
        except PublicSourceError as exc:
            return [], self._check(
                source,
                strategy="official_public_api",
                source_url=adapter.endpoint(source),
                status="source_unavailable",
                jobs_found=0,
                warning=_safe_warning(exc),
                checked_at=checked_at,
            )
        return jobs, self._check(
            source,
            strategy="official_public_api",
            source_url=adapter.endpoint(source),
            status="success" if jobs else "no_matching_jobs",
            jobs_found=len(jobs),
            warning="",
            checked_at=checked_at,
        )

    def run(self, options: DiscoveryRunOptions) -> dict[str, Any]:
        options.validate()
        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Another discovery run or save is already in progress.")
        try:
            return self._run_locked(options)
        finally:
            self._mutation_lock.release()

    def _run_locked(self, options: DiscoveryRunOptions) -> dict[str, Any]:
        credentials = self.google_connection.require_credentials()
        run_started_at = datetime.now(TIME_ZONE).replace(microsecond=0)
        run_id = f"{FILE_PREFIXES[options.mode]}-{uuid.uuid4().hex[:12]}"
        checked_at = run_started_at.isoformat()
        entries = self._entries(options.company_ids)
        sources = [entry.to_source_config() for entry in entries]
        sources.extend(options.manual_sources)

        drive_service = self.drive_service_factory(credentials)
        folders = ensure_job_hunt_folders(
            drive_service,
            run_date=run_started_at.date().isoformat(),
        )
        root_id = str(folders["root"]["id"])
        source_folder_id = str(folders["source"]["id"])
        date_folder_id = str(folders["date"]["id"])
        app_state = load_local_state(self.paths.app_state_path)
        self._sync_registry(drive_service, source_folder_id, app_state)
        seen_state, seen_state_file_id = self._load_seen_state(
            options.mode,
            drive_service,
            source_folder_id,
        )

        http = self.http_client_factory()
        discovered: list[DiscoveryJob] = []
        checks: list[SourceCheck] = []
        source_by_record: dict[str, int] = {}
        try:
            for index, source in enumerate(sources):
                try:
                    if options.mode == COMPANY_PORTALS:
                        jobs, check = self._company_source(
                            source,
                            options.filters,
                            http,
                            checked_at,
                        )
                    else:
                        jobs, check = self._ats_source(
                            source,
                            options.filters,
                            http,
                            checked_at,
                        )
                except Exception as exc:  # one broken source must not cancel the batch
                    jobs = []
                    check = self._check(
                        source,
                        strategy="source_error",
                        source_url=(
                            source.public_feed_url or source.portal_url or source.careers_url
                        ),
                        status="source_unavailable",
                        jobs_found=0,
                        warning=_safe_warning(exc),
                        checked_at=checked_at,
                    )
                checks.append(check)
                for job in jobs:
                    discovered.append(job)
                    source_by_record[job.job_record_id] = index
        finally:
            http.close()

        deduplicated = _deduplicate_jobs(discovered)
        current_rows, change_counts = classify_discovery_rows(
            [job.to_dict() for job in deduplicated],
            seen_state,
        )
        exported_counts = [0 for _ in checks]
        for row in current_rows:
            index = source_by_record.get(str(row.get("job_record_id") or ""))
            if index is not None and 0 <= index < len(exported_counts):
                exported_counts[index] += 1
        checks = [
            replace(check, jobs_exported=exported_counts[index])
            for index, check in enumerate(checks)
        ]

        completed_at = datetime.now(TIME_ZONE).replace(microsecond=0).isoformat()
        warning_count = sum(
            1
            for check in checks
            if check.warning or check.status not in {"success", "no_matching_jobs"}
        )
        succeeded = sum(
            1
            for check in checks
            if check.status in {"success", "success_with_fallback", "no_matching_jobs"}
        )
        summary: dict[str, Any] = {
            "run_id": run_id,
            "mode": options.mode,
            "status": "completed_with_warnings" if warning_count else "completed",
            "started_at": checked_at,
            "finished_at": completed_at,
            "sources_requested": len(sources),
            "sources_checked": len(checks),
            "sources_succeeded": succeeded,
            "sources_needing_manual_review": len(checks) - succeeded,
            "jobs_found": len(discovered),
            "jobs_after_deduplication": len(deduplicated),
            "jobs_new_this_run": change_counts["new"],
            "jobs_changed_since_prior_run": change_counts["changed"],
            "jobs_new_or_changed_this_run": (
                change_counts["new"] + change_counts["changed"]
            ),
            "jobs_unchanged_from_prior_runs": change_counts["previously_seen"],
            "jobs_exported_this_run": len(current_rows),
            "warnings": warning_count,
            "keyword_filter": options.filters.keyword,
            "location_filter": options.filters.location,
            "posted_within_days": options.filters.posted_within_days,
            "include_unknown_dates": options.filters.include_unknown_dates,
            "max_jobs_per_source": options.filters.max_jobs_per_source,
            "target_experience_min_years": options.filters.target_experience_min_years,
            "target_experience_max_years": options.filters.target_experience_max_years,
            "strict_experience_filter": options.filters.strict_experience_filter,
        }
        local_path = self._workbook_path(options.mode, run_started_at)
        check_rows = [check.to_dict() for check in checks]
        write_discovery_workbook(
            local_path,
            mode=options.mode,
            rows=current_rows,
            source_checks=check_rows,
            summary=summary,
            run_started_at=run_started_at,
        )
        verify_discovery_workbook(
            local_path,
            expected_jobs=len(current_rows),
            expected_checks=len(check_rows),
        )
        canonical_rows, canonical_checks, canonical_summary = read_discovery_workbook(local_path)
        drive_file = upload_or_update_file(
            drive_service,
            local_path,
            parent_id=date_folder_id,
        )
        metadata = {
            "run_id": run_id,
            "mode": options.mode,
            "local_path": str(local_path),
            "run_started_at": checked_at,
            "date_folder_id": date_folder_id,
            "source_folder_id": source_folder_id,
            "drive_file_id": str(drive_file["id"]),
            "drive_url": drive_file.get("webViewLink") or drive_file_url(str(drive_file["id"])),
        }
        app_state["drive_root_folder_id"] = root_id
        app_state["drive_source_folder_id"] = source_folder_id
        app_state[STATE_KEYS[options.mode]] = metadata

        updated_state = update_discovery_state(
            seen_state,
            current_rows,
            completed_at=completed_at,
        )
        self._sync_seen_state(
            options.mode,
            updated_state,
            drive_service,
            source_folder_id,
            app_state,
            existing_file_id=seen_state_file_id,
        )
        save_local_state(self.paths.app_state_path, app_state)
        return self._artifact_payload(
            metadata,
            canonical_rows,
            canonical_checks,
            canonical_summary,
        )

    def latest(self, mode: str) -> dict[str, Any] | None:
        self._validate_mode(mode)
        state = load_local_state(self.paths.app_state_path)
        metadata = state.get(STATE_KEYS[mode])
        if not isinstance(metadata, Mapping):
            return None
        local_path = self._safe_artifact_path(mode, metadata.get("local_path"))
        if local_path is None or not local_path.is_file():
            return None
        rows, checks, summary = read_discovery_workbook(local_path)
        return self._artifact_payload(metadata, rows, checks, summary)

    def get(self, mode: str, run_id: str) -> dict[str, Any]:
        artifact = self.latest(mode)
        if artifact is None or artifact["run_id"] != str(run_id):
            raise FileNotFoundError("The requested discovery run is unavailable.")
        return artifact

    def save(
        self,
        mode: str,
        run_id: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        self._validate_mode(mode)
        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Another discovery run or save is already in progress.")
        try:
            return self._save_locked(mode, run_id, rows)
        finally:
            self._mutation_lock.release()

    def _save_locked(
        self,
        mode: str,
        run_id: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        artifact = self.get(mode, run_id)
        edited_rows = validate_discovery_rows(rows, expected_rows=artifact["rows"])
        app_state = load_local_state(self.paths.app_state_path)
        metadata = dict(app_state.get(STATE_KEYS[mode]) or {})
        local_path = self._safe_artifact_path(mode, metadata.get("local_path"))
        if local_path is None or not local_path.is_file():
            raise FileNotFoundError("The local discovery workbook is unavailable.")
        drive_file_id = str(metadata.get("drive_file_id") or "")
        date_folder_id = str(metadata.get("date_folder_id") or "")
        source_folder_id = str(metadata.get("source_folder_id") or "")
        if not drive_file_id or not date_folder_id or not source_folder_id:
            raise RuntimeError("The Drive identity for this discovery run is unavailable.")

        pending_path = local_path.with_name(f"{local_path.stem}.pending.xlsx")
        run_started_at = datetime.fromisoformat(str(metadata["run_started_at"]))
        write_discovery_workbook(
            pending_path,
            mode=mode,
            rows=edited_rows,
            source_checks=artifact["source_checks"],
            summary=artifact["summary"],
            run_started_at=run_started_at,
        )
        verify_discovery_workbook(
            pending_path,
            expected_jobs=len(edited_rows),
            expected_checks=len(artifact["source_checks"]),
        )
        try:
            credentials = self.google_connection.require_credentials()
            drive_service = self.drive_service_factory(credentials)
            drive_file = upload_or_update_file(
                drive_service,
                pending_path,
                parent_id=date_folder_id,
                existing_file_id=drive_file_id,
            )
            pending_path.replace(local_path)
        finally:
            if pending_path.exists():
                pending_path.unlink()

        metadata["drive_file_id"] = str(drive_file["id"])
        metadata["drive_url"] = drive_file.get("webViewLink") or drive_file_url(
            str(drive_file["id"])
        )
        current_state = normalize_discovery_state(read_json(self._state_path(mode)))
        current_state = update_user_fields(current_state, edited_rows)
        self._sync_seen_state(
            mode,
            current_state,
            drive_service,
            source_folder_id,
            app_state,
        )
        app_state[STATE_KEYS[mode]] = metadata
        save_local_state(self.paths.app_state_path, app_state)
        return self._artifact_payload(
            metadata,
            edited_rows,
            artifact["source_checks"],
            artifact["summary"],
        )

    def workbook_path(self, mode: str, run_id: str) -> Path:
        self.get(mode, run_id)
        state = load_local_state(self.paths.app_state_path)
        path = self._safe_artifact_path(
            mode,
            (state.get(STATE_KEYS[mode]) or {}).get("local_path"),
        )
        if path is None or not path.is_file():
            raise FileNotFoundError("The discovery workbook is unavailable.")
        return path

    @staticmethod
    def _validate_mode(mode: str) -> None:
        if mode not in DISCOVERY_MODES:
            raise ValueError("An unsupported discovery mode was supplied.")

    def _safe_artifact_path(self, mode: str, value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value)).resolve()
        try:
            path.relative_to(self._output_root(mode).resolve())
        except ValueError:
            return None
        return path

    @staticmethod
    def _artifact_payload(
        metadata: Mapping[str, Any],
        rows: Iterable[Mapping[str, Any]],
        source_checks: Iterable[Mapping[str, Any]],
        summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "run_id": str(metadata.get("run_id") or summary.get("run_id") or ""),
            "mode": str(metadata.get("mode") or summary.get("mode") or ""),
            "run_started_at": str(metadata.get("run_started_at") or ""),
            "file_name": Path(str(metadata.get("local_path") or "discovery.xlsx")).name,
            "drive_url": str(metadata.get("drive_url") or ""),
            "summary": dict(summary),
            "rows": [dict(row) for row in rows],
            "source_checks": [dict(row) for row in source_checks],
            "job_columns": list(DISCOVERY_JOB_COLUMNS),
            "editable_columns": sorted(EDITABLE_DISCOVERY_COLUMNS),
            "application_statuses": list(APPLICATION_STATUSES),
            "experience_fit_statuses": [
                "preferred",
                "possible_overlap",
                "outside_target",
                "unknown",
            ],
        }
