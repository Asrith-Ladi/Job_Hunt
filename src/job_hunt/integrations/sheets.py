"""Small-volume Google Sheets store with idempotent, review-safe job upserts."""


JOB_COLUMNS = [
    "job_record_id",
    "owner_id",
    "alert_source",
    "gmail_message_id",
    "email_subject",
    "email_received_at",
    "company",
    "title",
    "location",
    "years_of_experience",
    "alert_posted_at",
    "source_url",
    "official_url",
    "first_seen_at",
    "last_seen_at",
    "parse_confidence",
    "parse_status",
    "company_match",
    "application_status",
    "notes",
    "evidence_message_ids",
    "experience_min_years",
    "experience_max_years",
    "experience_fit",
    "experience_source",
]

LEGACY_COLUMN_RENAMES = {"experience_text": "years_of_experience"}
GMAIL_ALERTS_SHEET = "Gmail_Alerts"
LEGACY_GMAIL_ALERTS_SHEET = "Jobs"

FIRST_OBSERVED_COLUMNS = {
    "gmail_message_id",
    "email_subject",
    "email_received_at",
    "first_seen_at",
}
USER_MAINTAINED_COLUMNS = {"application_status", "notes"}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

RUN_COLUMNS = [
    "run_id",
    "started_at",
    "finished_at",
    "status",
    "messages_read",
    "messages_supported",
    "jobs_parsed",
    "jobs_after_deduplication",
    "jobs_filtered_out",
    "rows_inserted",
    "rows_updated",
    "parsing_warnings",
    "dry_run",
]


def _require_google_api():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API client is not installed. Use Python 3.12 and `pip install -e .`."
        ) from exc
    return build


