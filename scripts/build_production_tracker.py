"""Build the real, multi-tab personal job tracker in the existing Google Sheet."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from job_hunt.jobs.enrichment import (
    ResumeProfile,
    canonical_company,
    cold_referral_message,
    company_connections,
    connection_relevance,
    load_connections,
    score_alert_only,
    score_official_posting,
)
from job_hunt.integrations.google_auth import load_stored_credentials
from job_hunt.integrations.sheets import hyperlink_formula, rich_text_link_runs


TIME_ZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_SPREADSHEET_ID = "1oMtbn0y1Er4paiWgcQ1lpx_Cr08f2aEntR-wC4_iBKc"
DEFAULT_TOKEN = Path(".secrets/google_token.json")
DEFAULT_ALERTS = Path("local_samples/private/gmail_alert_jobs_2026-07-20.json")
DEFAULT_RESEARCH = Path("local_samples/private/official_research_2026-07-20.json")
DEFAULT_CONNECTIONS = Path("local_samples/private/Connections_2026-07-19.csv")


MAIN_HEADERS = [
    "priority",
    "application_status",
    "alert_source",
    "company",
    "alert_title",
    "alert_location",
    "alert_experience",
    "gmail_received_at",
    "alert_url",
    "official_match_status",
    "official_match_score",
    "match_reason",
    "official_title",
    "official_location",
    "official_experience",
    "official_requisition",
    "published_at",
    "active_status",
    "official_url",
    "job_description_summary",
    "eligibility_score",
    "eligibility_band",
    "eligibility_summary",
    "evidence_confidence",
    "score_components",
    "matched_resume_skills",
    "gaps_or_risks",
    "resume_evidence",
    "referral_count",
    "top_referral_candidates",
    "cold_message",
    "notes",
    "alert_record_id",
    "official_job_id",
]

GMAIL_HEADERS = [
    "job_record_id",
    "alert_source",
    "company",
    "title",
    "location",
    "years_of_experience",
    "email_received_at",
    "source_url",
    "parse_status",
    "official_candidate_count",
    "best_match_status",
    "best_match_score",
    "best_official_url",
    "best_eligibility_score",
    "best_eligibility_band",
    "application_status",
    "notes",
]

OFFICIAL_HEADERS = [
    "official_job_id",
    "company",
    "title",
    "location",
    "experience",
    "workplace_type",
    "employment_type",
    "active_status",
    "requisition_id",
    "published_at",
    "official_url",
    "description_summary",
    "required_skills",
    "preferred_skills",
    "eligibility_score",
    "eligibility_band",
    "evidence_confidence",
    "source_notes",
    "verified_at",
]

MATCH_HEADERS = [
    "alert_record_id",
    "alert_source",
    "alert_company",
    "alert_title",
    "official_job_id",
    "official_title",
    "official_url",
    "match_status",
    "official_match_score",
    "match_reason",
    "eligibility_score",
    "eligibility_band",
    "evidence_confidence",
    "verified_at",
]

CONNECTION_HEADERS = [
    "alert_record_id",
    "official_job_id",
    "company",
    "job_title",
    "referral_rank",
    "total_company_connections",
    "connection_name",
    "connection_position",
    "connection_company_as_exported",
    "connection_linkedin_url",
    "relevance_score",
    "match_basis",
    "cold_message",
]

RUN_HEADERS = [
    "run_id",
    "started_at",
    "finished_at",
    "status",
    "gmail_messages",
    "unique_alerts",
    "official_postings",
    "match_rows",
    "alerts_without_official_result",
    "main_rows",
    "connection_rows",
    "spreadsheet_id",
    "notes",
]

CONTACT_TOOL_HEADERS = ["tool_link", "available_data", "lookup_order", "usage_note"]
CONTACT_TOOL_START_COLUMN = 14  # O, leaving N as visual spacing after the audit table.
CONTACT_TOOL_SOURCES = (
    (
        "Hunter",
        "https://hunter.io/email-finder",
        "Professional work email",
        1,
        "First choice when the full name and company domain are known.",
    ),
    (
        "Apollo",
        "https://www.apollo.io/email-finder",
        "Work email; business phone when available",
        2,
        "Second choice; verify the returned company and confidence before contact.",
    ),
    (
        "RocketReach",
        "https://rocketreach.co/",
        "Email and phone when available",
        3,
        "Existing manual fallback; treat every result as potentially stale.",
    ),
    (
        "Lusha",
        "https://www.lusha.com/",
        "Work email; mobile or direct phone when available",
        4,
        "Credit-based fallback; prefer professional contact details.",
    ),
    (
        "ContactOut",
        "https://contactout.com/",
        "Work/personal email and direct dial when available",
        5,
        "Recruiter-oriented fallback; personal contact data is more sensitive.",
    ),
    (
        "SignalHire",
        "https://www.signalhire.com/",
        "Business/personal email and phone when available",
        6,
        "Last-resort manual lookup; do not use for bulk unsolicited outreach.",
    ),
)

RESUME_HEADERS = ["section", "item", "value", "max_points", "method_or_guardrail"]


def _profile() -> ResumeProfile:
    return ResumeProfile(
        years_experience=5.8,
        skills=frozenset(
            {
                "Python",
                "SQL",
                "Pandas",
                "NumPy",
                "scikit-learn",
                "TensorFlow",
                "Machine Learning",
                "Generative AI",
                "LLMs",
                "AI Agents",
                "LangGraph",
                "LangChain",
                "RAG",
                "MCP",
                "REST APIs",
                "System Design",
                "Distributed Systems",
                "Event-Driven Architecture",
                "AWS",
                "Cloud",
                "Docker",
                "Kubernetes",
                "CI/CD",
                "PostgreSQL",
                "Vector Databases",
                "Time Series",
                "Statistics",
                "NLP",
                "Deep Learning",
                "Data Engineering",
            }
        ),
        evidence=(
            "5+ years: ML Engineer since Mar 2023 and Python Developer since Sep 2020.",
            "Production GenAI and agentic systems using LangGraph/LangChain, RAG and MCP/FastMCP.",
            "Python/SQL ML stack with TensorFlow, scikit-learn, pandas, NumPy and PostgreSQL/pgvector.",
            "AWS, Docker, Kubernetes, CI/CD, distributed/event-driven APIs and production monitoring.",
            "M.Tech Software Systems (2024) and AWS Cloud Practitioner.",
        ),
    )


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _url_cell(value: object) -> str:
    return hyperlink_formula(value) or str(value or "")


def _named_url_cell(value: object, label: object) -> str:
    return hyperlink_formula(value, label) or str(label or "")


def _linked_referral_summary(connections) -> tuple[str, list[tuple[int, int, str]]]:
    """Return display text plus link spans for each referral name."""

    text = ""
    links = []
    for connection in connections:
        if text:
            text += "\n"
        start = len(text)
        text += connection.full_name
        end = len(text)
        text += f" — {connection.position or 'position not provided'}"
        if connection.linkedin_url.startswith(("https://", "http://")):
            links.append((start, end, connection.linkedin_url))
    return text, links


def _url_link_span(text: str, url: str) -> list[tuple[int, int, str]]:
    target = str(url or "").strip()
    start = text.find(target) if target.startswith(("https://", "http://")) else -1
    return [(start, start + len(target), target)] if start >= 0 else []


def _join(values: list[str] | tuple[str, ...], limit: int | None = None) -> str:
    items = [str(item).strip() for item in values if str(item).strip()]
    if limit is not None:
        items = items[:limit]
    return "\n".join(items)


def _eligibility_summary(result: dict) -> str:
    matched = ", ".join(result["matched_skills"][:5]) or "requirements unavailable"
    gaps = "; ".join(result["gaps"][:3]) or "No material gap found in documented evidence."
    return (
        f"{result['band']} ({result['score']}/100). {result['experience_reason']} "
        f"Matched: {matched}. Gaps/risk: {gaps}"
    )


def _priority(posting: dict | None, eligibility: dict) -> str:
    if posting and posting.get("active_status") in {"closed", "filled", "inactive"}:
        return "Skip"
    if posting is None:
        return "Review"
    if eligibility["score"] >= 85:
        return "High"
    if eligibility["score"] >= 70:
        return "Medium"
    return "Low"


def _main_key(alert_id: str, official_job_id: str) -> tuple[str, str]:
    return str(alert_id or ""), str(official_job_id or "")


def _build_tracker_data(alert_payload: dict, research: dict, connection_path: Path) -> dict:
    profile = _profile()
    alerts = list(alert_payload.get("jobs") or [])
    postings = list(research.get("postings") or [])
    postings_by_id = {item["official_job_id"]: item for item in postings}
    matches_by_alert = research.get("matches") or {}
    connections = load_connections(connection_path)
    resume_evidence = _join(profile.evidence)
    verified_at = research.get("verified_at") or ""
    checked_alert_ids = {
        str(item) for item in research.get("checked_alert_ids") or []
    }
    checked_alert_ids.update(matches_by_alert)

    main_records = []
    match_records = []
    connection_records = []
    gmail_records = []
    matched_official_ids = set()
    alerts_without_official = 0
    alerts_pending_research = 0

    for alert in alerts:
        alert_id = alert["job_record_id"]
        mapping_rows = list(matches_by_alert.get(alert_id) or [])
        candidates_for_gmail = []
        if not mapping_rows:
            was_checked = alert_id in checked_alert_ids
            if was_checked:
                alerts_without_official += 1
            else:
                alerts_pending_research += 1
            mapping_rows = [
                {
                    "official_job_id": "",
                    "match_status": (
                        "no_official_result" if was_checked else "research_pending"
                    ),
                    "match_score": "",
                    "match_reason": (
                        (
                            "No current public official posting was located for this alert on "
                            f"{verified_at}; re-check the employer site or add a manual official link."
                        )
                        if was_checked
                        else (
                            "Official-site research has not run for this alert yet; run again "
                            "or increase the per-run uncached-alert limit."
                        )
                    ),
                }
            ]

        for mapping in mapping_rows:
            official_id = mapping.get("official_job_id") or ""
            posting = postings_by_id.get(official_id)
            if posting:
                matched_official_ids.add(official_id)
                eligibility = score_official_posting(posting, profile)
                company = canonical_company(posting.get("company"))
                job_title = posting.get("title") or alert.get("title") or ""
                job_url = posting.get("official_url") or alert.get("source_url") or ""
                description = posting.get("description_summary") or ""
                official_location = posting.get("location") or ""
                official_experience = posting.get("experience_text") or ""
                requisition = posting.get("requisition_id") or ""
                published = posting.get("published_at") or ""
                active_status = posting.get("active_status") or "unknown"
                official_url = posting.get("official_url") or ""
            else:
                eligibility = score_alert_only(alert, profile)
                company = canonical_company(alert.get("company"))
                job_title = alert.get("title") or ""
                job_url = alert.get("source_url") or ""
                description = (
                    "Gmail alert card only; no full public official description was located.\n"
                    "Eligibility is preliminary and required-skill coverage is intentionally unscored.\n"
                    "Re-check the employer careers page or supply a manual official job link."
                )
                official_location = ""
                official_experience = ""
                requisition = ""
                published = ""
                active_status = "not_verified"
                official_url = ""

            company_matches = company_connections(connections, company)
            top_connections = company_matches[:3]
            top_referrals, top_referral_links = _linked_referral_summary(top_connections)
            cold_message = (
                cold_referral_message(
                    top_connections[0],
                    company,
                    job_title,
                    job_url,
                    eligibility["matched_skills"],
                )
                if top_connections
                else "No same-company connection found in the supplied LinkedIn export."
            )
            main_record = {
                "priority": _priority(posting, eligibility),
                "application_status": "not_started",
                "alert_source": alert.get("alert_source") or "",
                "company": company,
                "alert_title": alert.get("title") or "",
                "alert_location": alert.get("location") or "",
                "alert_experience": alert.get("experience_text") or "Not stated in alert",
                "gmail_received_at": alert.get("email_received_at") or "",
                "alert_url": _url_cell(alert.get("source_url")),
                "official_match_status": mapping.get("match_status") or "",
                "official_match_score": mapping.get("match_score", ""),
                "match_reason": mapping.get("match_reason") or "",
                "official_title": posting.get("title") if posting else "",
                "official_location": official_location,
                "official_experience": official_experience,
                "official_requisition": requisition,
                "published_at": published,
                "active_status": active_status,
                "official_url": _url_cell(official_url),
                "job_description_summary": description,
                "eligibility_score": eligibility["score"],
                "eligibility_band": eligibility["band"],
                "eligibility_summary": _eligibility_summary(eligibility),
                "evidence_confidence": eligibility["confidence"],
                "score_components": eligibility["components"],
                "matched_resume_skills": _join(eligibility["matched_skills"]),
                "gaps_or_risks": _join(eligibility["gaps"]),
                "resume_evidence": resume_evidence,
                "referral_count": len(company_matches),
                "top_referral_candidates": top_referrals,
                "_top_referral_links": top_referral_links,
                "cold_message": cold_message,
                "_cold_message_links": _url_link_span(cold_message, job_url),
                "notes": "",
                "alert_record_id": alert_id,
                "official_job_id": official_id,
            }
            main_records.append(main_record)
            candidates_for_gmail.append((mapping, posting, eligibility))

            match_records.append(
                {
                    "alert_record_id": alert_id,
                    "alert_source": alert.get("alert_source") or "",
                    "alert_company": alert.get("company") or "",
                    "alert_title": alert.get("title") or "",
                    "official_job_id": official_id,
                    "official_title": posting.get("title") if posting else "",
                    "official_url": _url_cell(official_url),
                    "match_status": mapping.get("match_status") or "",
                    "official_match_score": mapping.get("match_score", ""),
                    "match_reason": mapping.get("match_reason") or "",
                    "eligibility_score": eligibility["score"],
                    "eligibility_band": eligibility["band"],
                    "evidence_confidence": eligibility["confidence"],
                    "verified_at": verified_at,
                }
            )

            for rank, connection in enumerate(top_connections, start=1):
                connection_message = cold_referral_message(
                    connection,
                    company,
                    job_title,
                    job_url,
                    eligibility["matched_skills"],
                )
                connection_records.append(
                    {
                        "alert_record_id": alert_id,
                        "official_job_id": official_id,
                        "company": company,
                        "job_title": job_title,
                        "referral_rank": rank,
                        "total_company_connections": len(company_matches),
                        "connection_name": _named_url_cell(
                            connection.linkedin_url, connection.full_name
                        ),
                        "connection_position": connection.position,
                        "connection_company_as_exported": connection.company,
                        "connection_linkedin_url": _url_cell(connection.linkedin_url),
                        "relevance_score": connection_relevance(connection),
                        "match_basis": (
                            "Same canonical employer in the supplied LinkedIn export; "
                            "rank reflects role relevance, not relationship strength."
                        ),
                        "cold_message": connection_message,
                        "_cold_message_links": _url_link_span(
                            connection_message, job_url
                        ),
                    }
                )

        best_mapping, best_posting, best_eligibility = max(
            candidates_for_gmail,
            key=lambda item: (
                int(item[0].get("match_score") or 0),
                int(item[2].get("score") or 0),
            ),
        )
        gmail_records.append(
            {
                "job_record_id": alert_id,
                "alert_source": alert.get("alert_source") or "",
                "company": alert.get("company") or "",
                "title": alert.get("title") or "",
                "location": alert.get("location") or "",
                "years_of_experience": alert.get("experience_text") or "",
                "email_received_at": alert.get("email_received_at") or "",
                "source_url": _url_cell(alert.get("source_url")),
                "parse_status": alert.get("parse_status") or "",
                "official_candidate_count": sum(1 for item in candidates_for_gmail if item[1]),
                "best_match_status": best_mapping.get("match_status") or "",
                "best_match_score": best_mapping.get("match_score", ""),
                "best_official_url": _url_cell(
                    best_posting.get("official_url") if best_posting else ""
                ),
                "best_eligibility_score": best_eligibility["score"],
                "best_eligibility_band": best_eligibility["band"],
                "application_status": "not_started",
                "notes": "",
            }
        )

    official_records = []
    for posting in postings:
        if posting["official_job_id"] not in matched_official_ids:
            continue
        eligibility = score_official_posting(posting, profile)
        official_records.append(
            {
                "official_job_id": posting["official_job_id"],
                "company": posting.get("company") or "",
                "title": posting.get("title") or "",
                "location": posting.get("location") or "",
                "experience": posting.get("experience_text") or "",
                "workplace_type": posting.get("workplace_type") or "",
                "employment_type": posting.get("employment_type") or "",
                "active_status": posting.get("active_status") or "",
                "requisition_id": posting.get("requisition_id") or "",
                "published_at": posting.get("published_at") or "",
                "official_url": _url_cell(posting.get("official_url")),
                "description_summary": posting.get("description_summary") or "",
                "required_skills": _join(posting.get("required_skills") or []),
                "preferred_skills": _join(posting.get("preferred_skills") or []),
                "eligibility_score": eligibility["score"],
                "eligibility_band": eligibility["band"],
                "evidence_confidence": posting.get("evidence_confidence") or "",
                "source_notes": posting.get("source_notes") or "",
                "verified_at": verified_at,
            }
        )

    priority_order = {"High": 0, "Medium": 1, "Review": 2, "Low": 3, "Skip": 4}
    main_records.sort(
        key=lambda item: (
            priority_order[item["priority"]],
            -int(item["eligibility_score"]),
            item["company"].lower(),
            item["official_title"].lower(),
        )
    )
    gmail_records.sort(key=lambda item: (item["alert_source"], item["company"].lower(), item["title"].lower()))
    official_records.sort(key=lambda item: (item["active_status"] != "active", -int(item["eligibility_score"]), item["company"].lower()))
    match_records.sort(key=lambda item: (item["alert_company"].lower(), -int(item["official_match_score"] or 0)))
    connection_records.sort(key=lambda item: (item["company"].lower(), item["job_title"].lower(), int(item["referral_rank"])))

    resume_records = [
        {"section": "Profile", "item": "Experience", "value": "5+ years (calculated as 5.8 for range scoring)", "max_points": "", "method_or_guardrail": "Derived from dated resume roles; not inferred from job alerts."},
        {"section": "Profile", "item": "Core skills", "value": ", ".join(sorted(profile.skills)), "max_points": "", "method_or_guardrail": "Only documented resume evidence is counted."},
        {"section": "Profile", "item": "Evidence summary", "value": resume_evidence, "max_points": "", "method_or_guardrail": "Contact details and direct identifiers are excluded."},
        {"section": "Eligibility rule", "item": "Experience fit", "value": "Within/near/outside stated range", "max_points": 30, "method_or_guardrail": "Official range first; Gmail-alert range only for preliminary rows."},
        {"section": "Eligibility rule", "item": "Required-skill coverage", "value": "Documented resume skills / stated official required skills", "max_points": 40, "method_or_guardrail": "Missing official requirements are not invented."},
        {"section": "Eligibility rule", "item": "Role/title alignment", "value": "ML/AI/data-science role alignment and seniority risk", "max_points": 15, "method_or_guardrail": "Manager/architect/principal titles are penalized without matching leadership evidence."},
        {"section": "Eligibility rule", "item": "Production/cloud alignment", "value": "Production, cloud and deployment evidence", "max_points": 10, "method_or_guardrail": "Uses documented AWS/Docker/Kubernetes/CI/CD evidence."},
        {"section": "Eligibility rule", "item": "Education/certification", "value": "Relevant M.Tech and AWS certification", "max_points": 5, "method_or_guardrail": "No equivalency claims beyond the resume."},
        {"section": "Guardrail", "item": "Official match score", "value": "Company/title/location/requisition evidence", "max_points": 100, "method_or_guardrail": "Kept separate from eligibility; a matching job can still be a poor resume fit."},
        {"section": "Guardrail", "item": "Alert-only score", "value": "Preliminary and capped", "max_points": 60, "method_or_guardrail": "Required skills and full description remain unscored until an official posting is found."},
        {"section": "Guardrail", "item": "Referral ranking", "value": "Recruiting/technical-role relevance", "max_points": "", "method_or_guardrail": "Same-company match is not a claim of relationship strength or willingness to refer."},
    ]

    return {
        "main": main_records,
        "gmail": gmail_records,
        "official": official_records,
        "matches": match_records,
        "connections": connection_records,
        "resume": resume_records,
        "stats": {
            "gmail_messages": int(alert_payload.get("summary", {}).get("messages_read") or 0),
            "unique_alerts": len(alerts),
            "official_postings": len(official_records),
            "match_rows": len(match_records),
            "alerts_without_official_result": alerts_without_official,
            "alerts_pending_research": alerts_pending_research,
            "main_rows": len(main_records),
            "connection_rows": len(connection_records),
            "verified_at": verified_at,
            "raw_connections": len(connections),
        },
    }


def _records_to_rows(records: list[dict], headers: list[str]) -> list[list[object]]:
    return [[record.get(header, "") for header in headers] for record in records]


def _column_letter(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _rgb(value: str) -> dict:
    value = value.lstrip("#")
    return {
        "red": int(value[0:2], 16) / 255,
        "green": int(value[2:4], 16) / 255,
        "blue": int(value[4:6], 16) / 255,
    }


def _grid(sheet_id, start_row, end_row, start_col, end_col):
    return {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row,
        "startColumnIndex": start_col,
        "endColumnIndex": end_col,
    }


def _read_existing_user_fields(sheets, spreadsheet_id: str, sheet_title: str) -> dict:
    try:
        response = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_title}'!A:AZ",
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
    except Exception:
        return {}
    values = response.get("values") or []
    if len(values) < 3:
        return {}
    headers = values[2]
    index = {name: position for position, name in enumerate(headers)}
    required = {"alert_record_id", "official_job_id"}
    if not required.issubset(index):
        return {}
    preserved = {}
    for row in values[3:]:
        def cell(name):
            position = index.get(name)
            return row[position] if position is not None and position < len(row) else ""

        key = _main_key(cell("alert_record_id"), cell("official_job_id"))
        preserved[key] = {
            "priority": cell("priority"),
            "application_status": cell("application_status"),
            "notes": cell("notes"),
        }
    return preserved


def _apply_preserved_fields(records: list[dict], preserved: dict) -> None:
    for record in records:
        old = preserved.get(_main_key(record["alert_record_id"], record["official_job_id"]))
        if not old:
            continue
        for field in ("priority", "application_status", "notes"):
            if old.get(field):
                record[field] = old[field]


def _sheet_payload(title: str, summary: str, headers: list[str], records: list[dict]):
    # Keep the frozen first column narrow and place the banner in the unfrozen area.
    return [["", title], ["", summary], headers] + _records_to_rows(records, headers)


def _contact_tool_payload() -> list[list[object]]:
    records = [
        {
            "tool_link": _named_url_cell(url, name),
            "available_data": available_data,
            "lookup_order": lookup_order,
            "usage_note": usage_note,
        }
        for name, url, available_data, lookup_order, usage_note in CONTACT_TOOL_SOURCES
    ]
    return _sheet_payload(
        "Contact Lookup Tools — manual use only",
        (
            "Use one-person lookups only; do not upload the complete Connections export. "
            "Verify each result and respect the person's preferred contact channel."
        ),
        CONTACT_TOOL_HEADERS,
        records,
    )


def _replace_production_sheets(sheets, spreadsheet_id: str, date_title: str, payloads: dict):
    contact_tool_payload = _contact_tool_payload()
    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="spreadsheetId,properties.title,sheets.properties(sheetId,title,index)",
    ).execute()
    properties = {item["properties"]["title"]: item["properties"] for item in metadata.get("sheets") or []}

    requests = []
    if "2026-07-19" in properties and "Sample_2026-07-19" not in properties:
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": properties["2026-07-19"]["sheetId"],
                        "title": "Sample_2026-07-19",
                    },
                    "fields": "title",
                }
            }
        )

    target_titles = list(payloads)
    for title in target_titles:
        if title in properties:
            requests.append({"deleteSheet": {"sheetId": properties[title]["sheetId"]}})
    for index, title in enumerate(target_titles):
        row_count = max(250, len(payloads[title]) + 25)
        column_count = max(
            20 if title == "Runs" else 12,
            len(payloads[title][2]) + 2,
        )
        requests.append(
            {
                "addSheet": {
                    "properties": {
                        "title": title,
                        "index": index,
                        "gridProperties": {
                            "rowCount": row_count,
                            "columnCount": column_count,
                            "frozenRowCount": 3,
                            "frozenColumnCount": 1,
                        },
                    }
                }
            }
        )
    requests.append(
        {
            "updateSpreadsheetProperties": {
                "properties": {"title": "Personal Job Hunt"},
                "fields": "title",
            }
        }
    )
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()

    value_updates = []
    for title, values in payloads.items():
        last_column = _column_letter(max(len(row) for row in values))
        value_updates.append(
            {
                "range": f"'{title}'!A1:{last_column}{len(values)}",
                "majorDimension": "ROWS",
                "values": values,
            }
        )
    contact_start = _column_letter(CONTACT_TOOL_START_COLUMN + 1)
    contact_end = _column_letter(
        CONTACT_TOOL_START_COLUMN + len(CONTACT_TOOL_HEADERS)
    )
    value_updates.append(
        {
            "range": (
                f"'Runs'!{contact_start}1:{contact_end}{len(contact_tool_payload)}"
            ),
            "majorDimension": "ROWS",
            "values": contact_tool_payload,
        }
    )
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": value_updates},
    ).execute()

    return sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title,index,gridProperties)",
    ).execute()


def _format_sheets(sheets, spreadsheet_id: str, metadata: dict, payloads: dict, date_title: str):
    sheet_ids = {
        item["properties"]["title"]: item["properties"]["sheetId"]
        for item in metadata.get("sheets") or []
    }
    requests = []
    tab_colors = {
        date_title: "0F766E",
        "Gmail_Alerts": "475569",
        "Official_Jobs": "15803D",
        "Job_Matches": "B45309",
        "Connections": "1D4ED8",
        "Resume_Scoring": "7E22CE",
        "Runs": "334155",
    }

    for title, values in payloads.items():
        sheet_id = sheet_ids[title]
        headers = values[2]
        row_count = len(values)
        column_count = len(headers)
        requests.extend(
            [
                {
                    "mergeCells": {
                        "range": _grid(
                            sheet_id,
                            0,
                            1,
                            1,
                            min(6, column_count),
                        ),
                        "mergeType": "MERGE_ALL",
                    }
                },
                {
                    "mergeCells": {
                        "range": _grid(
                            sheet_id,
                            1,
                            2,
                            1,
                            min(6, column_count),
                        ),
                        "mergeType": "MERGE_ALL",
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "tabColor": _rgb(tab_colors[title]),
                            "gridProperties": {
                                "frozenRowCount": 3,
                                "frozenColumnCount": 1,
                            },
                        },
                        "fields": "tabColor,gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
                    }
                },
                {
                    "repeatCell": {
                        "range": _grid(sheet_id, 0, 1, 0, column_count),
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": _rgb(tab_colors[title]),
                                "textFormat": {
                                    "foregroundColor": _rgb("FFFFFF"),
                                    "bold": True,
                                    "fontSize": 14,
                                },
                                "verticalAlignment": "MIDDLE",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": _grid(sheet_id, 1, 2, 0, column_count),
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": _rgb("E2E8F0"),
                                "textFormat": {"foregroundColor": _rgb("334155"), "italic": True},
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": _grid(sheet_id, 2, 3, 0, column_count),
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": _rgb("1E293B"),
                                "textFormat": {"foregroundColor": _rgb("FFFFFF"), "bold": True},
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat",
                    }
                },
                {
                    "repeatCell": {
                        "range": _grid(sheet_id, 3, max(4, row_count), 0, column_count),
                        "cell": {
                            "userEnteredFormat": {
                                "verticalAlignment": "TOP",
                                "wrapStrategy": "WRAP",
                                "textFormat": {"fontSize": 10},
                            }
                        },
                        "fields": "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy,userEnteredFormat.textFormat.fontSize",
                    }
                },
                {
                    "setBasicFilter": {
                        "filter": {"range": _grid(sheet_id, 2, max(3, row_count), 0, column_count)}
                    }
                },
                {
                    "addBanding": {
                        "bandedRange": {
                            "range": _grid(sheet_id, 2, max(3, row_count), 0, column_count),
                            "rowProperties": {
                                "headerColor": _rgb("1E293B"),
                                "firstBandColor": _rgb("FFFFFF"),
                                "secondBandColor": _rgb("F8FAFC"),
                            },
                        }
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                        "properties": {"pixelSize": 34},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
                        "properties": {"pixelSize": 52},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 2, "endIndex": 3},
                        "properties": {"pixelSize": 48},
                        "fields": "pixelSize",
                    }
                },
            ]
        )

        data_height = 190 if title in {date_title, "Connections"} else 72
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 3,
                        "endIndex": max(4, row_count),
                    },
                    "properties": {"pixelSize": data_height},
                    "fields": "pixelSize",
                }
            }
        )

    widths = {
        date_title: [90, 125, 85, 150, 220, 165, 120, 160, 280, 145, 90, 300, 230, 170, 150, 135, 105, 100, 280, 440, 90, 120, 360, 105, 300, 250, 320, 330, 85, 330, 440, 260, 120, 130],
        "Gmail_Alerts": [125, 85, 165, 240, 170, 120, 160, 300, 145, 100, 145, 90, 300, 90, 125, 120, 260],
        "Official_Jobs": [145, 150, 240, 180, 160, 115, 110, 100, 130, 105, 300, 440, 260, 240, 90, 125, 105, 330, 105],
        "Job_Matches": [125, 85, 165, 230, 145, 230, 300, 145, 90, 330, 90, 125, 105, 105],
        "Connections": [125, 145, 150, 230, 90, 110, 180, 230, 210, 280, 100, 330, 440],
        "Resume_Scoring": [130, 190, 520, 100, 420],
        "Runs": [190, 175, 175, 130, 105, 105, 115, 95, 145, 95, 110, 230, 380],
    }
    for title, column_widths in widths.items():
        sheet_id = sheet_ids[title]
        for column, pixels in enumerate(column_widths):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": column,
                            "endIndex": column + 1,
                        },
                        "properties": {"pixelSize": pixels},
                        "fields": "pixelSize",
                    }
                }
            )

    runs_sheet_id = sheet_ids["Runs"]
    contact_tool_payload = _contact_tool_payload()
    contact_start = CONTACT_TOOL_START_COLUMN
    contact_end = contact_start + len(CONTACT_TOOL_HEADERS)
    contact_rows = len(contact_tool_payload)
    requests.extend(
        [
            {
                "repeatCell": {
                    "range": _grid(runs_sheet_id, 0, 1, contact_start, contact_end),
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": _rgb("334155"),
                            "textFormat": {
                                "foregroundColor": _rgb("FFFFFF"),
                                "bold": True,
                                "fontSize": 14,
                            },
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat",
                }
            },
            {
                "repeatCell": {
                    "range": _grid(runs_sheet_id, 1, 2, contact_start, contact_end),
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": _rgb("E2E8F0"),
                            "textFormat": {
                                "foregroundColor": _rgb("334155"),
                                "italic": True,
                            },
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat",
                }
            },
            {
                "repeatCell": {
                    "range": _grid(runs_sheet_id, 2, 3, contact_start, contact_end),
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": _rgb("1E293B"),
                            "textFormat": {
                                "foregroundColor": _rgb("FFFFFF"),
                                "bold": True,
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat",
                }
            },
            {
                "repeatCell": {
                    "range": _grid(
                        runs_sheet_id, 3, contact_rows, contact_start, contact_end
                    ),
                    "cell": {
                        "userEnteredFormat": {
                            "verticalAlignment": "TOP",
                            "wrapStrategy": "WRAP",
                            "textFormat": {"fontSize": 10},
                        }
                    },
                    "fields": (
                        "userEnteredFormat.verticalAlignment,"
                        "userEnteredFormat.wrapStrategy,"
                        "userEnteredFormat.textFormat.fontSize"
                    ),
                }
            },
            {
                "addBanding": {
                    "bandedRange": {
                        "range": _grid(
                            runs_sheet_id, 2, contact_rows, contact_start, contact_end
                        ),
                        "rowProperties": {
                            "headerColor": _rgb("1E293B"),
                            "firstBandColor": _rgb("FFFFFF"),
                            "secondBandColor": _rgb("F8FAFC"),
                        },
                    }
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": runs_sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 3,
                        "endIndex": contact_rows,
                    },
                    "properties": {"pixelSize": 72},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": runs_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 13,
                        "endIndex": 14,
                    },
                    "properties": {"pixelSize": 28},
                    "fields": "pixelSize",
                }
            },
        ]
    )
    for offset, pixels in enumerate([170, 250, 105, 420]):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": runs_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": contact_start + offset,
                        "endIndex": contact_start + offset + 1,
                    },
                    "properties": {"pixelSize": pixels},
                    "fields": "pixelSize",
                }
            }
        )

    main_sheet_id = sheet_ids[date_title]
    main_headers = payloads[date_title][2]
    main_rows = len(payloads[date_title])
    priority_col = main_headers.index("priority")
    status_col = main_headers.index("application_status")
    score_col = main_headers.index("eligibility_score")
    active_col = main_headers.index("active_status")
    requests.extend(
        [
            {
                "setDataValidation": {
                    "range": _grid(main_sheet_id, 3, max(4, main_rows), priority_col, priority_col + 1),
                    "rule": {
                        "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": item} for item in ["High", "Medium", "Review", "Low", "Skip"]]},
                        "strict": True,
                        "showCustomUi": True,
                    },
                }
            },
            {
                "setDataValidation": {
                    "range": _grid(main_sheet_id, 3, max(4, main_rows), status_col, status_col + 1),
                    "rule": {
                        "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": item} for item in ["not_started", "reviewing", "saved", "applied", "interview", "rejected", "withdrawn"]]},
                        "strict": True,
                        "showCustomUi": True,
                    },
                }
            },
        ]
    )
    for condition, color in [
        ({"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "85"}]}, "DCFCE7"),
        ({"type": "NUMBER_BETWEEN", "values": [{"userEnteredValue": "70"}, {"userEnteredValue": "84"}]}, "FEF3C7"),
        ({"type": "NUMBER_LESS", "values": [{"userEnteredValue": "70"}]}, "FEE2E2"),
    ]:
        requests.append(
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [_grid(main_sheet_id, 3, max(4, main_rows), score_col, score_col + 1)],
                        "booleanRule": {
                            "condition": condition,
                            "format": {"backgroundColor": _rgb(color), "textFormat": {"bold": True}},
                        },
                    },
                    "index": 0,
                }
            }
        )
    for text_value, color in [("closed", "FEE2E2"), ("filled", "FEE2E2"), ("active", "DCFCE7"), ("not_verified", "E2E8F0")]:
        requests.append(
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [_grid(main_sheet_id, 3, max(4, main_rows), active_col, active_col + 1)],
                        "booleanRule": {
                            "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": text_value}]},
                            "format": {"backgroundColor": _rgb(color), "textFormat": {"bold": True}},
                        },
                    },
                    "index": 0,
                }
            }
        )

    id_start = main_headers.index("alert_record_id")
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": main_sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": id_start,
                    "endIndex": len(main_headers),
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }
    )

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()


def _apply_rich_text_links(
    sheets, spreadsheet_id: str, metadata: dict, data: dict, date_title: str
) -> list[str]:
    """Apply per-substring links after normal cell values and formatting are written."""

    sheet_ids = {
        item["properties"]["title"]: item["properties"]["sheetId"]
        for item in metadata.get("sheets") or []
    }
    requests = []
    expected_urls = []
    groups = [
        (
            date_title,
            MAIN_HEADERS,
            data["main"],
            {
                "top_referral_candidates": "_top_referral_links",
                "cold_message": "_cold_message_links",
            },
        ),
        (
            "Connections",
            CONNECTION_HEADERS,
            data["connections"],
            {"cold_message": "_cold_message_links"},
        ),
    ]
    for title, headers, records, linked_fields in groups:
        sheet_id = sheet_ids[title]
        for row_index, record in enumerate(records, start=3):
            for field, links_key in linked_fields.items():
                links = record.get(links_key) or []
                runs = rich_text_link_runs(record.get(field) or "", links)
                if not runs:
                    continue
                column_index = headers.index(field)
                requests.append(
                    {
                        "updateCells": {
                            "range": _grid(
                                sheet_id,
                                row_index,
                                row_index + 1,
                                column_index,
                                column_index + 1,
                            ),
                            "rows": [{"values": [{"textFormatRuns": runs}]}],
                            "fields": "textFormatRuns",
                        }
                    }
                )
                expected_urls.extend(link[2] for link in links)
    if requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
    return expected_urls


def _verify_sheet(
    sheets,
    spreadsheet_id: str,
    payloads: dict,
    date_title: str,
    expected_rich_text_urls: list[str],
) -> dict:
    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="properties.title,sheets.properties(title,index,gridProperties)",
    ).execute()
    actual_titles = [item["properties"]["title"] for item in metadata.get("sheets") or []]
    expected_titles = list(payloads)
    missing = [title for title in expected_titles if title not in actual_titles]
    if missing:
        raise RuntimeError(f"Production tracker verification failed; missing tabs: {missing}")

    grid_by_title = {
        item["properties"]["title"]: item["properties"].get("gridProperties") or {}
        for item in metadata.get("sheets") or []
    }
    for title in expected_titles:
        grid = grid_by_title[title]
        if grid.get("frozenRowCount") != 3 or grid.get("frozenColumnCount") != 1:
            raise RuntimeError(
                f"Freeze-pane verification failed for {title}: {grid}"
            )

    ranges = []
    for title, values in payloads.items():
        last_column = _column_letter(len(values[2]))
        ranges.append(f"'{title}'!A1:{last_column}{len(values)}")
    contact_tool_payload = _contact_tool_payload()
    contact_start = _column_letter(CONTACT_TOOL_START_COLUMN + 1)
    contact_end = _column_letter(
        CONTACT_TOOL_START_COLUMN + len(CONTACT_TOOL_HEADERS)
    )
    contact_range = (
        f"'Runs'!{contact_start}1:{contact_end}{len(contact_tool_payload)}"
    )
    ranges.append(contact_range)
    formula_response = sheets.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=ranges,
        valueRenderOption="FORMULA",
    ).execute()
    hyperlink_count = 0
    formula_errors = []
    privacy_violations = []
    for value_range in formula_response.get("valueRanges") or []:
        range_name = value_range.get("range") or ""
        for row_number, row in enumerate(value_range.get("values") or [], start=1):
            for value in row:
                text = str(value)
                if text.startswith("=HYPERLINK("):
                    hyperlink_count += 1
                if text.startswith(("#REF!", "#VALUE!", "#N/A", "#NAME?")):
                    formula_errors.append((range_name, row_number, text))
                if "Connections" in range_name and re.search(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", text):
                    privacy_violations.append((range_name, row_number))
    if formula_errors:
        raise RuntimeError(f"Formula errors found: {formula_errors[:5]}")
    if privacy_violations:
        raise RuntimeError("Connection email addresses were detected in the production Sheet.")

    contact_response = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=contact_range,
        valueRenderOption="FORMULA",
    ).execute().get("values") or []
    expected_contact_formulas = [
        row[0] for row in contact_tool_payload[3:]
    ]
    actual_contact_formulas = [
        row[0] for row in contact_response[3:] if row
    ]
    if actual_contact_formulas != expected_contact_formulas:
        raise RuntimeError("Contact lookup tool hyperlink verification failed.")

    connection_name_range = (
        f"'Connections'!G4:G{len(payloads['Connections'])}"
    )
    connection_name_values = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=connection_name_range,
        valueRenderOption="FORMULA",
    ).execute().get("values") or []
    profile_name_hyperlinks = sum(
        1
        for row in connection_name_values
        if row and str(row[0]).startswith("=HYPERLINK(")
    )
    expected_profile_name_hyperlinks = len(payloads["Connections"]) - 3
    if profile_name_hyperlinks != expected_profile_name_hyperlinks:
        raise RuntimeError(
            "Referral-name hyperlink verification failed: "
            f"expected {expected_profile_name_hyperlinks}, got {profile_name_hyperlinks}."
        )

    rich_ranges = [
        f"'{date_title}'!AD4:AE{len(payloads[date_title])}",
        f"'Connections'!M4:M{len(payloads['Connections'])}",
    ]
    rich_response = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=rich_ranges,
        includeGridData=True,
        fields="sheets(data(rowData(values(textFormatRuns))))",
    ).execute()
    actual_rich_text_urls = []
    for sheet in rich_response.get("sheets") or []:
        for grid_data in sheet.get("data") or []:
            for row in grid_data.get("rowData") or []:
                for cell in row.get("values") or []:
                    for run in cell.get("textFormatRuns") or []:
                        uri = ((run.get("format") or {}).get("link") or {}).get("uri")
                        if uri:
                            actual_rich_text_urls.append(uri)
    if sorted(actual_rich_text_urls) != sorted(expected_rich_text_urls):
        raise RuntimeError(
            "Rich-text hyperlink verification failed: "
            f"expected {len(expected_rich_text_urls)}, got {len(actual_rich_text_urls)}."
        )

    message_ranges = [
        f"'{date_title}'!AE4:AE{len(payloads[date_title])}",
        f"'Connections'!M4:M{len(payloads['Connections'])}",
    ]
    message_response = sheets.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=message_ranges,
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    actual_structured_messages = sum(
        1
        for value_range in message_response.get("valueRanges") or []
        for row in value_range.get("values") or []
        if row
        and str(row[0]).startswith("Hi ")
        and "\n\nJob posting:\n" in str(row[0])
        and str(row[0]).endswith("Thank you for your time,\nAsrith")
    )
    expected_structured_messages = 0
    for title in (date_title, "Connections"):
        values = payloads[title]
        cold_message_index = values[2].index("cold_message")
        expected_structured_messages += sum(
            1
            for row in values[3:]
            if len(row) > cold_message_index
            and str(row[cold_message_index]).startswith("Hi ")
        )
    if actual_structured_messages != expected_structured_messages:
        raise RuntimeError(
            "Structured cold-message verification failed: "
            f"expected {expected_structured_messages}, got {actual_structured_messages}."
        )

    main_values = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{date_title}'!A1:AH",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values") or []
    expected_main_rows = len(payloads[date_title])
    if len(main_values) != expected_main_rows:
        raise RuntimeError(
            f"Main-tab row count mismatch: expected {expected_main_rows}, got {len(main_values)}"
        )
    return {
        "tab_order": actual_titles,
        "hyperlink_formulas": hyperlink_count,
        "referral_name_hyperlinks": profile_name_hyperlinks,
        "cold_message_and_referral_rich_links": len(actual_rich_text_urls),
        "structured_cold_messages": actual_structured_messages,
        "contact_tool_links": len(actual_contact_formulas),
        "main_data_rows": max(0, len(main_values) - 3),
        "formula_errors": 0,
        "connection_email_leaks": 0,
    }


def build_production_tracker(
    spreadsheet_id: str,
    token_path: Path,
    alert_path: Path,
    research_path: Path,
    connection_path: Path,
    run_date: str,
    dry_run: bool = False,
) -> dict:
    started = datetime.now(TIME_ZONE)
    alert_payload = _load_json(alert_path)
    research = _load_json(research_path)
    data = _build_tracker_data(alert_payload, research, connection_path)

    if dry_run:
        return {"dry_run": True, **data["stats"]}

    credentials = load_stored_credentials(token_path)
    if credentials is None:
        raise RuntimeError("Saved Google credentials are unavailable; reconnect in Streamlit.")
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    preserved = _read_existing_user_fields(sheets, spreadsheet_id, run_date)
    _apply_preserved_fields(data["main"], preserved)

    finished = datetime.now(TIME_ZONE)
    run_record = {
        "run_id": started.strftime("production-%Y%m%d-%H%M%S"),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "status": "completed",
        "gmail_messages": data["stats"]["gmail_messages"],
        "unique_alerts": data["stats"]["unique_alerts"],
        "official_postings": data["stats"]["official_postings"],
        "match_rows": data["stats"]["match_rows"],
        "alerts_without_official_result": data["stats"]["alerts_without_official_result"],
        "main_rows": data["stats"]["main_rows"],
        "connection_rows": data["stats"]["connection_rows"],
        "spreadsheet_id": spreadsheet_id,
        "notes": "Real production run; public official sources only; no LinkedIn/Naukri protected-page scraping.",
    }

    stats = data["stats"]
    payloads = {
        run_date: _sheet_payload(
            f"Application Queue — {run_date}",
            (
                f"{stats['main_rows']} queue rows • {stats['unique_alerts']} Gmail alerts • "
                f"{stats['official_postings']} official postings • "
                f"{stats['alerts_without_official_result']} checked with no result • "
                f"{stats['alerts_pending_research']} pending official research.\n"
                "Official-match confidence and resume eligibility are separate."
            ),
            MAIN_HEADERS,
            data["main"],
        ),
        "Gmail_Alerts": _sheet_payload(
            "Gmail Alerts — normalized source cards",
            (
                f"{stats['unique_alerts']} unique jobs parsed from "
                f"{stats['gmail_messages']} approved-label emails; "
                f"{stats['alerts_pending_research']} await official-site research."
            ),
            GMAIL_HEADERS,
            data["gmail"],
        ),
        "Official_Jobs": _sheet_payload(
            "Official Employer Jobs",
            f"{stats['official_postings']} public employer postings verified on {stats['verified_at']}; descriptions are concise paraphrases.",
            OFFICIAL_HEADERS,
            data["official"],
        ),
        "Job_Matches": _sheet_payload(
            "Alert → Official Job Matches",
            "One row per alert/candidate relationship. A high official-match score does not imply high resume eligibility.",
            MATCH_HEADERS,
            data["matches"],
        ),
        "Connections": _sheet_payload(
            "Referral Candidates",
            (
                f"Top three same-company connections per tracker row from {stats['raw_connections']} supplied export rows. "
                "Emails are excluded; ranking is role relevance, not relationship strength."
            ),
            CONNECTION_HEADERS,
            data["connections"],
        ),
        "Resume_Scoring": _sheet_payload(
            "Resume Evidence & Scoring Rules",
            "Transparent components total 100 for official postings; alert-only preliminary scores are capped at 60.",
            RESUME_HEADERS,
            data["resume"],
        ),
        "Runs": _sheet_payload(
            "Production Run Audit",
            "One row per generated production workbook run.",
            RUN_HEADERS,
            [run_record],
        ),
    }

    metadata = _replace_production_sheets(sheets, spreadsheet_id, run_date, payloads)
    _format_sheets(sheets, spreadsheet_id, metadata, payloads, run_date)
    expected_rich_text_urls = _apply_rich_text_links(
        sheets, spreadsheet_id, metadata, data, run_date
    )
    verification = _verify_sheet(
        sheets,
        spreadsheet_id,
        payloads,
        run_date,
        expected_rich_text_urls,
    )
    return {
        "dry_run": False,
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        **stats,
        "verification": verification,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--alerts", type=Path, default=DEFAULT_ALERTS)
    parser.add_argument("--research", type=Path, default=DEFAULT_RESEARCH)
    parser.add_argument("--connections", type=Path, default=DEFAULT_CONNECTIONS)
    parser.add_argument("--date", default=datetime.now(TIME_ZONE).date().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = build_production_tracker(
        spreadsheet_id=args.spreadsheet_id,
        token_path=args.token,
        alert_path=args.alerts,
        research_path=args.research,
        connection_path=args.connections,
        run_date=args.date,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
