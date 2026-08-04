"""Google Web OAuth helpers for the personal Streamlit application."""

import hmac
import json
import time
from pathlib import Path


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
OAUTH_STATE_TTL_SECONDS = 10 * 60


def _require_google_auth():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise RuntimeError(
            "Google client libraries are not installed. Use Python 3.12 and `pip install -e .`."
        ) from exc
    return Request, Credentials, Flow


def _require_credentials_file(credentials_path):
    path = Path(credentials_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError("OAuth credentials file was not found.")
    return path


def _write_private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(value, encoding="utf-8")
    temporary_path.replace(path)


def load_stored_credentials(token_path):
    """Load and refresh an existing token without starting an interactive flow."""

    token_path = Path(token_path)
    if not token_path.is_file():
        return None
    Request, Credentials, _ = _require_google_auth()

    try:
        credentials = Credentials.from_authorized_user_file(
            str(token_path), GOOGLE_SCOPES
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            _write_private_json(token_path, credentials.to_json())
    except Exception as exc:
        raise RuntimeError(
            "The saved Google connection could not be refreshed. Reconnect Google."
        ) from exc

    if not credentials.valid:
        return None
    return credentials


def create_authorization_url(credentials_path, redirect_uri):
    """Create an offline-access consent URL, state, and PKCE verifier."""

    _, _, Flow = _require_google_auth()
    credentials_path = _require_credentials_file(credentials_path)
    if not redirect_uri:
        raise ValueError("An OAuth redirect URI is required.")

    try:
        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=GOOGLE_SCOPES,
            redirect_uri=redirect_uri,
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        if not flow.code_verifier:
            raise RuntimeError("The Google OAuth client did not create a PKCE verifier.")
        return authorization_url, state, flow.code_verifier
    except Exception as exc:
        raise RuntimeError(
            "Google authorization could not be started. Check the Web OAuth client settings."
        ) from exc


def exchange_authorization_code(
    credentials_path,
    token_path,
    redirect_uri,
    code,
    state,
    code_verifier,
):
    """Exchange a verified callback code and persist the resulting user token."""

    _, _, Flow = _require_google_auth()
    credentials_path = _require_credentials_file(credentials_path)
    if not redirect_uri or not code or not state or not code_verifier:
        raise ValueError("The OAuth callback is incomplete.")

    try:
        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=GOOGLE_SCOPES,
            state=state,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        _write_private_json(token_path, credentials.to_json())
        return credentials
    except Exception as exc:
        raise RuntimeError(
            "Google authorization could not be completed. Reconnect Google and try again."
        ) from exc


def save_pending_oauth_state(state_path, state, code_verifier, now=None):
    """Persist callback state and its PKCE verifier across the browser redirect."""

    if not state or not code_verifier:
        raise ValueError("OAuth state and PKCE verifier cannot be empty.")
    payload = {
        "state": state,
        "code_verifier": code_verifier,
        "created_at": float(time.time() if now is None else now),
    }
    _write_private_json(state_path, json.dumps(payload, separators=(",", ":")))


def consume_pending_oauth_state(
    state_path,
    received_state,
    now=None,
    ttl_seconds=OAUTH_STATE_TTL_SECONDS,
):
    """Consume and validate one pending state value, rejecting replay and stale callbacks."""

    state_path = Path(state_path)
    if not received_state or not state_path.is_file():
        return None

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        expected_state = payload.get("state")
        code_verifier = payload.get("code_verifier")
        created_at = float(payload.get("created_at"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        expected_state = None
        code_verifier = None
        created_at = 0.0
    finally:
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass

    current_time = float(time.time() if now is None else now)
    age = current_time - created_at
    is_valid = (
        isinstance(expected_state, str)
        and isinstance(code_verifier, str)
        and bool(code_verifier)
        and 0 <= age <= ttl_seconds
        and hmac.compare_digest(expected_state, received_state)
    )
    return code_verifier if is_valid else None
