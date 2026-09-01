"""Gmail application services used by the React/FastAPI boundary.

The module keeps Google credentials and raw Gmail messages behind the Python
boundary.  Callers receive only normalized job rows, run summaries, and links
to app-owned Drive resources.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from job_hunt.gmail.config import RunConfig
from job_hunt.gmail.state import (
    append_gmail_run_history,
    normalize_gmail_run_state,
    select_new_or_changed_gmail_jobs,
    update_gmail_run_state,
)
from job_hunt.network.referrals import enrich_gmail_referrals
from job_hunt.gmail.workbook import (
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
from job_hunt.runtime.state import load_local_state, save_local_state
from job_hunt.gmail.pipeline import run_pipeline
from job_hunt.runtime.files import read_json, write_json_atomic
from job_hunt.runtime.google import GoogleConnectionService
from job_hunt.runtime.paths import AppPaths, GMAIL_SEEN_STATE_NAME, TIME_ZONE


DEFAULT_SOURCE_LABELS = {
    "linkedin": "Job_Alerts/LinkedIn",
    "naukri": "Job_Alerts/Naukari",
}
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MAX_MESSAGES = 500
HISTORICAL_EDITABLE_COLUMNS = {"application_status", "notes"}


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
                "applications",
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

    @staticmethod
    def _run_config(options: GmailRunOptions) -> RunConfig:
        return RunConfig(
            gmail_query=options.resolved_query(),
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

    def search(
        self,
        options: GmailRunOptions,
        *,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Read and normalize the current matching alerts without creating an artifact."""

        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Another Gmail search or application update is already in progress.")
        try:
            return self._search_locked(options, progress_callback=progress_callback)
        finally:
            self._mutation_lock.release()

    def _search_locked(
        self,
        options: GmailRunOptions,
        *,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        config = self._run_config(options)
        config.validate()
        credentials = self.google_connection.require_credentials()
        run_started_at = datetime.now(TIME_ZONE).replace(microsecond=0)
        reader = GoogleGmailReader.from_credentials(credentials)
        result = run_pipeline(config, reader, progress_callback=progress_callback)
        rows = [job.to_dict() for job in result.jobs]
        rows.sort(
            key=lambda job: (
                str(job.get("alert_source") or "").casefold(),
                str(job.get("company") or "").casefold(),
                str(job.get("title") or "").casefold(),
                str(job.get("source_url") or ""),
            )
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "gmail_referrals",
                    "message": "Matching saved LinkedIn connections to job companies.",
                    "current_item": "Offline referral matching",
                    "completed_items": len(rows),
                    "total_items": len(rows),
                    "matches_found": len(rows),
                }
            )
        rows, referral_stats = enrich_gmail_referrals(rows, self.paths.registry_path)
        summary = asdict(result.summary)
        summary["jobs_returned_this_search"] = len(rows)
        summary["jobs_exported_this_run"] = 0
        summary["jobs_unchanged_from_prior_runs"] = 0
        summary["persistence"] = "temporary_search"
        summary.update(referral_stats)
        metadata = {
            "run_id": str(summary["run_id"]),
            "run_started_at": run_started_at.isoformat(),
            "transient": True,
        }
        return self._artifact_payload(metadata, rows, summary)

    def run(self, options: GmailRunOptions) -> dict[str, Any]:
        if not self._mutation_lock.acquire(blocking=False):
            raise RuntimeError("Another Gmail run or save is already in progress.")
        try:
            return self._run_locked(options)
        finally:
            self._mutation_lock.release()

    def _run_locked(self, options: GmailRunOptions) -> dict[str, Any]:
        config = self._run_config(options)
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
        updated_seen_state = append_gmail_run_history(
            updated_seen_state,
            {
                "run_id": metadata["run_id"],
                "run_started_at": metadata["run_started_at"],
                "file_name": local_path.name,
                "date_folder_id": metadata["date_folder_id"],
                "drive_file_id": metadata["drive_file_id"],
                "drive_url": metadata["drive_url"],
                "rows_exported": len(export_rows),
                "messages_read": summary.get("messages_read"),
                "unique_jobs": summary.get("jobs_after_deduplication"),
                "unchanged_jobs": summary.get("jobs_unchanged_from_prior_runs"),
                "status": summary.get("status"),
            },
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
        run_id = str(metadata.get("run_id") or "").strip()
        if not run_id:
            return None
        try:
            return self.get(run_id)
        except FileNotFoundError:
            return None

    def _local_run_paths(self) -> list[Path]:
        root = self.paths.run_output_root.resolve()
        if not root.is_dir():
            return []
        paths: list[Path] = []
        for candidate in root.glob("*/*.xlsx"):
            path = candidate.resolve()
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if (
                path.is_file()
                and path.name.startswith("gmail_alerts_")
                and ".pending" not in path.name
            ):
                paths.append(path)
        return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)

    @staticmethod
    def _path_run_started_at(path: Path) -> str:
        timestamp = path.stem.removeprefix("gmail_alerts_")
        try:
            parsed = datetime.strptime(timestamp, "%Y-%m-%d_%H%M%S").replace(
                tzinfo=TIME_ZONE
            )
        except ValueError:
            parsed = datetime.fromtimestamp(path.stat().st_mtime, TIME_ZONE)
        return parsed.replace(microsecond=0).isoformat()

    @staticmethod
    def _history_sort_value(record: Mapping[str, Any]) -> float:
        try:
            return datetime.fromisoformat(str(record.get("run_started_at") or "")).timestamp()
        except (TypeError, ValueError):
            return 0.0

    def _history_records(self) -> list[dict[str, Any]]:
        seen_state = normalize_gmail_run_state(read_json(self.paths.gmail_seen_state_path))
        records = {
            str(record.get("run_id") or ""): {
                **dict(record),
                "_local_path": "",
                "loadable": bool(record.get("drive_file_id")),
            }
            for record in seen_state.get("run_history") or []
            if str(record.get("run_id") or "").strip()
        }
        app_state = load_local_state(self.paths.app_state_path)
        latest = dict(app_state.get("last_gmail_run") or {})
        latest_id = str(latest.get("run_id") or "")

        for path in self._local_run_paths():
            try:
                rows, summary = read_gmail_run_workbook(path)
            except (OSError, ValueError):
                continue
            run_id = str(summary.get("run_id") or "").strip()
            if not run_id:
                continue
            record = dict(records.get(run_id) or {})
            record.update(
                {
                    "run_id": run_id,
                    "run_started_at": str(
                        record.get("run_started_at") or self._path_run_started_at(path)
                    ),
                    "file_name": path.name,
                    "rows_exported": int(
                        summary.get("jobs_exported_this_run")
                        if summary.get("jobs_exported_this_run") is not None
                        else len(rows)
                    ),
                    "messages_read": int(summary.get("messages_read") or 0),
                    "unique_jobs": int(summary.get("jobs_after_deduplication") or 0),
                    "unchanged_jobs": int(
                        summary.get("jobs_unchanged_from_prior_runs") or 0
                    ),
                    "status": str(summary.get("status") or ""),
                    "_local_path": str(path),
                    "loadable": True,
                }
            )
            if run_id == latest_id:
                for field in (
                    "run_started_at",
                    "date_folder_id",
                    "drive_file_id",
                    "drive_url",
                ):
                    if latest.get(field):
                        record[field] = latest[field]
            records[run_id] = record

        for run_id, record in records.items():
            record["is_current"] = run_id == latest_id
        return sorted(records.values(), key=self._history_sort_value, reverse=True)

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        """List prior normalized Gmail runs without returning their job rows."""

        limit = max(1, min(int(limit), 200))
        public_fields = (
            "run_id",
            "run_started_at",
            "file_name",
            "drive_url",
            "rows_exported",
            "messages_read",
            "unique_jobs",
            "unchanged_jobs",
            "status",
            "is_current",
            "loadable",
        )
        return [
            {field: record.get(field, "") for field in public_fields}
            for record in self._history_records()[:limit]
        ]

    def _history_record(self, run_id: str) -> dict[str, Any]:
        requested = str(run_id or "").strip()
        for record in self._history_records():
            if str(record.get("run_id") or "") == requested:
                return record
        raise FileNotFoundError("The requested Gmail run is unavailable.")

    def _materialize_history_record(self, record: Mapping[str, Any]) -> Path:
        local_path = self._safe_artifact_path(record.get("_local_path"))
        if local_path is not None and local_path.is_file():
            return local_path

        file_name = Path(str(record.get("file_name") or "")).name
        if (
            not file_name.startswith("gmail_alerts_")
            or Path(file_name).suffix.casefold() != ".xlsx"
        ):
            raise FileNotFoundError("The historical Gmail workbook name is invalid.")
        drive_file_id = str(record.get("drive_file_id") or "").strip()
        if not drive_file_id:
            raise FileNotFoundError("This historical Gmail workbook is unavailable locally.")
        try:
            run_date = datetime.fromisoformat(
                str(record.get("run_started_at") or "")
            ).date().isoformat()
        except ValueError as exc:
            raise FileNotFoundError("The historical Gmail run date is invalid.") from exc
        output_path = self.paths.run_output_root / run_date / file_name
        credentials = self.google_connection.require_credentials()
        drive = build_drive_service(credentials)
        download_drive_file(drive, drive_file_id, output_path)
        rows, summary = read_gmail_run_workbook(output_path)
        if str(summary.get("run_id") or "") != str(record.get("run_id") or ""):
            output_path.unlink(missing_ok=True)
            raise FileNotFoundError("The downloaded Gmail workbook identity did not match.")
        verify_gmail_run_workbook(output_path, expected_rows=len(rows))
        return output_path

    def get(self, run_id: str) -> dict[str, Any]:
        record = self._history_record(run_id)
        local_path = self._materialize_history_record(record)
        rows, summary = read_gmail_run_workbook(local_path)
        rows, referral_stats = enrich_gmail_referrals(rows, self.paths.registry_path)
        summary.update(referral_stats)
        metadata = {
            **dict(record),
            "local_path": str(local_path),
            "historical": not bool(record.get("is_current")),
            "review_only": False,
        }
        return self._artifact_payload(metadata, rows, summary)

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
        state = load_local_state(self.paths.app_state_path)
        latest_id = str((state.get("last_gmail_run") or {}).get("run_id") or "")
        historical = str(run_id) != latest_id
        record = self._history_record(run_id)
        artifact = self.get(run_id)
        expected_ids = [row["job_record_id"] for row in artifact["rows"]]
        submitted_rows = validate_editor_rows(rows, expected_record_ids=expected_ids)
        submitted_by_id = {
            str(row["job_record_id"]): row
            for row in submitted_rows
        }
        allowed_columns = (
            HISTORICAL_EDITABLE_COLUMNS if historical else EDITABLE_GMAIL_COLUMNS
        )
        edited_rows: list[dict[str, Any]] = []
        for original_row in artifact["rows"]:
            original = dict(original_row)
            submitted = submitted_by_id[str(original["job_record_id"])]
            for column in allowed_columns:
                original[column] = submitted.get(column, "")
            edited_rows.append(original)
        edited_rows, referral_stats = enrich_gmail_referrals(
            edited_rows,
            self.paths.registry_path,
        )
        updated_summary = dict(artifact["summary"])
        updated_summary.update(referral_stats)
        local_path = self._materialize_history_record(record)
        run_started_at = datetime.fromisoformat(str(record["run_started_at"]))
        pending_path = local_path.parent / ".pending" / local_path.name
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
            folders = ensure_job_hunt_folders(
                drive_service,
                run_date=run_started_at.date().isoformat(),
            )
            root_id = str(folders["root"]["id"])
            source_id = str(folders["source"]["id"])
            date_folder_id = str(folders["date"]["id"])
            drive_file = upload_or_update_file(
                drive_service,
                pending_path,
                parent_id=date_folder_id,
                existing_file_id=str(record.get("drive_file_id") or ""),
            )
            pending_path.replace(local_path)
        finally:
            if pending_path.exists():
                pending_path.unlink()
            try:
                pending_path.parent.rmdir()
            except OSError:
                pass

        metadata = {
            **dict(record),
            "run_id": str(run_id),
            "local_path": str(local_path),
            "run_started_at": run_started_at.isoformat(),
            "date_folder_id": date_folder_id,
            "drive_file_id": str(drive_file["id"]),
            "drive_url": drive_file.get("webViewLink") or drive_file_url(drive_file["id"]),
            "historical": historical,
            "review_only": False,
        }
        current_seen_state, seen_state_file_id = self._load_seen_state_from_drive(
            drive_service,
            source_id,
        )
        seen_state = append_gmail_run_history(
            current_seen_state,
            {
                "run_id": metadata["run_id"],
                "run_started_at": metadata["run_started_at"],
                "file_name": local_path.name,
                "date_folder_id": metadata["date_folder_id"],
                "drive_file_id": metadata["drive_file_id"],
                "drive_url": metadata["drive_url"],
                "rows_exported": len(edited_rows),
                "messages_read": updated_summary.get("messages_read"),
                "unique_jobs": updated_summary.get("jobs_after_deduplication"),
                "unchanged_jobs": updated_summary.get("jobs_unchanged_from_prior_runs"),
                "status": updated_summary.get("status"),
            },
        )
        write_json_atomic(self.paths.gmail_seen_state_path, seen_state)
        source_ids = dict(state.get("drive_source_file_ids") or {})
        seen_state_file = upload_or_update_file(
            drive_service,
            self.paths.gmail_seen_state_path,
            parent_id=source_id,
            existing_file_id=(
                seen_state_file_id or source_ids.get(GMAIL_SEEN_STATE_NAME)
            ),
            mime_type="application/json",
        )
        source_ids[GMAIL_SEEN_STATE_NAME] = str(seen_state_file["id"])
        state["drive_root_folder_id"] = root_id
        state["drive_source_folder_id"] = source_id
        state["drive_source_file_ids"] = source_ids
        if not historical:
            state["last_gmail_run"] = {
                key: value
                for key, value in metadata.items()
                if not key.startswith("_") and key not in {"historical", "review_only"}
            }
        save_local_state(self.paths.app_state_path, state)
        return self._artifact_payload(metadata, edited_rows, updated_summary)

    def workbook_path(self, run_id: str) -> Path:
        return self._materialize_history_record(self._history_record(run_id))

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
        normalized_rows: list[dict[str, Any]] = []
        referral_candidates: dict[str, list[dict[str, str]]] = {}
        for source_row in rows:
            row = dict(source_row)
            raw_candidates = row.pop("referral_candidates", [])
            record_id = str(row.get("job_record_id") or "").strip()
            candidates: list[dict[str, str]] = []
            if record_id and isinstance(raw_candidates, list):
                for raw_candidate in raw_candidates:
                    if not isinstance(raw_candidate, Mapping):
                        continue
                    candidate = {
                        key: str(raw_candidate.get(key) or "").strip()
                        for key in ("name", "position", "profile_url", "message")
                    }
                    if candidate["name"] and candidate["profile_url"]:
                        candidates.append(candidate)
            if candidates:
                referral_candidates[record_id] = candidates
            normalized_rows.append(row)
        run_id = str(metadata.get("run_id") or summary.get("run_id") or "")
        transient = bool(metadata.get("transient"))
        return {
            "run_id": run_id,
            "run_started_at": str(metadata.get("run_started_at") or ""),
            "file_name": (
                ""
                if transient
                else Path(str(metadata.get("local_path") or "gmail_alerts.xlsx")).name
            ),
            "drive_url": str(metadata.get("drive_url") or ""),
            "historical": bool(metadata.get("historical")),
            "review_only": bool(metadata.get("review_only")),
            "transient": bool(metadata.get("transient")),
            "summary": dict(summary),
            "rows": normalized_rows,
            "referral_candidates": referral_candidates,
            "job_columns": list(GMAIL_RUN_COLUMNS),
            "editable_columns": sorted(EDITABLE_GMAIL_COLUMNS),
            "application_statuses": list(APPLICATION_STATUSES),
            "experience_fit_statuses": list(EXPERIENCE_FIT_STATUSES),
        }


def service_error_message(exc: Exception) -> str:
    """Public error boundary that never serializes Google or Gmail payloads."""

    return _safe_error(exc)