def _column_letter(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def hyperlink_formula(value, label=None):
    """Return a safe Google Sheets hyperlink formula with a visible label."""

    url = str(value or "").strip()
    if not url.lower().startswith(("https://", "http://")):
        return None
    visible = url if label in (None, "") else str(label).strip()
    escaped_url = url.replace('"', '""')
    escaped_label = visible.replace('"', '""')
    return '=HYPERLINK("{0}","{1}")'.format(escaped_url, escaped_label)


def rich_text_link_runs(text, links):
    """Build Sheets API rich-text runs for non-overlapping linked substrings.

    ``links`` contains ``(start, end, url)`` tuples whose indexes use Python
    string offsets. Google Sheets expects UTF-16 offsets, so the conversion is
    performed here before the request is sent.
    """

    text = str(text or "")
    spans = []
    for start, end, url in links:
        target = str(url or "").strip()
        if not target.lower().startswith(("https://", "http://")):
            continue
        start = int(start)
        end = int(end)
        if start < 0 or end <= start or end > len(text):
            raise ValueError("Rich-text link span is outside the cell text.")
        spans.append((start, end, target))
    spans.sort(key=lambda item: (item[0], item[1]))
    for previous, current in zip(spans, spans[1:]):
        if current[0] < previous[1]:
            raise ValueError("Rich-text link spans must not overlap.")
    if not spans:
        return []

    def utf16_index(position):
        return len(text[:position].encode("utf-16-le")) // 2

    runs = []
    if spans[0][0] > 0:
        runs.append({"startIndex": 0, "format": {}})
    for index, (start, end, target) in enumerate(spans):
        runs.append(
            {
                "startIndex": utf16_index(start),
                "format": {
                    "link": {"uri": target},
                    "foregroundColor": {"red": 0.0667, "green": 0.3333, "blue": 0.8},
                    "underline": True,
                },
            }
        )
        next_start = spans[index + 1][0] if index + 1 < len(spans) else None
        if end < len(text) and (next_start is None or next_start > end):
            runs.append({"startIndex": utf16_index(end), "format": {}})
    return runs


def job_url_formula_updates(row_number, row):
    """Build targeted USER_ENTERED updates for one Gmail_Alerts row."""

    updates = []
    for column_name in ("source_url", "official_url"):
        column_index = JOB_COLUMNS.index(column_name)
        value = row[column_index] if column_index < len(row) else ""
        formula = hyperlink_formula(value)
        if formula:
            updates.append(
                {
                    "range": "{0}!{1}{2}".format(
                        GMAIL_ALERTS_SHEET,
                        _column_letter(column_index + 1), row_number
                    ),
                    "values": [[formula]],
                }
            )
    return updates


def updated_range_start_row(updated_range):
    """Extract the first row number from a Sheets API updatedRange value."""

    start_cell = str(updated_range or "").rsplit("!", 1)[-1].split(":", 1)[0]
    digits = "".join(character for character in start_cell if character.isdigit())
    return int(digits) if digits else None


def _row_values(row):
    padded = list(row) + [""] * max(0, len(JOB_COLUMNS) - len(row))
    return dict(zip(JOB_COLUMNS, padded))


def _merge_message_ids(existing, incoming):
    values = []
    for raw in (existing, incoming):
        values.extend(item.strip() for item in str(raw or "").split(",") if item.strip())
    return ",".join(dict.fromkeys(values))


def merge_existing_job_row(existing_row, incoming_row):
    """Merge a rerun without erasing first-seen evidence or user-maintained cells."""

    existing = _row_values(existing_row)
    incoming = _row_values(incoming_row)
    merged = dict(incoming)

    # A partial later alert should not erase a value learned on an earlier run.
    for column in JOB_COLUMNS:
        if merged.get(column) in (None, "") and existing.get(column) not in (None, ""):
            merged[column] = existing[column]

    for column in FIRST_OBSERVED_COLUMNS | USER_MAINTAINED_COLUMNS:
        if existing.get(column) not in (None, ""):
            merged[column] = existing[column]

    merged["evidence_message_ids"] = _merge_message_ids(
        existing.get("evidence_message_ids"),
        incoming.get("evidence_message_ids"),
    )
    merged["last_seen_at"] = max(
        str(existing.get("last_seen_at") or ""),
        str(incoming.get("last_seen_at") or ""),
    )

    existing_confidence = str(existing.get("parse_confidence") or "")
    incoming_confidence = str(incoming.get("parse_confidence") or "")
    if CONFIDENCE_ORDER.get(existing_confidence, -1) > CONFIDENCE_ORDER.get(
        incoming_confidence, -1
    ):
        merged["parse_confidence"] = existing_confidence

    return [
        merged.get(column) if merged.get(column) is not None else ""
        for column in JOB_COLUMNS
    ]


class GoogleSheetsStore:
    def __init__(self, sheets_service, spreadsheet_id=None):
        self.sheets = sheets_service
        self.spreadsheet_id = spreadsheet_id

    @classmethod
    def from_credentials(cls, credentials, spreadsheet_id=None):
        build = _require_google_api()
        return cls(
            build("sheets", "v4", credentials=credentials, cache_discovery=False),
            spreadsheet_id=spreadsheet_id,
        )

    def _ensure_spreadsheet(self):
        if not self.spreadsheet_id:
            body = {
                "properties": {"title": "Personal Job Hunt"},
                "sheets": [
                    {"properties": {"title": GMAIL_ALERTS_SHEET}},
                    {"properties": {"title": "Runs"}},
                ],
            }
            created = self.sheets.spreadsheets().create(
                body=body, fields="spreadsheetId"
            ).execute()
            self.spreadsheet_id = created["spreadsheetId"]
        else:
            metadata = self.sheets.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties(sheetId,title)",
            ).execute()
            sheet_properties = {
                sheet["properties"]["title"]: sheet["properties"]
                for sheet in metadata.get("sheets") or []
            }
            existing = set(sheet_properties)
            requests = []
            if (
                GMAIL_ALERTS_SHEET not in existing
                and LEGACY_GMAIL_ALERTS_SHEET in existing
            ):
                requests.append(
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_properties[LEGACY_GMAIL_ALERTS_SHEET][
                                    "sheetId"
                                ],
                                "title": GMAIL_ALERTS_SHEET,
                            },
                            "fields": "title",
                        }
                    }
                )
                existing.remove(LEGACY_GMAIL_ALERTS_SHEET)
                existing.add(GMAIL_ALERTS_SHEET)
            requests.extend(
                {"addSheet": {"properties": {"title": title}}}
                for title in (GMAIL_ALERTS_SHEET, "Runs")
                if title not in existing
            )
            if requests:
                self.sheets.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id, body={"requests": requests}
                ).execute()
        self._ensure_headers(GMAIL_ALERTS_SHEET, JOB_COLUMNS)
        self._ensure_headers("Runs", RUN_COLUMNS)
        return self.spreadsheet_id

    def _ensure_headers(self, sheet_name, columns):
        response = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range="{0}!1:1".format(sheet_name),
        ).execute()
        current = (response.get("values") or [[]])[0]
        normalized_current = [LEGACY_COLUMN_RENAMES.get(column, column) for column in current]
        if normalized_current == columns:
            if current != columns:
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range="{0}!A1".format(sheet_name),
                    valueInputOption="RAW",
                    body={"values": [columns]},
                ).execute()
            return
        if current and columns[: len(normalized_current)] == normalized_current:
            self.sheets.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range="{0}!A1".format(sheet_name),
                valueInputOption="RAW",
                body={"values": [columns]},
            ).execute()
            return
        if current and current != columns:
            raise RuntimeError(
                "{0} header does not match the expected core schema.".format(sheet_name)
            )
        self.sheets.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range="{0}!A1".format(sheet_name),
            valueInputOption="RAW",
            body={"values": [columns]},
        ).execute()

    def upsert_jobs(self, jobs):
        self._ensure_spreadsheet()
        end_column = _column_letter(len(JOB_COLUMNS))
        response = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range="{0}!A2:{1}".format(GMAIL_ALERTS_SHEET, end_column),
        ).execute()
        rows = response.get("values") or []
        row_by_id = {row[0]: (index + 2, row) for index, row in enumerate(rows) if row}

        updates = []
        inserts = []
        link_updates = []
        for job in jobs:
            values = job.to_dict()
            row = [values.get(column) or "" for column in JOB_COLUMNS]
            existing = row_by_id.get(job.job_record_id)
            if existing:
                existing_row, existing_values = existing
                row = merge_existing_job_row(existing_values, row)
                updates.append(
                    {
                        "range": "{0}!A{1}:{2}{1}".format(
                            GMAIL_ALERTS_SHEET, existing_row, end_column
                        ),
                        "values": [row],
                    }
                )
                link_updates.extend(job_url_formula_updates(existing_row, row))
            else:
                inserts.append(row)

        if updates:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()
        if inserts:
            append_result = self.sheets.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="{0}!A:{1}".format(GMAIL_ALERTS_SHEET, end_column),
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": inserts},
            ).execute()
            first_inserted_row = updated_range_start_row(
                (append_result.get("updates") or {}).get("updatedRange")
            )
            if first_inserted_row is None:
                first_inserted_row = len(rows) + 2
            for offset, row in enumerate(inserts):
                link_updates.extend(
                    job_url_formula_updates(first_inserted_row + offset, row)
                )
        if link_updates:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": link_updates},
            ).execute()
        return len(inserts), len(updates)

    def append_run(self, summary):
        self._ensure_spreadsheet()
        values = summary.to_dict()
        row = [
            values.get(column) if values.get(column) is not None else ""
            for column in RUN_COLUMNS
        ]
        self.sheets.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Runs!A:M",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
