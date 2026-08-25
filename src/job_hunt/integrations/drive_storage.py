"""App-owned Google Drive folders and file synchronization for run artifacts."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
EXCEL_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
JOB_HUNT_FOLDER_NAME = "Job Hunt"
SOURCE_FOLDER_NAME = "Source"


def _google_drive_components():
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "Google client libraries are not installed. Run `pip install -e .`."
        ) from exc
    return build, MediaFileUpload, MediaIoBaseDownload


def build_drive_service(credentials):
    build, _, _ = _google_drive_components()
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _escape_query(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _find_child(drive_service, name: str, parent_id: str | None, mime_type: str):
    clauses = [
        f"name = '{_escape_query(name)}'",
        f"mimeType = '{_escape_query(mime_type)}'",
        "trashed = false",
    ]
    if parent_id:
        clauses.append(f"'{_escape_query(parent_id)}' in parents")
    response = (
        drive_service.files()
        .list(
            q=" and ".join(clauses),
            spaces="drive",
            fields=(
                "files(id,name,mimeType,parents,webViewLink,modifiedTime,"
                "md5Checksum,size)"
            ),
            pageSize=10,
        )
        .execute()
    )
    files = response.get("files") or []
    return files[0] if files else None


def find_child_file(
    drive_service,
    name: str,
    *,
    parent_id: str,
    mime_type: str,
) -> dict[str, Any] | None:
    """Find one app-visible file by exact name, parent, and MIME type."""

    return _find_child(drive_service, name, parent_id, mime_type)


def ensure_folder(
    drive_service,
    name: str,
    *,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Return an existing app-visible folder or create it once."""

    existing = _find_child(drive_service, name, parent_id, FOLDER_MIME_TYPE)
    if existing:
        return existing
    body: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME_TYPE}
    if parent_id:
        body["parents"] = [parent_id]
    return (
        drive_service.files()
        .create(
            body=body,
            fields="id,name,mimeType,parents,webViewLink",
        )
        .execute()
    )


def ensure_job_hunt_folders(
    drive_service,
    *,
    run_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Ensure ``Job Hunt/Source`` and optionally one date-named run folder."""

    root = ensure_folder(drive_service, JOB_HUNT_FOLDER_NAME)
    source = ensure_folder(
        drive_service,
        SOURCE_FOLDER_NAME,
        parent_id=str(root["id"]),
    )
    result = {"root": root, "source": source}
    if run_date:
        result["date"] = ensure_folder(
            drive_service,
            str(run_date),
            parent_id=str(root["id"]),
        )
    return result


def upload_or_update_file(
    drive_service,
    local_path: Path,
    *,
    parent_id: str,
    existing_file_id: str | None = None,
    mime_type: str = EXCEL_MIME_TYPE,
    uploader_factory=None,
) -> dict[str, Any]:
    """Upload a local file once, then replace its content on later UI saves."""

    local_path = Path(local_path)
    if not local_path.is_file():
        raise FileNotFoundError(f"Drive upload source was not found: {local_path.name}")
    _, default_uploader, _ = _google_drive_components()
    uploader_factory = uploader_factory or default_uploader
    media = uploader_factory(str(local_path), mimetype=mime_type, resumable=False)
    fields = "id,name,mimeType,parents,webViewLink,modifiedTime"

    file_id = str(existing_file_id or "").strip()
    if not file_id:
        existing = _find_child(
            drive_service,
            local_path.name,
            parent_id,
            mime_type,
        )
        file_id = str((existing or {}).get("id") or "")

    if file_id:
        return (
            drive_service.files()
            .update(
                fileId=file_id,
                media_body=media,
                fields=fields,
            )
            .execute()
        )
    return (
        drive_service.files()
        .create(
            body={
                "name": local_path.name,
                "parents": [str(parent_id)],
                "mimeType": mime_type,
            },
            media_body=media,
            fields=fields,
        )
        .execute()
    )


def download_drive_file(
    drive_service,
    file_id: str,
    output_path: Path,
    *,
    downloader_factory=None,
) -> Path:
    """Download one app-owned binary file and replace its local copy atomically."""

    _, _, default_downloader = _google_drive_components()
    downloader_factory = downloader_factory or default_downloader
    request = drive_service.files().get_media(fileId=str(file_id).strip())
    buffer = BytesIO()
    downloader = downloader_factory(buffer, request)
    complete = False
    while not complete:
        _, complete = downloader.next_chunk()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_bytes(buffer.getvalue())
    temporary_path.replace(output_path)
    return output_path


def drive_folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{str(folder_id).strip()}"


def drive_file_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{str(file_id).strip()}/view"
