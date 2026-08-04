"""Small local state file for app-owned resource identifiers only."""

import json
from pathlib import Path


def load_local_state(path):
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_local_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(path)
