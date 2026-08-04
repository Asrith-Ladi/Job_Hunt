import tempfile
import unittest
from pathlib import Path

from job_hunt.local_state import load_local_state, save_local_state


class LocalStateTests(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "state.json"
            self.assertEqual(load_local_state(path), {})
            save_local_state(path, {"spreadsheet_id": "sheet-123"})
            self.assertEqual(load_local_state(path), {"spreadsheet_id": "sheet-123"})

    def test_invalid_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "state.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(load_local_state(path), {})


if __name__ == "__main__":
    unittest.main()
