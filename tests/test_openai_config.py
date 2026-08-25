import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_hunt.intelligence.config import load_openai_settings


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

    def test_gitignored_env_file_is_supported(self):
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
            settings = load_openai_settings(root)

        self.assertEqual(settings.api_key, "private-env-secret")
        self.assertEqual(settings.model, "gpt-test")
        self.assertEqual(settings.source, "private_env_file")

    def test_retired_streamlit_file_is_not_an_active_configuration_source(self):
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

        self.assertFalse(settings.configured)
        self.assertEqual(settings.source, "not_configured")


if __name__ == "__main__":
    unittest.main()
