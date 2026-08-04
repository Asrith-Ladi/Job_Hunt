import tempfile
import unittest
from pathlib import Path
from unittest import mock

from job_hunt.integrations.google_auth import (
    GOOGLE_SCOPES,
    consume_pending_oauth_state,
    create_authorization_url,
    exchange_authorization_code,
    save_pending_oauth_state,
)


class GoogleScopeTests(unittest.TestCase):
    def test_personal_mvp_scopes_are_fixed_and_do_not_modify_mail(self):
        self.assertEqual(
            GOOGLE_SCOPES,
            [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/drive.file",
            ],
        )


class GoogleOAuthStateTests(unittest.TestCase):
    def test_matching_state_is_valid_once(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "oauth_state.json"
            save_pending_oauth_state(
                state_path,
                "expected-state",
                "pkce-verifier",
                now=100.0,
            )

            self.assertEqual(
                consume_pending_oauth_state(
                    state_path,
                    "expected-state",
                    now=101.0,
                ),
                "pkce-verifier",
            )
            self.assertIsNone(
                consume_pending_oauth_state(
                    state_path,
                    "expected-state",
                    now=102.0,
                )
            )

    def test_mismatched_or_expired_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "oauth_state.json"
            save_pending_oauth_state(
                state_path,
                "expected-state",
                "pkce-verifier",
                now=100.0,
            )
            self.assertIsNone(
                consume_pending_oauth_state(
                    state_path,
                    "different-state",
                    now=101.0,
                )
            )

            save_pending_oauth_state(
                state_path,
                "expected-state",
                "pkce-verifier",
                now=100.0,
            )
            self.assertIsNone(
                consume_pending_oauth_state(
                    state_path,
                    "expected-state",
                    now=701.0,
                    ttl_seconds=600,
                )
            )

    def test_pkce_verifier_is_forwarded_during_code_exchange(self):
        class FakeCredentials:
            def to_json(self):
                return "{}"

        class FakeFlow:
            last_exchange_options = None

            def __init__(self, exchange_options):
                self.exchange_options = exchange_options
                self.code_verifier = None
                self.credentials = FakeCredentials()

            @classmethod
            def from_client_secrets_file(cls, path, scopes, **options):
                instance = cls(options)
                if options.get("code_verifier"):
                    cls.last_exchange_options = options
                    instance.code_verifier = options["code_verifier"]
                return instance

            def authorization_url(self, **options):
                self.code_verifier = "generated-pkce-verifier"
                return "https://accounts.google.com/example", "generated-state"

            def fetch_token(self, code):
                self.code = code

        with tempfile.TemporaryDirectory() as directory:
            credentials_path = Path(directory) / "oauth-client.json"
            credentials_path.write_text("{}", encoding="utf-8")
            token_path = Path(directory) / "token.json"
            required = (None, None, FakeFlow)

            with mock.patch(
                "job_hunt.integrations.google_auth._require_google_auth",
                return_value=required,
            ):
                _, state, verifier = create_authorization_url(
                    credentials_path,
                    "http://localhost:8501/",
                )
                exchange_authorization_code(
                    credentials_path,
                    token_path,
                    "http://localhost:8501/",
                    "authorization-code",
                    state,
                    verifier,
                )

            self.assertEqual(verifier, "generated-pkce-verifier")
            self.assertEqual(
                FakeFlow.last_exchange_options["code_verifier"],
                verifier,
            )
            self.assertFalse(
                FakeFlow.last_exchange_options["autogenerate_code_verifier"]
            )


if __name__ == "__main__":
    unittest.main()
