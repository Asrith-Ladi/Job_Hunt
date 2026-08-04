"""Read the public company-source tables from the canonical Excel registry."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries

from job_hunt.discovery.detection import DetectionResult, detect_source
from job_hunt.discovery.models import SourceConfig, clean_text


CATEGORY_SHEETS = (
    "MNC",
    "Product Companies",
    "Startups",
    "Mid-Sized Companies",
    "Other Companies",
)


@dataclass(frozen=True)
class CompanyRegistryEntry:
    company_id: str
    company: str
    category: str
    sector: str
    priority: str
    careers_url: str
    portal_url: str
    source_type_label: str
    source_identifier: str
    public_feed_url: str
    api_key_required: str
    india_jobs: str
    active: str
    last_checked: str
    verification_status: str
    fallback: str
    notes: str
    detection: DetectionResult

    @property
    def adapter_ready(self) -> bool:
        return self.detection.adapter_ready and bool(self.detection.identifier)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["adapter_ready"] = self.adapter_ready
        return value

    def to_source_config(self) -> SourceConfig:
        return SourceConfig(
            company=self.company,
            provider=self.detection.provider,
            identifier=self.detection.identifier,
            category=self.category,
            careers_url=self.careers_url,
            portal_url=self.portal_url,
            public_feed_url=self.public_feed_url,
            region=self.detection.region,
            company_id=self.company_id,
            fallback=self.fallback or self.detection.fallback,
            source_type_label=self.source_type_label,
        )


def _company_id(company: str, category: str) -> str:
    identity = f"{clean_text(company).casefold()}|{clean_text(category).casefold()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _text(row: dict[str, Any], key: str) -> str:
    return clean_text(row.get(key))


def load_company_registry(path: Path) -> list[CompanyRegistryEntry]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("The canonical company registry workbook was not found.")
    workbook = load_workbook(path, data_only=True, read_only=False)
    entries: list[CompanyRegistryEntry] = []
    seen: set[str] = set()
    for sheet_name in CATEGORY_SHEETS:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Registry sheet is missing: {sheet_name}")
        sheet = workbook[sheet_name]
        table_names = list(sheet.tables.keys())
        if len(table_names) != 1:
            raise ValueError(f"Registry sheet must contain one table: {sheet_name}")
        table = sheet.tables[table_names[0]]
        min_col, min_row, max_col, max_row = range_boundaries(table.ref)
        headers = [sheet.cell(min_row, column).value for column in range(min_col, max_col + 1)]
        for row_number in range(min_row + 1, max_row + 1):
            row = dict(
                zip(
                    headers,
                    [
                        sheet.cell(row_number, column).value
                        for column in range(min_col, max_col + 1)
                    ],
                )
            )
            company = _text(row, "Company")
            if not company:
                continue
            normalized = company.casefold()
            if normalized in seen:
                raise ValueError(f"Company appears in more than one registry category: {company}")
            seen.add(normalized)
            careers_url = _text(row, "Official Careers Page")
            portal_url = _text(row, "Direct Job Portal")
            feed_url = _text(row, "Public Jobs API / Feed")
            source_type = _text(row, "ATS / Source Type")
            identifier = _text(row, "Source Identifier")
            detection = detect_source(
                source_type_label=source_type,
                identifier=identifier,
                urls=(portal_url, careers_url, feed_url),
            )
            entries.append(
                CompanyRegistryEntry(
                    company_id=_company_id(company, sheet_name),
                    company=company,
                    category=sheet_name,
                    sector=_text(row, "Sector"),
                    priority=_text(row, "Priority"),
                    careers_url=careers_url,
                    portal_url=portal_url,
                    source_type_label=source_type,
                    source_identifier=identifier,
                    public_feed_url=feed_url,
                    api_key_required=_text(row, "API Key Required"),
                    india_jobs=_text(row, "India Jobs"),
                    active=_text(row, "Active"),
                    last_checked=_text(row, "Last Checked"),
                    verification_status=_text(row, "Verification Status"),
                    fallback=_text(row, "Fallback"),
                    notes=_text(row, "Notes"),
                    detection=detection,
                )
            )
    if len(entries) != 210:
        raise ValueError(f"Expected 210 unique registry companies, found {len(entries)}.")
    return entries
