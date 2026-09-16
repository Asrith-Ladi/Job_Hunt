"""Replace the app-owned Drive registry and verify the uploaded bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from job_hunt.integrations.drive_storage import (
    EXCEL_MIME_TYPE,
    build_drive_service,
    download_drive_file,
    drive_file_url,
    drive_folder_url,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.integrations.google_auth import load_stored_credentials
from job_hunt.runtime.state import load_local_state, save_local_state


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = (
    PROJECT_ROOT
    / "outputs"
    / "linkedin_registry_20260915"
    / "Company_Source_Registry.xlsx"
)
DEFAULT_TOKEN = PROJECT_ROOT / ".secrets" / "google_token.json"
DEFAULT_STATE = PROJECT_ROOT / ".secrets" / "app_state.json"
DEFAULT_VERIFICATION_OUTPUT = (
    PROJECT_ROOT
    / "outputs"
    / "linkedin_registry_20260915"
    / "drive_verification"
    / "Company_Source_Registry.xlsx"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--verification-output",
        type=Path,
        default=DEFAULT_VERIFICATION_OUTPUT,
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    registry = args.registry.resolve()
    if not registry.is_file():
        raise FileNotFoundError(f"Registry workbook was not found: {registry}")

    credentials = load_stored_credentials(args.token)
    if credentials is None:
        raise RuntimeError(
            "Google is not connected. Complete OAuth in the application."
        )

    state = load_local_state(args.state)
    drive_service = build_drive_service(credentials)
    folders = ensure_job_hunt_folders(drive_service)
    source_folder_id = str(folders["source"]["id"])
    source_ids = dict(state.get("drive_source_file_ids") or {})
    file_id = str(source_ids.get(registry.name) or "").strip()

    if not file_id:
        existing = find_child_file(
            drive_service,
            registry.name,
            parent_id=source_folder_id,
            mime_type=EXCEL_MIME_TYPE,
        )
        file_id = str((existing or {}).get("id") or "").strip()

    uploaded = upload_or_update_file(
        drive_service,
        registry,
        parent_id=source_folder_id,
        existing_file_id=file_id or None,
    )
    file_id = str(uploaded["id"])
    source_ids[registry.name] = file_id
    state.update(
        {
            "drive_root_folder_id": folders["root"]["id"],
            "drive_source_folder_id": source_folder_id,
            "drive_source_file_ids": source_ids,
        }
    )
    save_local_state(args.state, state)

    metadata = (
        drive_service.files()
        .get(
            fileId=file_id,
            fields=(
                "id,name,mimeType,parents,webViewLink,modifiedTime,"
                "md5Checksum,size"
            ),
        )
        .execute()
    )
    verification_output = args.verification_output.resolve()
    download_drive_file(drive_service, file_id, verification_output)
    local_sha256 = _sha256(registry)
    downloaded_sha256 = _sha256(verification_output)
    verified = local_sha256 == downloaded_sha256
    if not verified:
        raise RuntimeError("Drive verification failed: uploaded bytes do not match.")

    print(
        json.dumps(
            {
                "name": metadata.get("name"),
                "size": metadata.get("size"),
                "modifiedTime": metadata.get("modifiedTime"),
                "md5Checksum": metadata.get("md5Checksum"),
                "webViewLink": metadata.get("webViewLink")
                or drive_file_url(file_id),
                "sourceFolderUrl": drive_folder_url(source_folder_id),
                "localSha256": local_sha256,
                "downloadedSha256": downloaded_sha256,
                "verified": verified,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
