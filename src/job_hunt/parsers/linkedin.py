"""LinkedIn alert recognition with conservative public-link extraction."""

from job_hunt.parsers.portal import PortalLinkParser
from job_hunt.parsers.card_extractors import extract_linkedin_cards


class LinkedInAlertParser(PortalLinkParser):
    source = "linkedin"
    sender_markers = ("linkedin",)
    subject_markers = ("linkedin",)
    host_suffixes = ("linkedin.com",)
    path_markers = ("/jobs/view/",)

    def card_details(self, message):
        return extract_linkedin_cards(message.html_body, self._is_job_link)
