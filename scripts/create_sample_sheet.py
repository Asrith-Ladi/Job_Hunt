"""Create a formatted Google Sheets sample for the approved six-alert pilot."""

import argparse
import json
from pathlib import Path

from googleapiclient.discovery import build

from job_hunt.integrations.google_auth import load_stored_credentials
from job_hunt.integrations.sheets import hyperlink_formula


TIME_ZONE = "Asia/Kolkata"


def _rgb(hex_color):
    value = hex_color.lstrip("#")
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


def _column_letter(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _format_request(grid_range, cell_format, fields="userEnteredFormat"):
    return {
        "repeatCell": {
            "range": grid_range,
            "cell": {"userEnteredFormat": cell_format},
            "fields": fields,
        }
    }


def _column_width(sheet_id, column_index, pixels):
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": column_index,
                "endIndex": column_index + 1,
            },
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }
    }


def _row_height(sheet_id, start_index, end_index, pixels):
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": start_index,
                "endIndex": end_index,
            },
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }
    }


def _validation_request(grid_range, values):
    return {
        "setDataValidation": {
            "range": grid_range,
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": value} for value in values],
                },
                "strict": True,
                "showCustomUi": True,
            },
        }
    }


def _conditional_text(sheet_id, start_row, end_row, column, text, fill, font):
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [_grid(sheet_id, start_row, end_row, column, column + 1)],
                "booleanRule": {
                    "condition": {
                        "type": "TEXT_EQ",
                        "values": [{"userEnteredValue": text}],
                    },
                    "format": {
                        "backgroundColor": _rgb(fill),
                        "textFormat": {
                            "foregroundColor": _rgb(font),
                            "bold": True,
                        },
                    },
                },
            },
            "index": 0,
        }
    }


def _sample_hyperlink_updates(data, sample_date):
    """Build targeted formula writes while keeping every full URL visible."""

    specifications = [
        (sample_date, 6, (5, 14)),
        ("Gmail_Alerts", 2, (11,)),
        ("Official_Jobs", 2, (4,)),
    ]
    updates = []
    for sheet_title, first_row, url_columns in specifications:
        for offset, row in enumerate(data[sheet_title][1:]):
            for column_index in url_columns:
                formula = hyperlink_formula(row[column_index])
                if formula:
                    updates.append(
                        {
                            "range": "'{0}'!{1}{2}".format(
                                sheet_title,
                                _column_letter(column_index + 1),
                                first_row + offset,
                            ),
                            "values": [[formula]],
                        }
                    )
    return updates


def _migrate_sample_gmail_alerts_tab(sheets, spreadsheet_id, metadata):
    """Rename the legacy sample tab in place without altering its contents or style."""

    properties_by_title = {
        item["properties"]["title"]: item["properties"]
        for item in metadata.get("sheets") or []
    }
    if "Gmail_Alerts" not in properties_by_title and "Jobs" in properties_by_title:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": properties_by_title["Jobs"]["sheetId"],
                                "title": "Gmail_Alerts",
                            },
                            "fields": "title",
                        }
                    }
                ]
            },
        ).execute()
        properties_by_title["Jobs"]["title"] = "Gmail_Alerts"
    return metadata


