"""Server-only OpenAI configuration for the personal job-hunt application."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from job_hunt.integrations.openai_research import DEFAULT_OPENAI_MODEL


_LEGACY_KEYS = {"OPENAI_API_KEY", "OPENAI_MODEL"}
_ENV_LINE = re.compile(
    r"^\s*(OPENAI_API_KEY|OPENAI_MODEL)\s*=\s*(.*?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OpenAISettings:
    """Resolved settings whose secret value never crosses the API boundary."""

    api_key: str
    model: str
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def _unquote(value: str) -> str:
    value = str(value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def _read_key_values(path: Path) -> dict[str, str]:
    """Read only the two supported keys from a Git-ignored local settings file."""

    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key = match.group(1).upper()
        if key in _LEGACY_KEYS:
            values[key] = _unquote(match.group(2))
    return values


def load_openai_settings(project_root: Path) -> OpenAISettings:
    """Resolve environment first, then private local migration fallbacks.

    ``.streamlit/secrets.toml`` remains readable only so the user's existing key keeps
    working after Streamlit retirement. New local and deployed setups should use an
    environment/deployment secret or the Git-ignored ``.env`` file.
    """

    root = Path(project_root).resolve()
    environment_key = os.environ.get("OPENAI_API_KEY", "").strip()
    environment_model = os.environ.get("OPENAI_MODEL", "").strip()
    if environment_key:
        return OpenAISettings(
            api_key=environment_key,
            model=environment_model or DEFAULT_OPENAI_MODEL,
            source="environment",
        )

    for path, source in (
        (root / ".env", "private_env_file"),
        (root / ".streamlit" / "secrets.toml", "legacy_streamlit_migration"),
    ):
        values = _read_key_values(path)
        key = values.get("OPENAI_API_KEY", "").strip()
        if key:
            return OpenAISettings(
                api_key=key,
                model=(
                    environment_model
                    or values.get("OPENAI_MODEL", "").strip()
                    or DEFAULT_OPENAI_MODEL
                ),
                source=source,
            )

    return OpenAISettings(
        api_key="",
        model=environment_model or DEFAULT_OPENAI_MODEL,
        source="not_configured",
    )
