import unittest

from job_hunt.jobs.experience import (
    classify_experience_fit,
    experience_text_from_url,
    extract_experience_range,
)


class ExperienceTests(unittest.TestCase):
    def test_extracts_range_from_descriptive_url(self):
        url = (
            "https://naukri.com/jd/job-listings-ai-engineer-example-hyderabad-"
            "2-to-6-years-123"
        )

        parsed = extract_experience_range(url)

        self.assertEqual(parsed.minimum, 2.0)
        self.assertEqual(parsed.maximum, 6.0)
        self.assertEqual(experience_text_from_url(url), "2-6 years")

    def test_classifies_preferred_overlap_outside_and_unknown(self):
        self.assertEqual(classify_experience_fit("5-10 years", 5, 8), "preferred")
        self.assertEqual(classify_experience_fit("2-6 years", 5, 8), "possible_overlap")
        self.assertEqual(classify_experience_fit("9+ years", 5, 8), "outside_target")
        self.assertEqual(classify_experience_fit(None, 5, 8), "unknown")


if __name__ == "__main__":
    unittest.main()