def _review_rows(sample_date):
    source_rows = [
        [
            sample_date,
            "linkedin",
            "EY",
            "Digital - Senior",
            "Hyderabad (On-site)",
            "https://linkedin.com/comm/jobs/view/4439237316",
            1,
            "Digital- GEN AI Nvidia- Senior",
            "Hyderabad",
            "6-9 years",
            "official_portal",
            6,
            9,
            "https://careers.ey.com/ey/job/Hyderabad-Digital-GEN-AI-Nvidia-Senior-TG-500081/1283178001/",
            "review_required",
            70,
            "Company and location match; generic alert title does not prove the requisition.",
            "not_started",
        ],
        [
            sample_date,
            "linkedin",
            "EY",
            "Digital - Senior",
            "Hyderabad (On-site)",
            "https://linkedin.com/comm/jobs/view/4439237316",
            2,
            "EY - GDS Consulting - AIA - Python Full stack AI Engineer - Senior",
            "Hyderabad",
            "",
            "unknown",
            "",
            "",
            "https://careers.ey.com/ey/job/Hyderabad-EY-GDS-Consulting-AIA-Python-Full-stack-AI-Engineer-Senior-TG-500081/1411524633/",
            "review_required",
            65,
            "Related official senior digital/AI role; experience was not clearly stated.",
            "not_started",
        ],
        [
            sample_date,
            "linkedin",
            "EY",
            "Digital-Senior",
            "Hyderabad (On-site)",
            "https://linkedin.com/comm/jobs/view/4439241132",
            1,
            "Digital- GEN AI Nvidia- Senior",
            "Hyderabad",
            "6-9 years",
            "official_portal",
            6,
            9,
            "https://careers.ey.com/ey/job/Hyderabad-Digital-GEN-AI-Nvidia-Senior-TG-500081/1283178001/",
            "review_required",
            70,
            "Company and location match; generic alert title does not prove the requisition.",
            "not_started",
        ],
        [
            sample_date,
            "linkedin",
            "EY",
            "Digital-Senior",
            "Hyderabad (On-site)",
            "https://linkedin.com/comm/jobs/view/4439241132",
            2,
            "EY - GDS Consulting - AIA - Python Full stack AI Engineer - Senior",
            "Hyderabad",
            "",
            "unknown",
            "",
            "",
            "https://careers.ey.com/ey/job/Hyderabad-EY-GDS-Consulting-AIA-Python-Full-stack-AI-Engineer-Senior-TG-500081/1411524633/",
            "review_required",
            65,
            "Related official senior digital/AI role; experience was not clearly stated.",
            "not_started",
        ],
        [
            sample_date,
            "linkedin",
            "Real",
            "Senior Machine Learning Engineer",
            "India (Remote)",
            "https://linkedin.com/comm/jobs/view/4423231055",
            1,
            "Senior Machine Learning Engineer",
            "India (Remote)",
            "5+ years",
            "official_portal",
            5,
            "",
            "https://jobs.ashbyhq.com/real/d36a6c61-ff2d-4530-bcb7-f3cead4b2bac/",
            "exact",
            98,
            "Exact company, title, location, and employer ATS posting.",
            "not_started",
        ],
        [
            sample_date,
            "naukri",
            "Covalense Global",
            "Gen AI Engineer",
            "Hyderabad",
            "https://naukri.com/jd/job-listings-gen-ai-engineer-covalense-global-hyderabad-2-to-6-years-130726503094",
            1,
            "Gen AI Engineer",
            "Hyderabad, India (Remote)",
            "2-6 years",
            "alert_url",
            2,
            6,
            "https://www.covalenseglobal.com/careers",
            "exact",
            95,
            "Exact employer role; years come from the alert URL, not the employer page.",
            "not_started",
        ],
        [
            sample_date,
            "naukri",
            "Accenture",
            "AI / ML Engineer",
            "Hyderabad",
            "https://naukri.com/jd/job-listings-ai-ml-engineer-accenture-solutions-pvt-ltd-hyderabad-3-to-8-years-130726930566",
            1,
            "AI / ML Engineer - Machine Learning",
            "Hyderabad",
            "5-10 years",
            "official_portal",
            5,
            10,
            "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5118203-S1894954_en",
            "review_required",
            88,
            "Same company, title, and location; exact requisition is not identified by alert.",
            "not_started",
        ],
        [
            sample_date,
            "naukri",
            "Accenture",
            "AI / ML Engineer",
            "Hyderabad",
            "https://naukri.com/jd/job-listings-ai-ml-engineer-accenture-solutions-pvt-ltd-hyderabad-3-to-8-years-130726930566",
            2,
            "AI / ML Engineer - Large Language Models",
            "Hyderabad",
            "5-10 years",
            "official_portal",
            5,
            10,
            "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5094709-S1885176_en",
            "review_required",
            87,
            "Same company, title, and location; LLM specialization needs user review.",
            "not_started",
        ],
        [
            sample_date,
            "naukri",
            "Accenture",
            "AI / ML Engineer",
            "Hyderabad",
            "https://naukri.com/jd/job-listings-ai-ml-engineer-accenture-solutions-pvt-ltd-hyderabad-3-to-8-years-130726930566",
            3,
            "AI / ML Engineer - Machine Learning Operations",
            "Hyderabad",
            "5-10 years (minimum 7.5)",
            "official_portal",
            7.5,
            10,
            "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5223735-S1923454_en",
            "review_required",
            84,
            "Same title/location with MLOps specialization and 7.5-year minimum.",
            "not_started",
        ],
        [
            sample_date,
            "naukri",
            "Accenture",
            "AI / ML Engineer",
            "Hyderabad",
            "https://naukri.com/jd/job-listings-ai-ml-engineer-accenture-solutions-pvt-ltd-hyderabad-3-to-8-years-130726930566",
            4,
            "AI / ML Engineer - Data Science",
            "Hyderabad",
            "7.5+ years",
            "official_portal",
            7.5,
            "",
            "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5291800-S1933742_en",
            "review_required",
            82,
            "Same title/location with Data Science specialization; user review required.",
            "not_started",
        ],
        [
            sample_date,
            "naukri",
            "Proxelera",
            "AI/ML Engineer",
            "Hyderabad",
            "https://naukri.com/jd/job-listings-ai-ml-engineer-proxelera-hyderabad-2-to-5-years-170726502402",
            "",
            "",
            "",
            "2-5 years",
            "alert_url",
            2,
            5,
            "",
            "no_official_result",
            0,
            "Official careers page exposes no detailed posting for this role.",
            "not_started",
        ],
    ]
    rows = []
    for row_number, source in enumerate(source_rows, start=6):
        formula = (
            '=IF(L{0}="","unknown",IF(OR(AND(M{0}<>"",M{0}<$B$3),'
            'L{0}>$D$3),"outside_target",IF(AND(L{0}>=$B$3,L{0}<=$D$3),'
            '"preferred","possible_overlap")))'
        ).format(row_number)
        rows.append(source[:13] + [formula] + source[13:])
    return rows


