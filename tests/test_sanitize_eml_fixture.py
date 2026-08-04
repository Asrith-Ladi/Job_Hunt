import unittest

from scripts.sanitize_eml_fixture import redact_text, sanitize_html, sanitize_url


class FixtureSanitizerTests(unittest.TestCase):
    def test_url_keeps_job_path_and_parameter_names_but_not_values(self):
        value = sanitize_url(
            "https://jobs.example.com/job/123?tracking=private&source=email",
            [],
        )
        self.assertEqual(
            value,
            "https://jobs.example.com/job/123?tracking=REDACTED&source=REDACTED",
        )

    def test_personal_values_and_addresses_are_removed(self):
        value = redact_text(
            "Hello Sample Person at person@example.com",
            ["Sample Person", "Sample"],
        )
        self.assertNotIn("Sample", value)
        self.assertNotIn("person@example.com", value)
        self.assertIn("REDACTED_NAME", value)
        self.assertIn("REDACTED_EMAIL", value)

    def test_html_drops_scripts_and_unsafe_attributes(self):
        value = sanitize_html(
            '<div data-user="secret"><script>private()</script>'
            '<a href="https://example.com/job/1?token=secret">Role</a></div>',
            [],
        )
        self.assertNotIn("data-user", value)
        self.assertNotIn("private()", value)
        self.assertIn("token=REDACTED", value)

    def test_linkedin_profile_footer_is_removed(self):
        value = redact_text(
            "This email was intended for Person (private profile headline)",
            ["Person"],
        )
        self.assertEqual(value, "REDACTED_PROFILE_CONTEXT")


if __name__ == "__main__":
    unittest.main()
