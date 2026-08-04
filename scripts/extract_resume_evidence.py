"""Extract professional resume text from DOCX while omitting direct contact details."""

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTACT_PATTERNS = [
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)"),
    re.compile(r"\b(?:linkedin|github)\.com/", re.IGNORECASE),
]


def _paragraph_text(paragraph):
    values = []
    for node in paragraph.iter():
        if node.tag == "{{{0}}}t".format(WORD_NAMESPACE):
            values.append(node.text or "")
        elif node.tag == "{{{0}}}tab".format(WORD_NAMESPACE):
            values.append("\t")
        elif node.tag in {
            "{{{0}}}br".format(WORD_NAMESPACE),
            "{{{0}}}cr".format(WORD_NAMESPACE),
        }:
            values.append("\n")
    return "".join(values).strip()


def extract_professional_text(docx_path, redacted_names=()):
    with zipfile.ZipFile(str(docx_path)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    paragraphs = []
    omitted = 0
    names = {name.casefold().strip() for name in redacted_names if name.strip()}
    for paragraph in root.iter("{{{0}}}p".format(WORD_NAMESPACE)):
        text = _paragraph_text(paragraph)
        if not text:
            continue
        normalized = text.casefold().strip()
        if normalized in names or any(pattern.search(text) for pattern in CONTACT_PATTERNS):
            omitted += 1
            continue
        paragraphs.append(text)
    return paragraphs, omitted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_docx", type=Path)
    parser.add_argument("output_text", type=Path)
    parser.add_argument("--redact-name", action="append", default=[])
    args = parser.parse_args()

    paragraphs, omitted = extract_professional_text(
        args.input_docx, redacted_names=args.redact_name
    )
    args.output_text.parent.mkdir(parents=True, exist_ok=True)
    args.output_text.write_text("\n".join(paragraphs) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "paragraphs_retained": len(paragraphs),
                "contact_lines_omitted": omitted,
                "output_bytes": args.output_text.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    main()