def _workbook_data(sample_date):
    review_headers = [
        "review_date",
        "alert_source",
        "company",
        "alert_title",
        "alert_location",
        "alert_url",
        "candidate_rank",
        "official_title",
        "official_location",
        "years_of_experience",
        "experience_source",
        "experience_min_years",
        "experience_max_years",
        "experience_fit",
        "official_url",
        "match_status",
        "match_score",
        "match_reason",
        "application_status",
    ]
    jobs_headers = [
        "job_record_id",
        "owner_id",
        "alert_source",
        "company",
        "title",
        "location",
        "years_of_experience",
        "experience_source",
        "experience_min_years",
        "experience_max_years",
        "experience_fit",
        "source_url",
        "email_received_at",
        "official_search_status",
        "selected_official_job_id",
        "application_status",
        "notes",
        "last_seen_at",
    ]
    jobs_rows = [
        ["li_4439237316", "personal", "linkedin", "EY", "Digital - Senior", "Hyderabad (On-site)", "", "unknown", "", "", "unknown", "https://linkedin.com/comm/jobs/view/4439237316", "2026-07-19 12:36:56", "candidates_found", "", "not_started", "", "2026-07-19 20:00:00"],
        ["li_4439241132", "personal", "linkedin", "EY", "Digital-Senior", "Hyderabad (On-site)", "", "unknown", "", "", "unknown", "https://linkedin.com/comm/jobs/view/4439241132", "2026-07-19 12:36:56", "candidates_found", "", "not_started", "", "2026-07-19 20:00:00"],
        ["li_4423231055", "personal", "linkedin", "Real", "Senior Machine Learning Engineer", "India (Remote)", "", "unknown", "", "", "unknown", "https://linkedin.com/comm/jobs/view/4423231055", "2026-07-19 12:36:56", "exact_match", "official_real_smle", "not_started", "", "2026-07-19 20:00:00"],
        ["nk_130726503094", "personal", "naukri", "Covalense Global", "Gen AI Engineer", "Hyderabad", "2-6 years", "alert_url", 2, 6, "possible_overlap", "https://naukri.com/jd/job-listings-gen-ai-engineer-covalense-global-hyderabad-2-to-6-years-130726503094", "2026-07-18 14:38:52", "exact_match", "official_covalense_genai", "not_started", "", "2026-07-19 20:00:00"],
        ["nk_130726930566", "personal", "naukri", "Accenture", "AI / ML Engineer", "Hyderabad", "3-8 years", "alert_url", 3, 8, "possible_overlap", "https://naukri.com/jd/job-listings-ai-ml-engineer-accenture-solutions-pvt-ltd-hyderabad-3-to-8-years-130726930566", "2026-07-18 14:38:52", "candidates_found", "", "not_started", "", "2026-07-19 20:00:00"],
        ["nk_170726502402", "personal", "naukri", "Proxelera", "AI/ML Engineer", "Hyderabad", "2-5 years", "alert_url", 2, 5, "possible_overlap", "https://naukri.com/jd/job-listings-ai-ml-engineer-proxelera-hyderabad-2-to-5-years-170726502402", "2026-07-18 14:38:52", "no_exact_official", "", "not_started", "", "2026-07-19 20:00:00"],
    ]
    official_headers = [
        "official_job_id",
        "company",
        "title",
        "location",
        "official_url",
        "requisition_id",
        "years_of_experience",
        "experience_source",
        "experience_min_years",
        "experience_max_years",
        "experience_fit",
        "employment_type",
        "workplace_type",
        "department",
        "primary_skill",
        "published_at",
        "description_summary",
        "active_status",
        "last_verified_at",
        "application_status",
        "notes",
    ]
    official_rows = [
        ["official_ey_1671460", "EY", "Digital- GEN AI Nvidia- Senior", "Hyderabad", "https://careers.ey.com/ey/job/Hyderabad-Digital-GEN-AI-Nvidia-Senior-TG-500081/1283178001/", "1671460", "6-9 years", "official_portal", 6, 9, "preferred", "", "On-site", "Assurance Digital", "Data Science / AI", "2026-03-06", "Senior data-science role covering analytics, NLP, machine learning, and deep learning.", "public_page_found", sample_date, "not_started", "Related candidate; exact LinkedIn requisition not established."],
        ["official_ey_1703723", "EY", "EY - GDS Consulting - AIA - Python Full stack AI Engineer - Senior", "Hyderabad", "https://careers.ey.com/ey/job/Hyderabad-EY-GDS-Consulting-AIA-Python-Full-stack-AI-Engineer-Senior-TG-500081/1411524633/", "1703723", "", "unknown", "", "", "unknown", "Full time", "", "AIA", "Python / AI", "2026-07-05", "Senior Python full-stack role with AI, GenAI, agentic AI, APIs, and cloud exposure.", "public_page_found", sample_date, "not_started", "Related candidate; employer experience not clearly stated."],
        ["official_real_smle", "Real", "Senior Machine Learning Engineer", "India (Remote)", "https://jobs.ashbyhq.com/real/d36a6c61-ff2d-4530-bcb7-f3cead4b2bac/", "d36a6c61-ff2d-4530-bcb7-f3cead4b2bac", "5+ years", "official_portal", 5, "", "preferred", "Full time", "Remote", "Research & Development", "AI/ML, GenAI, LLM", "", "Build production LLM and agentic systems for Real's India-based remote R&D team.", "public_page_found", sample_date, "not_started", "High-confidence exact match."],
        ["official_covalense_genai", "Covalense Global", "Gen AI Engineer", "Hyderabad, India", "https://www.covalenseglobal.com/careers", "", "", "unknown", "", "", "unknown", "", "Remote", "", "Generative AI", "", "Design and develop generative-AI architectures, algorithms, and frameworks.", "public_page_found", sample_date, "not_started", "Experience remains sourced from the alert URL."],
        ["official_acc_5118203", "Accenture", "AI / ML Engineer", "Hyderabad", "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5118203-S1894954_en", "ATCI-5118203-S1894954", "5-10 years", "official_portal", 5, 10, "preferred", "Full time", "", "AI LLM Technology Architecture", "Machine Learning", "", "Build ML/LLM workflows, retrieval, document extraction, OCR, and production-ready features.", "public_page_found", sample_date, "not_started", "Candidate 1 for manual review."],
        ["official_acc_5094709", "Accenture", "AI / ML Engineer", "Hyderabad", "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5094709-S1885176_en", "ATCI-5094709-S1885176", "5-10 years", "official_portal", 5, 10, "preferred", "Full time", "", "AI/ML Computational Science", "Large Language Models", "", "Develop production AI applications using LLMs, cloud AI, deep learning, and NLP.", "public_page_found", sample_date, "not_started", "Candidate 2 for manual review."],
        ["official_acc_5223735", "Accenture", "AI / ML Engineer", "Hyderabad", "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5223735-S1923454_en", "ATCI-5223735-S1923454", "5-10 years (minimum 7.5)", "official_portal", 7.5, 10, "preferred", "Full time", "", "AI/ML Computational Science", "Machine Learning Operations", "", "Design AI/ML decision frameworks with a Machine Learning Operations specialization.", "public_page_found", sample_date, "not_started", "Candidate 3 for manual review."],
        ["official_acc_5291800", "Accenture", "AI / ML Engineer", "Hyderabad", "https://www.accenture.com/in-en/careers/jobdetails?id=ATCI-5291800-S1933742_en", "ATCI-5291800-S1933742", "7.5+ years", "official_portal", 7.5, "", "preferred", "Full time", "", "AI/ML Computational Science", "Data Science", "", "Lead AI and machine-learning solution design with a Data Science specialization.", "public_page_found", sample_date, "not_started", "Candidate 4 for manual review."],
    ]
    match_headers = [
        "match_id",
        "job_record_id",
        "official_job_id",
        "candidate_rank",
        "match_score",
        "match_status",
        "match_reasons",
        "user_review_status",
        "created_at",
    ]
    match_rows = [
        ["match_ey1_1", "li_4439237316", "official_ey_1671460", 1, 70, "review_required", "Company/location match; generic title prevents exact identity.", "pending", sample_date],
        ["match_ey1_2", "li_4439237316", "official_ey_1703723", 2, 65, "review_required", "Related AI senior role; title differs.", "pending", sample_date],
        ["match_ey2_1", "li_4439241132", "official_ey_1671460", 1, 70, "review_required", "Company/location match; generic title prevents exact identity.", "pending", sample_date],
        ["match_ey2_2", "li_4439241132", "official_ey_1703723", 2, 65, "review_required", "Related AI senior role; title differs.", "pending", sample_date],
        ["match_real_1", "li_4423231055", "official_real_smle", 1, 98, "exact", "Company, title, location, and official ATS page align.", "pending", sample_date],
        ["match_covalense_1", "nk_130726503094", "official_covalense_genai", 1, 95, "exact", "Exact employer title and Hyderabad location.", "pending", sample_date],
        ["match_acc_1", "nk_130726930566", "official_acc_5118203", 1, 88, "review_required", "Same title/location; Machine Learning specialization.", "pending", sample_date],
        ["match_acc_2", "nk_130726930566", "official_acc_5094709", 2, 87, "review_required", "Same title/location; LLM specialization.", "pending", sample_date],
        ["match_acc_3", "nk_130726930566", "official_acc_5223735", 3, 84, "review_required", "Same title/location; MLOps specialization.", "pending", sample_date],
        ["match_acc_4", "nk_130726930566", "official_acc_5291800", 4, 82, "review_required", "Same title/location; Data Science specialization.", "pending", sample_date],
    ]
    run_headers = [
        "run_id",
        "run_date_local",
        "started_at",
        "finished_at",
        "run_type",
        "alerts_reviewed",
        "official_jobs_found",
        "matches_created",
        "status",
        "notes",
    ]
    run_rows = [["sample_20260719", sample_date, "2026-07-19 20:00:00", "2026-07-19 20:05:00", "sample_pilot", 6, 8, 10, "completed", "Interactive official-source sample; not an automated production run."]]
    return {
        sample_date: [review_headers] + _review_rows(sample_date),
        "Gmail_Alerts": [jobs_headers] + jobs_rows,
        "Official_Jobs": [official_headers] + official_rows,
        "Job_Matches": [match_headers] + match_rows,
        "Runs": [run_headers] + run_rows,
    }


