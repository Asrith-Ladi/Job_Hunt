import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.openai_config import load_openai_settings


class OpenAIConfigTests(unittest.TestCase):
    def test_environment_has_priority_without_exposing_the_key(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "environment-secret", "OPENAI_MODEL": "test-model"},
            clear=False,
        ):
            settings = load_openai_settings(Path(temporary))

        self.assertTrue(settings.configured)
        self.assertEqual(settings.api_key, "environment-secret")
        self.assertEqual(settings.model, "test-model")
        self.assertEqual(settings.source, "environment")

    def test_gitignored_env_precedes_legacy_streamlit_migration(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""},
            clear=False,
        ):
            root = Path(temporary)
            (root / ".env").write_text(
                'OPENAI_API_KEY="private-env-secret"\nOPENAI_MODEL=gpt-test\n',
                encoding="utf-8",
            )
            legacy = root / ".streamlit" / "secrets.toml"
            legacy.parent.mkdir()
            legacy.write_text('OPENAI_API_KEY = "legacy-secret"\n', encoding="utf-8")

            settings = load_openai_settings(root)

        self.assertEqual(settings.api_key, "private-env-secret")
        self.assertEqual(settings.model, "gpt-test")
        self.assertEqual(settings.source, "private_env_file")

    def test_legacy_streamlit_file_keeps_existing_setup_working(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""},
            clear=False,
        ):
            root = Path(temporary)
            legacy = root / ".streamlit" / "secrets.toml"
            legacy.parent.mkdir()
            legacy.write_text(
                'OPENAI_API_KEY = "legacy-secret"\nOPENAI_MODEL = "gpt-5.6-luna"\n',
                encoding="utf-8",
            )
            settings = load_openai_settings(root)

        self.assertEqual(settings.api_key, "legacy-secret")
        self.assertEqual(settings.source, "legacy_streamlit_migration")


if __name__ == "__main__":
    unittest.main()
