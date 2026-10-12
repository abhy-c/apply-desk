from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def extract_docx_tables(path: Path) -> list[list[list[str]]]:
    if path.stat().st_size>100000000: raise ValueError('Word import exceeds 100 MB')
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('word/document.xml').file_size>20000000: raise ValueError('Word document XML exceeds 20 MB')
        xml = archive.read("word/document.xml")

    root = ET.fromstring(xml)
    tables: list[list[list[str]]] = []
    for table in root.findall(".//w:tbl", WORD_NS):
        rows: list[list[str]] = []
        for tr in table.findall("./w:tr", WORD_NS):
            row = []
            for tc in tr.findall("./w:tc", WORD_NS):
                texts = [node.text or "" for node in tc.findall(".//w:t", WORD_NS)]
                row.append(clean_cell("".join(texts)))
            if any(row):
                rows.append(row)
        if rows:
            tables.append(rows)
    return tables


def recruiter_rows_from_docx(path: Path) -> list[dict[str, str]]:
    tables = extract_docx_tables(path)
    if not tables:
        return []

    rows = tables[0]
    header = [cell.strip().lower() for cell in rows[0]]
    required = {"name", "title", "location"}
    if not required.issubset(set(header)):
        raise ValueError(f"Expected recruiter table with columns {sorted(required)}; got {header}")

    indexes = {name: header.index(name) for name in required}
    recruiters = []
    for idx, row in enumerate(rows[1:], start=1):
        name = row[indexes["name"]].strip()
        if not name:
            continue
        title = row[indexes["title"]].strip()
        location = row[indexes["location"]].strip()
        recruiters.append(
            {
                "recruiter_id": f"external_recruiter_{idx:03d}",
                "name": name,
                "title": title,
                "location": location,
                "company": "",
                "profile_url": "",
                "email": "",
                "source": path.name,
                "notes": "",
            }
        )
    return recruiters


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

