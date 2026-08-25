"""Server-side Google OAuth lifecycle for the application runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from job_hunt.integrations.google_auth import (
    consume_pending_oauth_state,
    create_authorization_url,
    exchange_authorization_code,
    load_stored_credentials,
    save_pending_oauth_state,
)
from job_hunt.runtime.paths import AppPaths


class GoogleConnectionService:
    """Keep Google credentials and OAuth state behind the backend boundary."""

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
