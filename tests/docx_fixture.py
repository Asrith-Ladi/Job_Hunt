"""Small synthetic DOCX fixture used by resume tests."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""


def create_resume_docx(path: Path, *, contact_in_skills: bool = False) -> Path:
    values = [
        "Candidate Name",
        "candidate@example.com | +91 99999 99999 | linkedin.com/in/candidate",
        "Machine Learning Engineer",
        "PROFESSIONAL SUMMARY",
        (
            "Machine Learning Engineer with 5+ years of experience building production "
            "AI systems in Python, AWS, Docker, and Kubernetes."
        ),
        "TECHNICAL SKILLS",
        "Languages: Python, SQL",
        "Cloud: AWS, Docker, Kubernetes",
        "candidate@example.com" if contact_in_skills else "AI: RAG, LangGraph, MCP",
        "WORK EXPERIENCE",
        "Machine Learning Engineer    Mar 2023 - Present",
        "Example Company | Hyderabad, India",
        "Built production machine-learning services using Python and AWS.",
        "Automated model validation, reducing manual testing effort by 80%.",
        "Python Developer    Sep 2020 - Mar 2023",
        "Example Company | Hyderabad, India",
        "Automated cloud health checks using Python.",
        "PERSONAL PROJECTS",
        "Agentic AI Assistant",
        "Built a RAG application using LangGraph.",
        "EDUCATION",
        "M.Tech in Software Systems    Graduated 2024",
    ]
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(value)}</w:t></w:r></w:p>" for value in values
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/></w:sectPr></w:body>"
        "</w:document>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", document)
    return path
