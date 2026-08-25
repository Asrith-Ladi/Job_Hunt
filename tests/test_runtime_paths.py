import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.runtime.paths import AppPaths


class RuntimePathTests(unittest.TestCase):
    def test_local_defaults_remain_project_scoped(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            "os.environ",
            {
                "JOB_HUNT_OUTPUT_DIR": "",
                "JOB_HUNT_GMAIL_RUN_DIR": "",
                "JOB_HUNT_REGISTRY_PATH": "",
                "JOB_HUNT_RUNTIME_DIR": "",
            },
        ):
            root = Path(temporary).resolve()
            paths = AppPaths.from_project_root(root)

        self.assertEqual(paths.runtime_root, root / ".secrets")
        self.assertEqual(paths.run_output_root, root / "outputs" / "gmail_runs")

    def test_deployment_paths_are_environment_configurable(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            "os.environ",
            {
                "JOB_HUNT_OUTPUT_DIR": "var/output",
                "JOB_HUNT_GMAIL_RUN_DIR": "var/gmail",
                "JOB_HUNT_REGISTRY_PATH": "config/registry.xlsx",
                "JOB_HUNT_RUNTIME_DIR": "var/private",
            },
        ):
            root = Path(temporary).resolve()
            paths = AppPaths.from_project_root(root)

        self.assertEqual(paths.runtime_root, root / "var" / "private")
        self.assertEqual(paths.run_output_root, root / "var" / "gmail")
        self.assertEqual(paths.registry_path, root / "config" / "registry.xlsx")


if __name__ == "__main__":
    unittest.main()
