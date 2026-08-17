"""Application services used by the React/FastAPI job-hunt application.

The module keeps Google credentials and raw Gmail messages behind the Python
boundary.  Callers receive only normalized job rows, run summaries, and links
to app-owned Drive resources.
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from job_hunt.config import RunConfig
from job_hunt.gmail_run_state import (
    normalize_gmail_run_state,
    select_new_or_changed_gmail_jobs,
    update_gmail_run_state,
)
from job_hunt.gmail_referrals import enrich_gmail_referrals
from job_hunt.gmail_workbook import (
    APPLICATION_STATUSES,
    EDITABLE_GMAIL_COLUMNS,
    EXPERIENCE_FIT_STATUSES,
    GMAIL_RUN_COLUMNS,
    read_gmail_run_workbook,
    validate_editor_rows,
    verify_gmail_run_workbook,
    write_gmail_run_workbook,
)
from job_hunt.integrations.drive_storage import (
    build_drive_service,
    download_drive_file,
    drive_file_url,
    drive_folder_url,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.integrations.gmail import GoogleGmailReader
from job_hunt.integrations.google_auth import (
    consume_pending_oauth_state,
    create_authorization_url,
    exchange_authorization_code,
    load_stored_credentials,
    save_pending_oauth_state,
)
from job_hunt.local_state import load_local_state, save_local_state
from job_hunt.pipeline import run_pipeline
from job_hunt.private_io import read_json, write_json_atomic


DEFAULT_SOURCE_LABELS = {
    "linkedin": "Job_Alerts/LinkedIn",
    "naukri": "Job_Alerts/Naukari",
}
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MAX_MESSAGES = 500
TIME_ZONE = ZoneInfo("Asia/Kolkata")
GMAIL_SEEN_STATE_NAME = "gmail_seen_state.json"
GOOGLE_TOKEN_NAME = "google_token.json"
GOOGLE_OAUTH_STATE_NAME = "google_oauth_state.json"
APP_STATE_NAME = "app_state.json"


@dataclass(frozen=True)
class AppPaths:
    """Filesystem locations owned by one personal deployment."""

    project_root: Path
    run_output_root: Path
    registry_path: Path
    secrets_root: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "AppPaths":
        root = Path(project_root).resolve()
        return cls(
            project_root=root,
            run_output_root=root / "outputs" / "gmail_runs",
            registry_path=(
                root / "outputs" / "mnc_registry_2026-07-31" / "Company_Source_Registry.xlsx"
            ),
            secrets_root=root / ".secrets",
        )

    @property
    def token_path(self) -> Path:
        return self.secrets_root / GOOGLE_TOKEN_NAME

    @property
    def oauth_state_path(self) -> Path:
        return self.secrets_root / GOOGLE_OAUTH_STATE_NAME

    @property
    def app_state_path(self) -> Path:
        return self.secrets_root / APP_STATE_NAME

    @property
    def gmail_seen_state_path(self) -> Path:
        return self.secrets_root / GMAIL_SEEN_STATE_NAME


@dataclass(frozen=True)
class GmailRunOptions:
    """Validated UI inputs for one manual Gmail-only run."""

    sources: tuple[str, ...] = ("linkedin", "naukri")
    labels_by_source: Mapping[str, str] | None = None
    gmail_query: str = ""
    company_allowlist: tuple[str, ...] = ()
    include_unmatched_companies: bool = True
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    max_messages: int = DEFAULT_MAX_MESSAGES
    target_experience_min_years: float = 5.0
    target_experience_max_years: float = 8.0
    strict_experience_filter: bool = False

    def resolved_query(self) -> str:
        if self.gmail_query.strip():
            return self.gmail_query.strip()
        labels = dict(DEFAULT_SOURCE_LABELS)
        labels.update(self.labels_by_source or {})
        return build_gmail_query(self.sources, labels, self.lookback_days)


def build_gmail_query(
    sources: Iterable[str],
    labels_by_source: Mapping[str, str],
    lookback_days: int,
) -> str:
    """Build the approved label-only rolling Gmail query."""

    label_terms = [
        f"label:{str(labels_by_source.get(source) or '').strip()}"
        for source in sources
        if str(labels_by_source.get(source) or "").strip()
    ]
    if not label_terms:
        return ""
    label_query = " ".join(label_terms)
    if len(label_terms) > 1:
        label_query = f"{{{label_query}}}"
    return f"{label_query} newer_than:{int(lookback_days)}d"


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (ValueError, FileNotFoundError, RuntimeError, OSError)):
        return str(exc)
    return type(exc).__name__


class GoogleConnectionService:
    """Server-side Google OAuth lifecycle for the personal application."""

    def __init__(
        self,
        paths: AppPaths,
        *,
        redirect_uri: str | None = None,
        frontend_url: str | None = None,
    ) -> None:
        self.paths = paths
        self.redirect_uri = (
            redirect_uri
            or os.environ.get("JOB_HUNT_OAUTH_REDIRECT_URI")
            or "http://localhost:8000/api/auth/google/callback"
        ).strip()
        self.frontend_url = (
            frontend_url or os.environ.get("JOB_HUNT_FRONTEND_URL") or "http://localhost:8000"
        ).rstrip("/")

    @property
    def credentials_path(self) -> Path:
        configured = os.environ.get("JOB_HUNT_GOOGLE_CREDENTIALS", "").strip()
        if configured:
            return Path(configured).expanduser()
        return self.paths.project_root / "oauth-client.json"

    def status(self) -> dict[str, Any]:
        credentials_file_available = self.credentials_path.is_file()
        try:
            credentials = load_stored_credentials(self.paths.token_path)
        except RuntimeError as exc:
            return {
                "connected": False,
                "credentials_file_available": credentials_file_available,
                "reconnect_required": True,
                "message": str(exc),
                "redirect_uri": self.redirect_uri,
            }
        connected = credentials is not None
        return {
            "connected": connected,
            "credentials_file_available": credentials_file_available,
            "reconnect_required": False,
            "message": (
                "Google is connected with read-only Gmail and app-created Drive access."
                if connected
                else "Google is not connected yet."
            ),
            "redirect_uri": self.redirect_uri,
        }

    def require_credentials(self):
        try:
            credentials = load_stored_credentials(self.paths.token_path)
        except RuntimeError as exc:
            raise RuntimeError("Reconnect Google before running Gmail alerts.") from exc
        if credentials is None:
            raise RuntimeError("Connect Google before running Gmail alerts.")
        return credentials

    def start(self) -> dict[str, str]:
        credentials_path = self.credentials_path
        if not credentials_path.is_file():
            raise FileNotFoundError("The Google OAuth client file is unavailable on the backend.")
        authorization_url, state, verifier = create_authorization_url(
            credentials_path,
            self.redirect_uri,
        )
        save_pending_oauth_state(
            self.paths.oauth_state_path,
            state,
            verifier,
        )
        return {"authorization_url": authorization_url}

    def complete(self, *, code: str, state: str) -> None:
        verifier = consume_pending_oauth_state(self.paths.oauth_state_path, state)
        if not verifier:
            raise ValueError(
                "The Google callback was invalid or expired. Start the connection again."
            )
        exchange_authorization_code(
            credentials_path=self.credentials_path,
            token_path=self.paths.token_path,
            redirect_uri=self.redirect_uri,
            code=code,
            state=state,
            code_verifier=verifier,
        )

    def discard_pending(self, state: str) -> None:
        consume_pending_oauth_state(self.paths.oauth_state_path, state)


class GmailWorkflowService:
    """Run, load, edit, and download one normalized Gmail workbook at a time."""

    def __init__(
        self,
        paths: AppPaths,
        google_connection: GoogleConnectionService,
    ) -> None:
        self.paths = paths
        self.google_connection = google_connection
        self._mutation_lock = threading.Lock()

    def defaults(self) -> dict[str, Any]:
        state = load_local_state(self.paths.app_state_path)
        root_id = str(state.get("drive_root_folder_id") or "")
        return {
            "source_tabs": [
                "run_setup",
                "job_queue",
                "network_reviews",
            ],
            "sources": ["linkedin", "naukri"],
            "labels_by_source": dict(DEFAULT_SOURCE_LABELS),
            "lookback_days": DEFAULT_LOOKBACK_DAYS,
            "max_messages": DEFAULT_MAX_MESSAGES,
            "target_experience_min_years": 5.0,
            "target_experience_max_years": 8.0,
            "include_unmatched_companies": True,
            "strict_experience_filter": False,
            "job_columns": list(GMAIL_RUN_COLUMNS),
            "editable_columns": sorted(EDITABLE_GMAIL_COLUMNS),
            "application_statuses": list(APPLICATION_STATUSES),
            "experience_fit_statuses": list(EXPERIENCE_FIT_STATUSES),
            "drive_workspace_url": drive_folder_url(root_id) if root_id else "",
        }

    def _run_workbook_path(self, run_started_at: datetime) -> Path:
        date_text = run_started_at.date().isoformat()
        timestamp = run_started_at.strftime("%Y-%m-%d_%H%M%S")
        return self.paths.run_output_root / date_text / f"gmail_alerts_{timestamp}.xlsx"

    def _load_seen_state_from_drive(
        self,
        drive_service,
        source_folder_id: str,
    ) -> tuple[dict[str, Any], str]:
        local_value = read_json(self.paths.gmail_seen_state_path)
        remote = find_child_file(
            drive_service,
            GMAIL_SEEN_STATE_NAME,
            parent_id=source_folder_id,
            mime_type="application/json",
        )
        if local_value is None and remote:
            download_drive_file(
                drive_service,
                str(remote["id"]),
                self.paths.gmail_seen_state_path,
            )
            local_value = read_json(self.paths.gmail_seen_state_path)
        return normalize_gmail_run_state(local_value), str((remote or {}).get("id") or "")

    def _sync_registry_source(
        self,
        drive_service,
        source_folder_id: str,
        local_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.paths.registry_path.is_file():
            return None
        source_ids = dict(local_state.get("drive_source_file_ids") or {})
        result = upload_or_update_file(
            drive_service,
            self.paths.registry_path,
            parent_id=source_folder_id,
            existing_file_id=source_ids.get(self.paths.registry_path.name),
        )
        source_ids[self.paths.registry_path.name] = result["id"]
        local_state["drive_source_file_ids"] = source_ids
        return result

    def run(self, options: GmailRunOptions) -> dict[str, Any]:
        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Another Gmail run or save is already in progress.")
        try:
            return self._run_locked(options)
        finally:
            self._mutation_lock.release()

    def _run_locked(self, options: GmailRunOptions) -> dict[str, Any]:
        query = options.resolved_query()
        config = RunConfig(
            gmail_query=query,
            owner_id="personal",
            active_sources=list(options.sources),
            company_allowlist=list(options.company_allowlist),
            include_unmatched_companies=options.include_unmatched_companies,
            lookback_days=int(options.lookback_days),
            dry_run=True,
            spreadsheet_id=None,
            max_messages=int(options.max_messages),
            target_experience_min_years=float(options.target_experience_min_years),
            target_experience_max_years=float(options.target_experience_max_years),
            experience_filter_mode=(
                "exclude_outside" if options.strict_experience_filter else "show_all"
            ),
        )
        config.validate()
        credentials = self.google_connection.require_credentials()
        run_started_at = datetime.now(TIME_ZONE).replace(microsecond=0)
        local_path = self._run_workbook_path(run_started_at)
        local_state = load_local_state(self.paths.app_state_path)

        drive_service = build_drive_service(credentials)
        folders = ensure_job_hunt_folders(
            drive_service,
            run_date=run_started_at.date().isoformat(),
        )
        root_id = str(folders["root"]["id"])
        source_id = str(folders["source"]["id"])
        date_id = str(folders["date"]["id"])
        self._sync_registry_source(drive_service, source_id, local_state)

        seen_state, seen_state_file_id = self._load_seen_state_from_drive(
            drive_service,
            source_id,
        )
        reader = GoogleGmailReader.from_credentials(credentials)
        result = run_pipeline(config, reader)
        all_rows = [job.to_dict() for job in result.jobs]
        all_rows.sort(
            key=lambda job: (
                str(job.get("alert_source") or "").casefold(),
                str(job.get("company") or "").casefold(),
                str(job.get("title") or "").casefold(),
                str(job.get("source_url") or ""),
            )
        )
        export_rows, unchanged_count = select_new_or_changed_gmail_jobs(
            all_rows,
            seen_state,
        )
        export_rows, referral_stats = enrich_gmail_referrals(
            export_rows,
            self.paths.registry_path,
        )
        summary = asdict(result.summary)
        summary["jobs_unchanged_from_prior_runs"] = unchanged_count
        summary["jobs_exported_this_run"] = len(export_rows)
        summary.update(referral_stats)

        write_gmail_run_workbook(
            local_path,
            export_rows,
            summary,
            run_started_at=run_started_at,
        )
        verify_gmail_run_workbook(local_path, expected_rows=len(export_rows))
        drive_file = upload_or_update_file(
            drive_service,
            local_path,
            parent_id=date_id,
        )

        metadata = {
            "run_id": str(summary["run_id"]),
            "local_path": str(local_path),
            "run_started_at": run_started_at.isoformat(),
            "date_folder_id": date_id,
            "drive_file_id": str(drive_file["id"]),
            "drive_url": drive_file.get("webViewLink") or drive_file_url(drive_file["id"]),
        }
        local_state["drive_root_folder_id"] = root_id
        local_state["drive_source_folder_id"] = source_id
        local_state["last_gmail_run"] = metadata
        save_local_state(self.paths.app_state_path, local_state)

        updated_seen_state = update_gmail_run_state(
            seen_state,
            all_rows,
            completed_at=str(summary.get("finished_at") or run_started_at.isoformat()),
        )
        write_json_atomic(self.paths.gmail_seen_state_path, updated_seen_state)
        seen_state_file = upload_or_update_file(
            drive_service,
            self.paths.gmail_seen_state_path,
            parent_id=source_id,
            existing_file_id=seen_state_file_id,
            mime_type="application/json",
        )
        source_ids = dict(local_state.get("drive_source_file_ids") or {})
        source_ids[GMAIL_SEEN_STATE_NAME] = seen_state_file["id"]
        local_state["drive_source_file_ids"] = source_ids
        local_state["last_gmail_run"] = metadata
        save_local_state(self.paths.app_state_path, local_state)
        return self._artifact_payload(metadata, export_rows, summary)

    def latest(self) -> dict[str, Any] | None:
        state = load_local_state(self.paths.app_state_path)
        metadata = state.get("last_gmail_run")
        if not isinstance(metadata, Mapping):
            return None
        local_path = self._safe_artifact_path(metadata.get("local_path"))
        if local_path is None or not local_path.is_file():
            return None
        rows, summary = read_gmail_run_workbook(local_path)
        rows, referral_stats = enrich_gmail_referrals(rows, self.paths.registry_path)
        summary.update(referral_stats)
        normalized_metadata = dict(metadata)
        normalized_metadata["run_id"] = str(
            normalized_metadata.get("run_id") or summary.get("run_id") or ""
        )
        return self._artifact_payload(normalized_metadata, rows, summary)

    def get(self, run_id: str) -> dict[str, Any]:
        artifact = self.latest()
        if artifact is None or artifact.get("run_id") != str(run_id):
            raise FileNotFoundError("The requested Gmail run is not available locally.")
        return artifact

    def save(self, run_id: str, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Another Gmail run or save is already in progress.")
        try:
            return self._save_locked(run_id, rows)
        finally:
            self._mutation_lock.release()

    def _save_locked(
        self,
        run_id: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        artifact = self.get(run_id)
        expected_ids = [row["job_record_id"] for row in artifact["rows"]]
        edited_rows = validate_editor_rows(rows, expected_record_ids=expected_ids)
        edited_rows, referral_stats = enrich_gmail_referrals(
            edited_rows,
            self.paths.registry_path,
        )
        updated_summary = dict(artifact["summary"])
        updated_summary.update(referral_stats)
        state = load_local_state(self.paths.app_state_path)
        metadata = dict(state.get("last_gmail_run") or {})
        local_path = self._safe_artifact_path(metadata.get("local_path"))
        if local_path is None or not local_path.is_file():
            raise FileNotFoundError("The local Gmail run workbook is unavailable.")
        drive_file_id = str(metadata.get("drive_file_id") or "")
        date_folder_id = str(metadata.get("date_folder_id") or "")
        if not drive_file_id or not date_folder_id:
            raise RuntimeError("The Drive identity for this Gmail run is unavailable.")

        run_started_at = datetime.fromisoformat(str(metadata["run_started_at"]))
        pending_path = local_path.with_name(f"{local_path.stem}.pending.xlsx")
        write_gmail_run_workbook(
            pending_path,
            edited_rows,
            updated_summary,
            run_started_at=run_started_at,
        )
        verify_gmail_run_workbook(pending_path, expected_rows=len(edited_rows))
        try:
            credentials = self.google_connection.require_credentials()
            drive_service = build_drive_service(credentials)
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
        metadata["drive_url"] = drive_file.get("webViewLink") or drive_file_url(drive_file["id"])
        state["last_gmail_run"] = metadata
        save_local_state(self.paths.app_state_path, state)
        return self._artifact_payload(metadata, edited_rows, updated_summary)

    def workbook_path(self, run_id: str) -> Path:
        self.get(run_id)
        state = load_local_state(self.paths.app_state_path)
        local_path = self._safe_artifact_path((state.get("last_gmail_run") or {}).get("local_path"))
        if local_path is None or not local_path.is_file():
            raise FileNotFoundError("The Gmail run workbook is unavailable.")
        return local_path

    def workspace(self) -> dict[str, str]:
        state = load_local_state(self.paths.app_state_path)
        root_id = str(state.get("drive_root_folder_id") or "")
        source_id = str(state.get("drive_source_folder_id") or "")
        return {
            "root_url": drive_folder_url(root_id) if root_id else "",
            "source_url": drive_folder_url(source_id) if source_id else "",
        }

    def _safe_artifact_path(self, value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value)).resolve()
        try:
            path.relative_to(self.paths.run_output_root.resolve())
        except ValueError:
            return None
        return path

    @staticmethod
    def _artifact_payload(
        metadata: Mapping[str, Any],
        rows: Iterable[Mapping[str, Any]],
        summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_rows = [dict(row) for row in rows]
        run_id = str(metadata.get("run_id") or summary.get("run_id") or "")
        return {
            "run_id": run_id,
            "run_started_at": str(metadata.get("run_started_at") or ""),
            "file_name": Path(str(metadata.get("local_path") or "gmail_alerts.xlsx")).name,
            "drive_url": str(metadata.get("drive_url") or ""),
            "summary": dict(summary),
            "rows": normalized_rows,
            "job_columns": list(GMAIL_RUN_COLUMNS),
            "editable_columns": sorted(EDITABLE_GMAIL_COLUMNS),
            "application_statuses": list(APPLICATION_STATUSES),
            "experience_fit_statuses": list(EXPERIENCE_FIT_STATUSES),
        }


def service_error_message(exc: Exception) -> str:
    """Public error boundary that never serializes Google or Gmail payloads."""

    return _safe_error(exc)
