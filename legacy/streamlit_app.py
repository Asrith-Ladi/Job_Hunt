"""Streamlit entry point for the personal, source-separated job-hunt workflow."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from job_hunt.config import RunConfig
from job_hunt.gmail_run_state import (
    normalize_gmail_run_state,
    select_new_or_changed_gmail_jobs,
    update_gmail_run_state,
)
from job_hunt.gmail_workbook import (
    APPLICATION_STATUSES,
    EDITABLE_GMAIL_COLUMNS,
    EXPERIENCE_FIT_STATUSES,
    normalize_editor_rows,
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
from job_hunt.integrations.sheets import JOB_COLUMNS
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
PROJECT_ROOT = Path(__file__).resolve().parent
RUN_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "gmail_runs"
REGISTRY_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "mnc_registry_2026-07-31"
    / "Company_Source_Registry.xlsx"
)
GMAIL_SEEN_STATE_PATH = PROJECT_ROOT / ".secrets" / "gmail_seen_state.json"
GMAIL_SEEN_STATE_NAME = "gmail_seen_state.json"
SOURCE_TAB_LABELS = [
    "1 · Gmail Alerts",
    "2 · Company Portals",
    "3 · ATS Sources",
]


def _split_lines(value):
    return [line.strip() for line in value.splitlines() if line.strip()]


def _build_gmail_query(sources, labels_by_source, lookback_days):
    label_terms = [
        "label:{0}".format(labels_by_source[source].strip())
        for source in sources
        if labels_by_source.get(source, "").strip()
    ]
    if not label_terms:
        return ""
    label_query = " ".join(label_terms)
    if len(label_terms) > 1:
        label_query = "{{{0}}}".format(label_query)
    return "{0} newer_than:{1}d".format(label_query, int(lookback_days))


def _query_param_value(query_params, name):
    value = query_params.get(name)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "")


def _streamlit_secret(st, name, default=""):
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        value = st.secrets.get(name, default)
    except (FileNotFoundError, KeyError):
        return default
    return str(value or default).strip()


def _run_workbook_path(run_started_at: datetime) -> Path:
    date_text = run_started_at.date().isoformat()
    timestamp = run_started_at.strftime("%Y-%m-%d_%H%M%S")
    return RUN_OUTPUT_ROOT / date_text / f"gmail_alerts_{timestamp}.xlsx"


def _credentials_ui(st):
    project_credentials = PROJECT_ROOT / "oauth-client.json"
    default_credentials = os.environ.get("JOB_HUNT_GOOGLE_CREDENTIALS", "").strip()
    if not default_credentials and project_credentials.is_file():
        default_credentials = str(project_credentials)
    credentials_path = st.text_input(
        "OAuth Web application credentials JSON path",
        value=default_credentials,
        help="This local secret is never copied to Google Drive or a run workbook.",
    )
    credential_file = (
        Path(credentials_path.strip()).expanduser() if credentials_path.strip() else None
    )
    token_path = PROJECT_ROOT / ".secrets" / "google_token.json"
    oauth_state_path = PROJECT_ROOT / ".secrets" / "google_oauth_state.json"
    redirect_uri = os.environ.get(
        "JOB_HUNT_OAUTH_REDIRECT_URI", "http://localhost:8501/"
    ).strip()
    st.caption("OAuth callback URI: `{0}`".format(redirect_uri))

    callback_error = _query_param_value(st.query_params, "error")
    callback_code = _query_param_value(st.query_params, "code")
    callback_state = _query_param_value(st.query_params, "state")

    if callback_error:
        consume_pending_oauth_state(oauth_state_path, callback_state)
        st.query_params.clear()
        st.error("Google authorization was cancelled or denied. No mailbox data was read.")
    elif callback_code:
        code_verifier = None
        if credential_file is not None and credential_file.is_file():
            code_verifier = consume_pending_oauth_state(oauth_state_path, callback_state)
        if credential_file is None or not credential_file.is_file():
            st.query_params.clear()
            st.error(
                "The OAuth credentials path is unavailable. Set the environment variable "
                "and restart Streamlit before connecting Google."
            )
        elif not code_verifier:
            st.query_params.clear()
            st.error("The Google callback was invalid or expired. Start the connection again.")
        else:
            try:
                exchange_authorization_code(
                    credentials_path=credential_file,
                    token_path=token_path,
                    redirect_uri=redirect_uri,
                    code=callback_code,
                    state=callback_state,
                    code_verifier=code_verifier,
                )
            except (ValueError, FileNotFoundError, RuntimeError) as exc:
                st.query_params.clear()
                st.error(str(exc))
            else:
                st.query_params.clear()
                st.session_state.pop("google_auth_request", None)
                st.rerun()

    try:
        credentials = load_stored_credentials(token_path)
    except RuntimeError as exc:
        st.error(str(exc))
        credentials = None

    if credentials is None:
        st.warning("Google is not connected yet.")
        if credential_file is None or not credential_file.is_file():
            st.info(
                "Set `JOB_HUNT_GOOGLE_CREDENTIALS` to the downloaded Web OAuth JSON path "
                "in the same terminal that starts Streamlit."
            )
        elif st.button("Prepare Google connection"):
            try:
                authorization_url, oauth_state, code_verifier = create_authorization_url(
                    credential_file, redirect_uri
                )
                save_pending_oauth_state(oauth_state_path, oauth_state, code_verifier)
                st.session_state["google_auth_request"] = {
                    "url": authorization_url,
                    "credentials_path": str(credential_file),
                    "redirect_uri": redirect_uri,
                }
            except (ValueError, FileNotFoundError, RuntimeError) as exc:
                st.error(str(exc))

        auth_request = st.session_state.get("google_auth_request")
        if (
            auth_request
            and auth_request.get("credentials_path") == str(credential_file)
            and auth_request.get("redirect_uri") == redirect_uri
        ):
            st.link_button("Continue with Google", auth_request["url"], type="primary")
        st.stop()
    return credentials


def _load_seen_state_from_drive(drive_service, source_folder_id: str) -> tuple[dict, str]:
    local_value = read_json(GMAIL_SEEN_STATE_PATH)
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
            GMAIL_SEEN_STATE_PATH,
        )
        local_value = read_json(GMAIL_SEEN_STATE_PATH)
    return normalize_gmail_run_state(local_value), str((remote or {}).get("id") or "")


def _sync_registry_source(
    drive_service,
    source_folder_id: str,
    local_state: dict[str, Any],
) -> dict[str, Any] | None:
    if not REGISTRY_PATH.is_file():
        return None
    source_ids = dict(local_state.get("drive_source_file_ids") or {})
    result = upload_or_update_file(
        drive_service,
        REGISTRY_PATH,
        parent_id=source_folder_id,
        existing_file_id=source_ids.get(REGISTRY_PATH.name),
    )
    source_ids[REGISTRY_PATH.name] = result["id"]
    local_state["drive_source_file_ids"] = source_ids
    return result


def _load_last_local_run(st, local_state: dict[str, Any]) -> None:
    if st.session_state.get("gmail_run_artifact"):
        return
    metadata = local_state.get("last_gmail_run")
    if not isinstance(metadata, dict):
        return
    local_path = Path(str(metadata.get("local_path") or ""))
    if not local_path.is_file():
        return
    try:
        rows, summary = read_gmail_run_workbook(local_path)
    except (OSError, ValueError):
        return
    restored = dict(metadata)
    restored["rows"] = rows
    restored["summary"] = summary
    st.session_state["gmail_run_artifact"] = restored


def _editor_column_config(st):
    return {
        "source_url": st.column_config.LinkColumn("source_url", display_text="Open alert"),
        "official_url": st.column_config.LinkColumn(
            "official_url", display_text="Open official job"
        ),
        "application_status": st.column_config.SelectboxColumn(
            "application_status",
            options=APPLICATION_STATUSES,
            required=True,
        ),
        "experience_fit": st.column_config.SelectboxColumn(
            "experience_fit",
            options=EXPERIENCE_FIT_STATUSES,
            required=True,
        ),
        "experience_min_years": st.column_config.NumberColumn(
            "experience_min_years", min_value=0.0, step=0.5, format="%.1f"
        ),
        "experience_max_years": st.column_config.NumberColumn(
            "experience_max_years", min_value=0.0, step=0.5, format="%.1f"
        ),
    }


def _show_gmail_run(st, credentials, local_state: dict[str, Any]) -> None:
    artifact = st.session_state.get("gmail_run_artifact")
    if not artifact:
        st.info("Run Gmail alerts to create and display the first dated workbook.")
        return

    rows = artifact.get("rows") or []
    summary = artifact.get("summary") or {}
    parsed = int(summary.get("jobs_parsed") or 0)
    deduplicated = int(summary.get("jobs_after_deduplication") or 0)
    unchanged = int(summary.get("jobs_unchanged_from_prior_runs") or 0)
    metric_columns = st.columns(5)
    metric_columns[0].metric("Emails read", int(summary.get("messages_read") or 0))
    metric_columns[1].metric("Jobs parsed", parsed)
    metric_columns[2].metric("Within-run duplicates", max(0, parsed - deduplicated))
    metric_columns[3].metric("Previously seen", unchanged)
    metric_columns[4].metric("Rows in this file", len(rows))

    st.caption(
        "All run rows are shown here. Editable columns are company, title, location, "
        "experience, official URL, application status, and notes."
    )
    if rows:
        disabled_columns = [
            column for column in JOB_COLUMNS if column not in EDITABLE_GMAIL_COLUMNS
        ]
        edited = st.data_editor(
            rows,
            column_order=JOB_COLUMNS,
            column_config=_editor_column_config(st),
            disabled=disabled_columns,
            hide_index=True,
            width="stretch",
            height=650,
            num_rows="fixed",
            key="gmail_editor_{0}".format(summary.get("run_id") or "current"),
        )
        st.caption("Edits stay on screen until **Save changes to Excel and Drive** is used.")
        if st.button("Save changes to Excel and Drive", type="primary"):
            try:
                edited_rows = normalize_editor_rows(edited)
                expected_ids = [row["job_record_id"] for row in rows]
                edited_rows = validate_editor_rows(
                    edited_rows,
                    expected_record_ids=expected_ids,
                )
                local_path = Path(artifact["local_path"])
                run_started_at = datetime.fromisoformat(artifact["run_started_at"])
                write_gmail_run_workbook(
                    local_path,
                    edited_rows,
                    summary,
                    run_started_at=run_started_at,
                )
                verify_gmail_run_workbook(local_path, expected_rows=len(edited_rows))
                drive_service = build_drive_service(credentials)
                drive_file = upload_or_update_file(
                    drive_service,
                    local_path,
                    parent_id=str(artifact["date_folder_id"]),
                    existing_file_id=str(artifact.get("drive_file_id") or ""),
                )
                artifact["rows"] = edited_rows
                artifact["drive_file_id"] = drive_file["id"]
                artifact["drive_url"] = drive_file.get("webViewLink") or drive_file_url(
                    drive_file["id"]
                )
                local_state["last_gmail_run"] = {
                    key: value for key, value in artifact.items() if key not in {"rows", "summary"}
                }
                save_local_state(PROJECT_ROOT / ".secrets" / "app_state.json", local_state)
            except (OSError, ValueError, FileNotFoundError, RuntimeError) as exc:
                st.error(f"Changes were not saved: {exc}")
            else:
                st.success("The same run workbook was updated locally and in Google Drive.")
    else:
        st.success("No new or changed Gmail jobs were found in this run.")

    local_path = Path(artifact["local_path"])
    if artifact.get("drive_url"):
        st.link_button("Open this Gmail run in Drive", artifact["drive_url"])
    if local_path.is_file():
        st.download_button(
            "Download this Gmail run workbook",
            data=local_path.read_bytes(),
            file_name=local_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def _run_gmail_phase(
    st,
    credentials,
    local_state: dict[str, Any],
    *,
    sources,
    gmail_query,
    companies_text,
    include_unmatched,
    lookback_days,
    max_messages,
    target_experience_min,
    target_experience_max,
    strict_experience_filter,
) -> None:
    config = RunConfig(
        gmail_query=gmail_query,
        owner_id="personal",
        active_sources=list(sources),
        company_allowlist=_split_lines(companies_text),
        include_unmatched_companies=include_unmatched,
        lookback_days=int(lookback_days),
        dry_run=True,
        spreadsheet_id=None,
        max_messages=int(max_messages),
        target_experience_min_years=float(target_experience_min),
        target_experience_max_years=float(target_experience_max),
        experience_filter_mode=(
            "exclude_outside" if strict_experience_filter else "show_all"
        ),
    )
    run_started_at = datetime.now(TIME_ZONE).replace(microsecond=0)
    local_path = _run_workbook_path(run_started_at)
    try:
        with st.status("Running the Gmail-only workflow...", expanded=True) as run_status:
            config.validate()
            drive_service = build_drive_service(credentials)
            folders = ensure_job_hunt_folders(
                drive_service,
                run_date=run_started_at.date().isoformat(),
            )
            root_id = str(folders["root"]["id"])
            source_id = str(folders["source"]["id"])
            date_id = str(folders["date"]["id"])
            run_status.write("Prepared Job Hunt/Source and the current date folder in Drive.")

            registry_file = _sync_registry_source(drive_service, source_id, local_state)
            if registry_file:
                run_status.write("Synchronized Company_Source_Registry.xlsx into Source.")

            seen_state, seen_state_file_id = _load_seen_state_from_drive(
                drive_service, source_id
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
                all_rows, seen_state
            )
            summary = asdict(result.summary)
            summary["jobs_unchanged_from_prior_runs"] = unchanged_count
            summary["jobs_exported_this_run"] = len(export_rows)
            run_status.write(
                f"Parsed {len(all_rows)} unique current jobs; "
                f"{len(export_rows)} are new or changed since successful prior runs."
            )

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
            run_status.write(f"Uploaded {local_path.name} to the dated Drive folder.")

            updated_seen_state = update_gmail_run_state(
                seen_state,
                all_rows,
                completed_at=str(summary.get("finished_at") or run_started_at.isoformat()),
            )
            write_json_atomic(GMAIL_SEEN_STATE_PATH, updated_seen_state)
            seen_state_file = upload_or_update_file(
                drive_service,
                GMAIL_SEEN_STATE_PATH,
                parent_id=source_id,
                existing_file_id=seen_state_file_id,
                mime_type="application/json",
            )

            metadata = {
                "local_path": str(local_path),
                "run_started_at": run_started_at.isoformat(),
                "date_folder_id": date_id,
                "drive_file_id": str(drive_file["id"]),
                "drive_url": drive_file.get("webViewLink")
                or drive_file_url(drive_file["id"]),
            }
            local_state["drive_root_folder_id"] = root_id
            local_state["drive_source_folder_id"] = source_id
            source_ids = dict(local_state.get("drive_source_file_ids") or {})
            source_ids[GMAIL_SEEN_STATE_NAME] = seen_state_file["id"]
            local_state["drive_source_file_ids"] = source_ids
            local_state["last_gmail_run"] = metadata
            save_local_state(PROJECT_ROOT / ".secrets" / "app_state.json", local_state)
            st.session_state["gmail_run_artifact"] = {
                **metadata,
                "rows": export_rows,
                "summary": summary,
            }
            run_status.update(label="Gmail workflow completed", state="complete")
    except Exception as exc:  # UI boundary: never expose API payloads or email bodies
        if isinstance(exc, (ValueError, FileNotFoundError, RuntimeError, OSError)):
            detail = str(exc)
        else:
            detail = type(exc).__name__
        st.error(f"Gmail run failed: {detail}")
        if local_path.is_file():
            st.info(f"A recoverable local workbook remains at {local_path}.")


def main():
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise SystemExit(
            "Streamlit is not installed. Use Python 3.12 and run `pip install -e .`."
        ) from exc

    st.set_page_config(page_title="Personal Job Hunt", layout="wide")
    st.title("Personal Job Hunt")
    st.caption(
        "Three independent discovery paths: Gmail alerts, company portals, and structured ATS sources"
    )
    credentials = _credentials_ui(st)
    st.success("Google connected: read-only Gmail plus app-created Drive files.")

    state_path = PROJECT_ROOT / ".secrets" / "app_state.json"
    local_state = load_local_state(state_path)
    _load_last_local_run(st, local_state)

    with st.sidebar:
        st.header("Gmail run settings")
        sources = st.multiselect(
            "Alert sources", ["linkedin", "naukri"], default=["linkedin", "naukri"]
        )
        linkedin_label = st.text_input(
            "LinkedIn Gmail label", value=DEFAULT_SOURCE_LABELS["linkedin"]
        )
        naukri_label = st.text_input(
            "Naukri Gmail label", value=DEFAULT_SOURCE_LABELS["naukri"]
        )
        lookback_days = st.number_input(
            "Rolling Gmail lookback (days)",
            min_value=1,
            max_value=90,
            value=DEFAULT_LOOKBACK_DAYS,
        )
        max_messages = st.number_input(
            "Maximum Gmail messages",
            min_value=1,
            max_value=5000,
            value=DEFAULT_MAX_MESSAGES,
        )
        companies_text = st.text_area(
            "Company list (optional, one per line)",
            help="Uncertain company parsing remains visible unless you turn it off.",
        )
        include_unmatched = st.checkbox(
            "Keep unmatched/unknown companies", value=True
        )
        target_experience_min = st.number_input(
            "Target minimum experience", min_value=0.0, value=5.0, step=0.5
        )
        target_experience_max = st.number_input(
            "Target maximum experience", min_value=0.0, value=8.0, step=0.5
        )
        strict_experience_filter = st.checkbox(
            "Exclude roles known outside the target range",
            value=False,
            help="Roles with missing experience remain visible.",
        )
        st.caption(
            "A Gmail run never invokes OpenAI, searches a portal, or sends an application."
        )

    labels_by_source = {
        "linkedin": linkedin_label.strip(),
        "naukri": naukri_label.strip(),
    }
    default_query = _build_gmail_query(sources, labels_by_source, lookback_days)

    gmail_tab, company_tab, ats_tab = st.tabs(SOURCE_TAB_LABELS)
    with gmail_tab:
        st.subheader("Gmail alerts")
        st.write(
            "Read approved labels, parse and deduplicate jobs, create one dated Excel "
            "run file, upload it to Drive, and review or edit every row here."
        )
        gmail_query = st.text_input("Gmail query", value=default_query)
        root_id = str(local_state.get("drive_root_folder_id") or "")
        if root_id:
            st.link_button("Open Job Hunt folder in Drive", drive_folder_url(root_id))
        if st.button("Run Gmail alerts", type="primary"):
            _run_gmail_phase(
                st,
                credentials,
                local_state,
                sources=sources,
                gmail_query=gmail_query,
                companies_text=companies_text,
                include_unmatched=include_unmatched,
                lookback_days=lookback_days,
                max_messages=max_messages,
                target_experience_min=target_experience_min,
                target_experience_max=target_experience_max,
                strict_experience_filter=strict_experience_filter,
            )
        _show_gmail_run(st, credentials, local_state)

    with company_tab:
        st.subheader("Company portals from the Excel registry")
        st.info(
            "Planned second phase. This tab will rotate through official portals stored "
            "in Company_Source_Registry.xlsx after the Gmail phase is approved."
        )

    with ats_tab:
        st.subheader("Structured ATS sources")
        st.info(
            "Planned third phase. This tab will use confirmed Greenhouse, Lever, Workable, "
            "SmartRecruiters, and similar structured sources without mixing them into Gmail."
        )


if __name__ == "__main__":
    main()
