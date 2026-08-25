"""Initialize the app-owned Drive registry without overwriting an existing copy."""

from __future__ import annotations

import argparse
from pathlib import Path

from job_hunt.integrations.drive_storage import (
    EXCEL_MIME_TYPE,
    build_drive_service,
    drive_file_url,
    drive_folder_url,
    ensure_job_hunt_folders,
    find_child_file,
    upload_or_update_file,
)
from job_hunt.integrations.google_auth import load_stored_credentials
from job_hunt.runtime.state import load_local_state, save_local_state


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN = PROJECT_ROOT / ".secrets" / "google_token.json"
DEFAULT_STATE = PROJECT_ROOT / ".secrets" / "app_state.json"
DEFAULT_REGISTRY = (
    PROJECT_ROOT
    / "outputs"
    / "mnc_registry_2026-07-31"
    / "Company_Source_Registry.xlsx"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    credentials = load_stored_credentials(args.token)
    if credentials is None:
        raise RuntimeError("Google is not connected. Complete OAuth in the React application.")
    if not args.registry.is_file():
        raise FileNotFoundError("The canonical company registry was not found.")

    state = load_local_state(args.state)
    drive_service = build_drive_service(credentials)
    folders = ensure_job_hunt_folders(drive_service)
    source_ids = dict(state.get("drive_source_file_ids") or {})
    registry = find_child_file(
        drive_service,
        args.registry.name,
        parent_id=str(folders["source"]["id"]),
        mime_type=EXCEL_MIME_TYPE,
    )
    if registry is None:
        registry = upload_or_update_file(
            drive_service,
            args.registry,
            parent_id=str(folders["source"]["id"]),
        )
    source_ids[args.registry.name] = registry["id"]
    state.update(
        {
            "drive_root_folder_id": folders["root"]["id"],
            "drive_source_folder_id": folders["source"]["id"],
            "drive_source_file_ids": source_ids,
        }
    )
    save_local_state(args.state, state)

    print(f"Job Hunt: {drive_folder_url(folders['root']['id'])}")
    print(f"Source: {drive_folder_url(folders['source']['id'])}")
    print(
        "Company_Source_Registry.xlsx: "
        f"{registry.get('webViewLink') or drive_file_url(registry['id'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