def _style_requests(sheet_ids, row_counts, sample_date):
    requests = []
    body_format = {
        "textFormat": {"fontFamily": "Arial", "fontSize": 10},
        "verticalAlignment": "TOP",
        "wrapStrategy": "WRAP",
    }
    header_colors = {
        sample_date: "0F766E",
        "Gmail_Alerts": "334155",
        "Official_Jobs": "166534",
        "Job_Matches": "92400E",
        "Runs": "5B21B6",
    }
    column_counts = {sample_date: 19, "Gmail_Alerts": 18, "Official_Jobs": 21, "Job_Matches": 9, "Runs": 10}
    for title, sheet_id in sheet_ids.items():
        row_count = row_counts[title]
        column_count = column_counts[title]
        frozen_rows = 5 if title == sample_date else 1
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": frozen_rows,
                            "frozenColumnCount": 3 if title == sample_date else 2,
                            "hideGridlines": True,
                        },
                    },
                    "fields": (
                        "gridProperties.frozenRowCount,gridProperties.frozenColumnCount,"
                        "gridProperties.hideGridlines"
                    ),
                }
            }
        )
        data_start = 4 if title == sample_date else 0
        requests.append(_format_request(_grid(sheet_id, data_start, row_count, 0, column_count), body_format))
        header_row = 4 if title == sample_date else 0
        header_format = {
            "backgroundColor": _rgb(header_colors[title]),
            "textFormat": {"fontFamily": "Arial", "fontSize": 10, "bold": True, "foregroundColor": _rgb("FFFFFF")},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "WRAP",
        }
        requests.append(_format_request(_grid(sheet_id, header_row, header_row + 1, 0, column_count), header_format))
        requests.append(_row_height(sheet_id, header_row, header_row + 1, 32))
        requests.append(
            {
                "setBasicFilter": {
                    "filter": {"range": _grid(sheet_id, header_row, row_count, 0, column_count)}
                }
            }
        )

    daily_id = sheet_ids[sample_date]
    requests.extend(
        [
            _format_request(
                _grid(daily_id, 0, 1, 0, 19),
                {"backgroundColor": _rgb("17365D"), "textFormat": {"fontFamily": "Arial", "fontSize": 16, "bold": True, "foregroundColor": _rgb("FFFFFF")}, "verticalAlignment": "MIDDLE"},
            ),
            _format_request(
                _grid(daily_id, 1, 2, 0, 19),
                {"backgroundColor": _rgb("DCE6F1"), "textFormat": {"fontFamily": "Arial", "fontSize": 10, "italic": True, "foregroundColor": _rgb("334155")}, "verticalAlignment": "MIDDLE"},
            ),
            _row_height(daily_id, 0, 1, 36),
            _row_height(daily_id, 1, 2, 28),
            _row_height(daily_id, 2, 3, 32),
            _row_height(daily_id, 5, row_counts[sample_date], 48),
        ]
    )
    for column in range(0, 19, 2):
        requests.append(
            _format_request(
                _grid(daily_id, 2, 3, column, column + 1),
                {"backgroundColor": _rgb("E2E8F0"), "textFormat": {"fontFamily": "Arial", "fontSize": 9, "bold": True, "foregroundColor": _rgb("334155")}, "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP"},
            )
        )
        if column + 1 < 19:
            requests.append(
                _format_request(
                    _grid(daily_id, 2, 3, column + 1, column + 2),
                    {"backgroundColor": _rgb("F8FAFC"), "textFormat": {"fontFamily": "Arial", "fontSize": 10, "bold": True, "foregroundColor": _rgb("0F766E")}, "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"},
                )
            )

    widths = {
        sample_date: [95, 85, 130, 210, 150, 280, 70, 230, 155, 125, 110, 80, 80, 125, 300, 125, 80, 280, 120],
        "Gmail_Alerts": [140, 75, 85, 135, 210, 150, 125, 110, 80, 80, 125, 300, 150, 145, 165, 115, 180, 150],
        "Official_Jobs": [155, 135, 240, 155, 310, 175, 145, 110, 80, 80, 120, 105, 105, 155, 155, 105, 330, 130, 105, 115, 220],
        "Job_Matches": [145, 145, 175, 90, 85, 130, 300, 135, 105],
        "Runs": [145, 110, 150, 150, 120, 100, 115, 105, 110, 330],
    }
    for title, pixel_widths in widths.items():
        for index, pixels in enumerate(pixel_widths):
            requests.append(_column_width(sheet_ids[title], index, pixels))

    status_values = ["not_started", "reviewing", "applied", "rejected", "closed"]
    requests.append(_validation_request(_grid(daily_id, 5, 200, 18, 19), status_values))
    requests.append(_validation_request(_grid(sheet_ids["Gmail_Alerts"], 1, 200, 15, 16), status_values))
    requests.append(_validation_request(_grid(sheet_ids["Official_Jobs"], 1, 200, 19, 20), status_values))
    requests.append(
        _validation_request(
            _grid(sheet_ids["Job_Matches"], 1, 200, 7, 8),
            ["pending", "selected", "rejected"],
        )
    )

    fit_colors = {
        "preferred": ("DCFCE7", "166534"),
        "possible_overlap": ("FEF3C7", "92400E"),
        "outside_target": ("FEE2E2", "991B1B"),
        "unknown": ("E5E7EB", "4B5563"),
    }
    for text, colors in fit_colors.items():
        requests.append(_conditional_text(daily_id, 5, 200, 13, text, *colors))
        requests.append(_conditional_text(sheet_ids["Gmail_Alerts"], 1, 200, 10, text, *colors))
        requests.append(_conditional_text(sheet_ids["Official_Jobs"], 1, 200, 10, text, *colors))
    match_colors = {
        "exact": ("DCFCE7", "166534"),
        "review_required": ("FEF3C7", "92400E"),
        "no_official_result": ("FEE2E2", "991B1B"),
    }
    for text, colors in match_colors.items():
        requests.append(_conditional_text(daily_id, 5, 200, 15, text, *colors))
        requests.append(_conditional_text(sheet_ids["Job_Matches"], 1, 200, 5, text, *colors))

    number_formats = [
        (daily_id, 5, row_counts[sample_date], 0, 1, "DATE", "yyyy-mm-dd"),
        (sheet_ids["Official_Jobs"], 1, row_counts["Official_Jobs"], 15, 16, "DATE", "yyyy-mm-dd"),
        (sheet_ids["Official_Jobs"], 1, row_counts["Official_Jobs"], 18, 19, "DATE", "yyyy-mm-dd"),
        (sheet_ids["Job_Matches"], 1, row_counts["Job_Matches"], 8, 9, "DATE", "yyyy-mm-dd"),
        (sheet_ids["Runs"], 1, row_counts["Runs"], 1, 2, "DATE", "yyyy-mm-dd"),
    ]
    for sheet_id, start_row, end_row, start_col, end_col, kind, pattern in number_formats:
        requests.append(
            _format_request(
                _grid(sheet_id, start_row, end_row, start_col, end_col),
                {"numberFormat": {"type": kind, "pattern": pattern}},
                "userEnteredFormat.numberFormat",
            )
        )
    return requests


