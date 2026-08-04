import unittest

from job_hunt.models import AlertMessage
from job_hunt.parsers.linkedin import LinkedInAlertParser
from job_hunt.parsers.naukri import NaukriAlertParser
from job_hunt.parsers import select_parser


NOW = "2026-07-19T00:00:00+00:00"


class ParserTests(unittest.TestCase):
    def test_linkedin_extracts_job_link_without_inventing_company(self):
        message = AlertMessage(
            message_id="m1",
            thread_id="t1",
            sender="LinkedIn Job Alerts <alerts@linkedin.com>",
            subject="Your job alert",
            received_at=NOW,
            html_body=(
                '<a href="https://www.linkedin.com/jobs/view/123?utm_source=email">'
                "Data Engineer</a>"
            ),
        )
        result = LinkedInAlertParser().parse(message, NOW)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].title, "Data Engineer")
        self.assertIsNone(result.jobs[0].company)
        self.assertEqual(result.jobs[0].parse_status, "partial_needs_fixture")

    def test_naukri_extracts_supported_job_listing_path(self):
        message = AlertMessage(
            message_id="m2",
            thread_id="t2",
            sender="Naukri <alerts@naukri.com>",
            subject="Naukri jobs",
            received_at=NOW,
            html_body=(
                '<a href="https://www.naukri.com/'
                'job-listings-python-engineer-123?utm_medium=email">'
                "Python Engineer</a>"
            ),
        )
        result = NaukriAlertParser().parse(message, NOW)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].alert_source, "naukri")

    def test_generic_view_label_is_not_treated_as_title(self):
        message = AlertMessage(
            message_id="m3",
            thread_id="t3",
            sender="alerts@linkedin.com",
            subject="alert",
            received_at=NOW,
            html_body='<a href="https://linkedin.com/jobs/view/789">View job</a>',
        )
        result = LinkedInAlertParser().parse(message, NOW)
        self.assertIsNone(result.jobs[0].title)
        self.assertEqual(result.jobs[0].parse_confidence, "low")

    def test_generic_subject_does_not_override_naukri_sender(self):
        message = AlertMessage(
            message_id="m4",
            thread_id="t4",
            sender="Naukri Alerts <alerts@naukri.com>",
            subject="Your daily job alert",
            received_at=NOW,
        )
        parser = select_parser(message, ["linkedin", "naukri"])
        self.assertIsInstance(parser, NaukriAlertParser)

    def test_linkedin_template_extracts_core_card_fields(self):
        url = "https://www.linkedin.com/comm/jobs/view/4439237316/?trackingId=private"
        message = AlertMessage(
            message_id="m5",
            thread_id="t5",
            sender="LinkedIn Job Alerts <alerts@linkedin.com>",
            subject="Your job alert",
            received_at=NOW,
            html_body=(
                '<a href="{0}"><img src="logo"></a>'
                '<a href="{0}"><a href="{0}" class="font-bold text-md">'
                "Digital - Senior</a>"
                '<p class="text-system-gray-100 text-xs">'
                "EY &middot; Hyderabad (On-site)</p></a>"
            ).format(url),
        )

        result = LinkedInAlertParser().parse(message, NOW)

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].title, "Digital - Senior")
        self.assertEqual(result.jobs[0].company, "EY")
        self.assertEqual(result.jobs[0].location, "Hyderabad (On-site)")
        self.assertEqual(result.jobs[0].parse_status, "parsed_core_fields")
        self.assertEqual(result.jobs[0].parse_confidence, "high")
        self.assertEqual(result.warnings, [])

    def test_naukri_weekly_template_extracts_core_card_fields(self):
        message = AlertMessage(
            message_id="m6",
            thread_id="t6",
            sender="Naukri <alerts@naukri.com>",
            subject="Jobs you might have missed",
            received_at=NOW,
            html_body=(
                '<a href="https://www.naukri.com/jd/example-token?uid=private">'
                "Gen AI Engineer</a>"
                "<table><tr><td></td></tr><tr><td>"
                "<table><tr><td>Covalense Global</td><td>4.0</td></tr></table>"
                "</td></tr>"
                '<tr><td class="cart_subheading">Hyderabad</td></tr></table>'
            ),
        )

        result = NaukriAlertParser().parse(message, NOW)

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].title, "Gen AI Engineer")
        self.assertEqual(result.jobs[0].company, "Covalense Global")
        self.assertEqual(result.jobs[0].location, "Hyderabad")
        self.assertEqual(result.jobs[0].parse_status, "parsed_core_fields")
        self.assertEqual(result.jobs[0].parse_confidence, "high")
        self.assertEqual(result.warnings, [])

    def test_naukri_extracts_experience_range_encoded_in_job_url(self):
        message = AlertMessage(
            message_id="m7",
            thread_id="t7",
            sender="Naukri <alerts@naukri.com>",
            subject="Jobs you might have missed",
            received_at=NOW,
            html_body=(
                '<a href="https://www.naukri.com/jd/job-listings-ai-ml-engineer-'
                'example-hyderabad-3-to-8-years-123">AI / ML Engineer</a>'
                "<table><tr><td></td></tr><tr><td>"
                "<table><tr><td>Example</td><td>4.0</td></tr></table>"
                "</td></tr>"
                '<tr><td class="cart_subheading">Hyderabad</td></tr></table>'
            ),
        )

        job = NaukriAlertParser().parse(message, NOW).jobs[0]

        self.assertEqual(job.experience_text, "3-8 years")
        self.assertEqual(job.experience_min_years, 3.0)
        self.assertEqual(job.experience_max_years, 8.0)
        self.assertEqual(job.experience_source, "alert_url")


if __name__ == "__main__":
    unittest.main()
