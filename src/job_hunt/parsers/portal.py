"""Conservative parser that extracts job links without inventing missing fields."""

from urllib.parse import urlsplit

from job_hunt.jobs.dedupe import canonicalize_url, stable_record_id
from job_hunt.jobs.experience import extract_experience_range
from job_hunt.jobs.models import JobRecord, ParseResult
from job_hunt.parsers.base import AlertParser
from job_hunt.parsers.html_links import extract_links


GENERIC_LINK_LABELS = {
    "apply",
    "apply now",
    "view",
    "view job",
    "view jobs",
    "see job",
    "learn more",
}


class PortalLinkParser(AlertParser):
    sender_markers = ()
    subject_markers = ()
    host_suffixes = ()
    path_markers = ()

    def card_details(self, message):
        return {}

    def matches(self, message):
        sender = message.sender.casefold()
        subject = message.subject.casefold()
        return any(marker in sender for marker in self.sender_markers) or any(
            marker in subject for marker in self.subject_markers
        )

    def _is_job_link(self, url):
        canonical = canonicalize_url(url)
        if not canonical:
            return False
        parsed = urlsplit(canonical)
        host_match = any(
            parsed.hostname == suffix or parsed.hostname.endswith(".{0}".format(suffix))
            for suffix in self.host_suffixes
        )
        path = parsed.path.casefold()
        return host_match and any(marker in path for marker in self.path_markers)

    def parse(self, message, observed_at):
        result = ParseResult(source=self.source)
        details_by_url = self.card_details(message)
        seen_urls = set()
        ordinal = 0
        partial_count = 0
        for url, label in extract_links(message.html_body, message.text_body):
            if not self._is_job_link(url):
                continue
            canonical = canonicalize_url(url)
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            ordinal += 1

            cleaned_label = " ".join(label.split()).strip()[:500]
            details = details_by_url.get(canonical, {})
            title = details.get("title") or cleaned_label or None
            if title and title.casefold() in GENERIC_LINK_LABELS:
                title = None
            company = details.get("company")
            location = details.get("location")
            experience_text = details.get("experience_text")
            experience_range = extract_experience_range(experience_text)
            has_core_fields = bool(title and company and location)
            if not has_core_fields:
                partial_count += 1

            result.jobs.append(
                JobRecord(
                    job_record_id=stable_record_id(
                        self.source, canonical, message.message_id, ordinal
                    ),
                    alert_source=self.source,
                    gmail_message_id=message.message_id,
                    email_subject=message.subject[:500],
                    email_received_at=message.received_at,
                    company=company,
                    title=title,
                    location=location,
                    experience_text=experience_text,
                    alert_posted_at=None,
                    source_url=canonical,
                    official_url=None,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    parse_confidence=(
                        "high" if has_core_fields else "medium" if title else "low"
                    ),
                    parse_status=(
                        "parsed_core_fields" if has_core_fields else "partial_needs_fixture"
                    ),
                    evidence_message_ids=[message.message_id],
                    experience_min_years=(
                        experience_range.minimum if experience_range else None
                    ),
                    experience_max_years=(
                        experience_range.maximum if experience_range else None
                    ),
                    experience_source=details.get("experience_source") or "unknown",
                )
            )

        if not result.jobs:
            result.warnings.append(
                "No supported {0} job links found in message {1}.".format(
                    self.source, message.message_id
                )
            )
        elif partial_count:
            result.warnings.append(
                "{0}: {1} of {2} jobs are missing one or more core fields.".format(
                    self.source.title(),
                    partial_count,
                    len(result.jobs),
                )
            )
        return result
