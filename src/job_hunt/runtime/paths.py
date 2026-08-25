"""Deployment-owned filesystem paths and shared time-zone policy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


TIME_ZONE = ZoneInfo("Asia/Kolkata")
GMAIL_SEEN_STATE_NAME = "gmail_seen_state.json"
GOOGLE_TOKEN_NAME = "google_token.json"
GOOGLE_OAUTH_STATE_NAME = "google_oauth_state.json"
APP_STATE_NAME = "app_state.json"
REGISTRY_FILE_NAME = "Company_Source_Registry.xlsx"
APPLICATION_QUEUE_NAME = "application_queue.json"


def _configured_path(name: str, default: Path, project_root: Path) -> Path:
    configured = os.environ.get(name, "").strip()
    candidate = Path(configured).expanduser() if configured else default
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


@dataclass(frozen=True)
class AppPaths:
    """Filesystem locations owned by one personal deployment."""

    project_root: Path
    run_output_root: Path
    registry_path: Path
    runtime_root: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "AppPaths":
        root = Path(project_root).resolve()
        output_root = _configured_path("JOB_HUNT_OUTPUT_DIR", root / "outputs", root)
        runtime_root = _configured_path(
            "JOB_HUNT_RUNTIME_DIR",
            root / ".secrets",
            root,
        )
        return cls(
            project_root=root,
            run_output_root=_configured_path(
                "JOB_HUNT_GMAIL_RUN_DIR",
                output_root / "gmail_runs",
                root,
            ),
            registry_path=_configured_path(
                "JOB_HUNT_REGISTRY_PATH",
                runtime_root / "source_cache" / REGISTRY_FILE_NAME,
                root,
            ),
            runtime_root=runtime_root,
        )

    @property
    def registry_seed_path(self) -> Path:
        """Repository seed used only when the app-owned Drive registry is absent."""

        return (
            self.project_root
            / "outputs"
            / "mnc_registry_2026-07-31"
            / REGISTRY_FILE_NAME
        )

    @property
    def token_path(self) -> Path:
        return self.runtime_root / GOOGLE_TOKEN_NAME

    @property
    def oauth_state_path(self) -> Path:
        return self.runtime_root / GOOGLE_OAUTH_STATE_NAME

    @property
    def app_state_path(self) -> Path:
        return self.runtime_root / APP_STATE_NAME

    @property
    def gmail_seen_state_path(self) -> Path:
        return self.runtime_root / GMAIL_SEEN_STATE_NAME

    @property
    def application_queue_path(self) -> Path:
        """Validated local mirror of the Drive-authoritative application queue."""

        return self.runtime_root / APPLICATION_QUEUE_NAME