def create_sample_sheet(token_path, sample_date, spreadsheet_id=None):
    credentials = load_stored_credentials(token_path)
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    data = _workbook_data(sample_date)
    title = "Personal Job Hunt - Sample - {0}".format(sample_date)
    colors = {
        sample_date: "2563EB",
        "Gmail_Alerts": "64748B",
        "Official_Jobs": "16A34A",
        "Job_Matches": "D97706",
        "Runs": "7C3AED",
    }
    body = {
        "properties": {"title": title, "locale": "en_US", "timeZone": TIME_ZONE},
        "sheets": [
            {
                "properties": {
                    "title": sheet_title,
                    "gridProperties": {
                        "rowCount": 200,
                        "columnCount": len(rows[0]),
                    },
                    "tabColorStyle": {"rgbColor": _rgb(colors[sheet_title])},
                }
            }
            for sheet_title, rows in data.items()
        ],
    }
    if spreadsheet_id:
        created = sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="spreadsheetId,properties.title,sheets.properties(sheetId,title)",
        ).execute()
    else:
        created = sheets.spreadsheets().create(
            body=body,
            fields="spreadsheetId,properties.title,sheets.properties(sheetId,title)",
        ).execute()
        spreadsheet_id = created["spreadsheetId"]
    created = _migrate_sample_gmail_alerts_tab(
        sheets, spreadsheet_id, created
    )
    sheet_ids = {
        item["properties"]["title"]: item["properties"]["sheetId"]
        for item in created["sheets"]
    }
    expected_titles = list(data)
    if list(sheet_ids) != expected_titles:
        raise RuntimeError("Existing Sheet tabs did not match the expected sample structure.")
    try:
        value_updates = []
        for sheet_title, rows in data.items():
            if sheet_title == sample_date:
                summary = [
                    "Target minimum", 5, "Target maximum", 8, "Review rows", "=COUNTA(A6:A16)",
                    "Exact matches", '=COUNTIF(P6:P16,"exact")', "Preferred", '=COUNTIF(N6:N16,"preferred")',
                    "Needs review", '=COUNTIF(P6:P16,"review_required")', "No official result", '=COUNTIF(P6:P16,"no_official_result")',
                    "Sample date", sample_date, "Target", "5-8 years", "Pilot",
                ]
                value_updates.extend(
                    [
                        {"range": "'{0}'!A1".format(sheet_title), "values": [["Personal Job Hunt - Daily Review"]]},
                        {"range": "'{0}'!A2".format(sheet_title), "values": [["Six approved alert jobs with ranked official-employer candidates; review before applying."]]},
                        {"range": "'{0}'!A3:S3".format(sheet_title), "values": [summary]},
                        {"range": "'{0}'!A5:S{1}".format(sheet_title, len(rows) + 4), "values": rows},
                    ]
                )
            else:
                end_column = chr(ord("A") + len(rows[0]) - 1) if len(rows[0]) <= 26 else "U"
                value_updates.append(
                    {"range": "'{0}'!A1:{1}{2}".format(sheet_title, end_column, len(rows)), "values": rows}
                )
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": value_updates},
        ).execute()
        hyperlink_updates = _sample_hyperlink_updates(data, sample_date)
        sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": hyperlink_updates,
            },
        ).execute()
        requests = _style_requests(
            sheet_ids,
            {sheet_title: (len(rows) + 4 if sheet_title == sample_date else len(rows)) for sheet_title, rows in data.items()},
            sample_date,
        )
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()
    except Exception as exc:
        raise RuntimeError(
            "Sample Sheet creation was incomplete. Recoverable spreadsheet ID: {0}. Cause: {1}".format(
                spreadsheet_id, type(exc).__name__
            )
        ) from exc

    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields=(
            "properties.title,sheets.properties("
            "title,gridProperties.frozenRowCount,gridProperties.frozenColumnCount,"
            "gridProperties.hideGridlines)"
        ),
    ).execute()
    expected_titles = list(data)
    actual_titles = [item["properties"]["title"] for item in metadata["sheets"]]
    if actual_titles != expected_titles:
        raise RuntimeError("Created Sheet tabs did not match the expected order.")
    preview = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'{0}'!A1:S16".format(sample_date),
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values") or []
    formulas = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'{0}'!F3:N16".format(sample_date),
        valueRenderOption="FORMULA",
    ).execute().get("values") or []
    if len(preview) != 16 or preview[4][0] != "review_date":
        raise RuntimeError("Dated review tab verification failed.")
    if not any(str(value).startswith("=") for row in formulas for value in row):
        raise RuntimeError("Dated review formulas were not preserved.")
    for item in metadata["sheets"]:
        grid = item["properties"].get("gridProperties") or {}
        if not grid.get("hideGridlines") or not grid.get("frozenRowCount"):
            raise RuntimeError("Sheet formatting metadata verification failed.")
    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": "https://docs.google.com/spreadsheets/d/{0}/edit".format(spreadsheet_id),
        "title": metadata["properties"]["title"],
        "tabs": actual_titles,
        "dated_review_rows": len(preview) - 5,
        "verification": "passed",
    }


