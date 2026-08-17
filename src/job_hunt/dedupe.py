"""Conservative URL normalization and within-run job deduplication."""

import hashlib
import re
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {
    "trk",
    "trackingid",
    "refid",
    "midtoken",
    "lipi",
    "src",
    "source",
}

DIRECT_JOB_PATHS = {
    "linkedin.com": ("/jobs/view/",),
    "naukri.com": ("/job-listings", "/job/", "/jd/"),
}


def normalize_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().casefold()


def canonicalize_url(url):
    if not url:
        return ""
    raw_url = url.strip()
    if len(raw_url) > 4096:
        return ""
    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""

    parsed_host = parsed.hostname.casefold()
    host = parsed_host
    if host.startswith("www."):
        host = host[4:]
    default_port = 80 if scheme == "http" else 443
    is_known_portal = any(
        parsed_host == suffix or parsed_host.endswith(".{0}".format(suffix))
        for suffix in DIRECT_JOB_PATHS
    )
    if port and port != default_port:
        if is_known_portal:
            return ""
        host = "{0}:{1}".format(host, port)
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    is_direct_portal_job = any(
        (
            parsed_host == suffix
            or parsed_host.endswith(".{0}".format(suffix))
        )
        and any(marker in path.casefold() for marker in markers)
        for suffix, markers in DIRECT_JOB_PATHS.items()
    )
    if is_direct_portal_job:
        for suffix in DIRECT_JOB_PATHS:
            if parsed_host == suffix or parsed_host.endswith(".{0}".format(suffix)):
                host = suffix
                break
    filtered_query = []
    if not is_direct_portal_job:
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.casefold()
            if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
                continue
            filtered_query.append((key, value))
        filtered_query.sort(key=lambda item: (item[0].casefold(), item[1]))

    return urlunsplit(("https", host, path, urlencode(filtered_query), ""))


def stable_record_id(source, url, message_id, ordinal=0):
    canonical = canonicalize_url(url)
    identity = "{0}|{1}".format(source.casefold(), canonical)
    if not canonical:
        identity = "{0}|{1}|{2}".format(source.casefold(), message_id, ordinal)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _fingerprint(record):
    values = [record.company, record.title, record.location]
    if not all(values):
        return ""
    joined = "|".join(normalize_text(value) for value in values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def dedupe_key(record):
    canonical = canonicalize_url(record.source_url)
    if canonical:
        return "url:{0}".format(canonical)
    fingerprint = _fingerprint(record)
    if fingerprint:
        return "fingerprint:{0}".format(fingerprint)
    return "record:{0}".format(record.job_record_id)


def _prefer(current, incoming):
    return current if current not in (None, "") else incoming


def _prefer_experience_source(current, incoming):
    if current in (None, "", "unknown") and incoming not in (None, ""):
        return incoming
    return current


def merge_records(current, incoming):
    evidence = list(dict.fromkeys(current.evidence_message_ids + incoming.evidence_message_ids))
    confidence_order = {"low": 0, "medium": 1, "high": 2}
    confidence = current.parse_confidence
    parse_status = current.parse_status
    if confidence_order.get(incoming.parse_confidence, 0) > confidence_order.get(confidence, 0):
        confidence = incoming.parse_confidence
        parse_status = incoming.parse_status

    return replace(
        current,
        company=_prefer(current.company, incoming.company),
        title=_prefer(current.title, incoming.title),
        location=_prefer(current.location, incoming.location),
        experience_text=_prefer(current.experience_text, incoming.experience_text),
        experience_min_years=_prefer(
            current.experience_min_years, incoming.experience_min_years
        ),
        experience_max_years=_prefer(
            current.experience_max_years, incoming.experience_max_years
        ),
        experience_fit=_prefer(current.experience_fit, incoming.experience_fit),
        experience_source=_prefer_experience_source(
            current.experience_source, incoming.experience_source
        ),
        alert_posted_at=_prefer(current.alert_posted_at, incoming.alert_posted_at),
        official_url=_prefer(current.official_url, incoming.official_url),
        last_seen_at=max(current.last_seen_at, incoming.last_seen_at),
        parse_confidence=confidence,
        parse_status=parse_status,
        evidence_message_ids=evidence,
    )


def deduplicate(records):
    merged = {}  # type: Dict[str, JobRecord]
    order = []  # type: List[str]
    for record in records:
        key = dedupe_key(record)
        if key not in merged:
            merged[key] = record
            order.append(key)
        else:
            merged[key] = merge_records(merged[key], record)
    return [merged[key] for key in order]


def company_match(company, allowlist):
    normalized_allowlist = {normalize_text(item) for item in allowlist if item}
    if not normalized_allowlist:
        return "not_configured"
    normalized_company = normalize_text(company)
    if not normalized_company:
        return "unknown"
    if normalized_company in normalized_allowlist:
        return "matched"
    return "unmatched"
