"""Naukri alert recognition with conservative public-link extraction."""

from job_hunt.parsers.portal import PortalLinkParser
from job_hunt.parsers.card_extractors import extract_naukri_cards


class NaukriAlertParser(PortalLinkParser):
    source = "naukri"
    sender_markers = ("naukri",)
    subject_markers = ("naukri",)
    host_suffixes = ("naukri.com",)
    path_markers = ("/job-listings", "/job/", "/jd/")

    def card_details(self, message):
        return extract_naukri_cards(message.html_body, self._is_job_link)