def linkify_existing_sample(token_path, sample_date, spreadsheet_id):
    """Make the sample's URL cells clickable without rewriting any other cells."""

    credentials = load_stored_credentials(token_path)
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    data = _workbook_data(sample_date)
    metadata = sheets.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="properties.title,sheets.properties(sheetId,title)",
    ).execute()
    metadata = _migrate_sample_gmail_alerts_tab(
        sheets, spreadsheet_id, metadata
    )
    expected_titles = list(data)
    actual_titles = [item["properties"]["title"] for item in metadata["sheets"]]
    if actual_titles != expected_titles:
        raise RuntimeError("Existing Sheet tabs did not match the expected sample structure.")

    hyperlink_updates = _sample_hyperlink_updates(data, sample_date)
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": hyperlink_updates},
    ).execute()
    verification = sheets.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=[update["range"] for update in hyperlink_updates],
        valueRenderOption="FORMULA",
    ).execute()
    formulas = [
        value_range.get("values", [[""]])[0][0]
        for value_range in verification.get("valueRanges") or []
    ]
    hyperlink_count = sum(
        str(formula).upper().startswith("=HYPERLINK(") for formula in formulas
    )
    if hyperlink_count != len(hyperlink_updates):
        raise RuntimeError("Not every sample URL cell retained its hyperlink formula.")

    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": "https://docs.google.com/spreadsheets/d/{0}/edit".format(
            spreadsheet_id
        ),
        "title": metadata["properties"]["title"],
        "tabs": actual_titles,
        "hyperlinks_written": hyperlink_count,
        "verification": "passed",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-19")
    parser.add_argument("--token", default=".secrets/google_token.json")
    parser.add_argument("--spreadsheet-id")
    parser.add_argument("--links-only", action="store_true")
    args = parser.parse_args()
    if args.links_only:
        if not args.spreadsheet_id:
            parser.error("--links-only requires --spreadsheet-id")
        result = linkify_existing_sample(
            Path(args.token), args.date, args.spreadsheet_id
        )
    else:
        result = create_sample_sheet(Path(args.token), args.date, args.spreadsheet_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
