"""Alert parser registry."""

from job_hunt.parsers.linkedin import LinkedInAlertParser
from job_hunt.parsers.naukri import NaukriAlertParser


def default_parsers():
    return [LinkedInAlertParser(), NaukriAlertParser()]


def select_parser(message, active_sources, parsers=None):
    candidates = parsers or default_parsers()
    for parser in candidates:
        if parser.source in active_sources and parser.matches(message):
            return parser
    return None
