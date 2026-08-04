"""Export the durable Google tracker as a local Excel workbook."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


EXCEL_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _google_drive_components():
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "Google client libraries are not installed. Run `pip install -e .`."
        ) from exc
    return build, MediaIoBaseDownload


def export_google_sheet_as_xlsx(
    credentials,
    spreadsheet_id: str,
    output_path: Path,
    *,
    drive_service=None,
    downloader_factory=None,
) -> Path:
    """Download a Google Sheet as XLSX and atomically replace ``output_path``."""

    if not str(spreadsheet_id or "").strip():
        raise ValueError("A Google Sheet ID is required for the Excel export.")

    output_path = Path(output_path)
    if output_path.suffix.casefold() != ".xlsx":
        raise ValueError("The local tracker path must end in .xlsx.")

    build, default_downloader = _google_drive_components()
    if drive_service is None:
        drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    downloader_factory = downloader_factory or default_downloader

    request = drive_service.files().export_media(
        fileId=str(spreadsheet_id).strip(),
        mimeType=EXCEL_MIME_TYPE,
    )
    buffer = BytesIO()
    downloader = downloader_factory(buffer, request)
    complete = False
    while not complete:
        _, complete = downloader.next_chunk()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_bytes(buffer.getvalue())
    temporary_path.replace(output_path)
    return output_path
