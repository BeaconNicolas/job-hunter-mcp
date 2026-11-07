"""Render a CV (the structure of profile/cv.yaml) to a Word document.

The layout is one column with no tables, text boxes or images, so applicant
tracking systems (ATS) can read it. Items with `include: false` are left out.

    job-hunter-render profile/cv.yaml output/cv.docx
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TEXT = RGBColor(0x1F, 0x29, 0x33)
ACCENT = RGBColor(0x1F, 0x4E, 0x79)
MUTED = RGBColor(0x52, 0x60, 0x6D)
FONT = "Calibri"
PAGE_MARGIN = Cm(1.7)
TEXT_WIDTH = Cm(21.0) - 2 * PAGE_MARGIN  # A4


def format_month(value: Any) -> str:
    """'2024-01' -> 'Jan 2024', 'present' -> 'Present'."""
    text = str(value).strip()
    if text.lower() == "present":
        return "Present"
    try:
        year, month = text.split("-")[:2]
        return date(int(year), int(month), 1).strftime("%b %Y")
    except ValueError:
        return text


def period(item: dict) -> str:
    if "period" in item:
        return str(item["period"]).replace(" - ", " – ")
    return f"{format_month(item['start'])} – {format_month(item['end'])}"


def included(items: list[dict] | None) -> list[dict]:
    return [i for i in (items or []) if i.get("include", True)]


def bullet_text(bullet: Any) -> str:
    return bullet["text"] if isinstance(bullet, dict) else str(bullet)


class CvDocument:
    def __init__(self) -> None:
        self.doc = Document()
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        section.left_margin = section.right_margin = PAGE_MARGIN
        section.top_margin = section.bottom_margin = Cm(1.5)

        normal = self.doc.styles["Normal"]
        normal.font.name = FONT
        normal.font.size = Pt(10.5)
        normal.font.color.rgb = TEXT
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        normal.paragraph_format.space_after = Pt(0)
        normal.paragraph_format.line_spacing = 1.08

        bullets = self.doc.styles["List Bullet"]
        bullets.font.name = FONT
        bullets.font.size = Pt(10.5)
        bullets.paragraph_format.space_after = Pt(1.5)
        bullets.paragraph_format.left_indent = Cm(0.55)
        bullets.paragraph_format.first_line_indent = Cm(-0.4)

        if "CV Heading" not in [s.name for s in self.doc.styles]:
            heading = self.doc.styles.add_style("CV Heading", WD_STYLE_TYPE.PARAGRAPH)
            heading.base_style = normal
            heading.font.size = Pt(11)
            heading.font.bold = True
            heading.font.color.rgb = ACCENT
            heading.paragraph_format.space_before = Pt(10)
            heading.paragraph_format.space_after = Pt(4)
            heading.paragraph_format.keep_with_next = True

    # -- building blocks -------------------------------------------------
    def paragraph(
        self,
        text: str = "",
        *,
        size: float | None = None,
        bold=False,
        italic=False,
        color: RGBColor | None = None,
        space_after: float = 0,
    ):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        if text:
            run = p.add_run(text)
            run.bold, run.italic = bold, italic
            if size:
                run.font.size = Pt(size)
            if color is not None:
                run.font.color.rgb = color
        return p

    def heading(self, text: str) -> None:
        p = self.doc.add_paragraph(text.upper(), style="CV Heading")
        # Thin line under the heading.
        p_pr = p._p.get_or_add_pPr()
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for key, value in {"w:val": "single", "w:sz": "6", "w:space": "1", "w:color": "1F4E79"}.items():
            bottom.set(qn(key), value)
        border.append(bottom)
        p_pr.append(border)

    def line_with_date(
        self,
        left: str,
        right: str,
        *,
        left_bold=True,
        left_italic=False,
        space_before: float = 0,
        keep_with_next=True,
    ):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.keep_with_next = keep_with_next
        p.paragraph_format.tab_stops.add_tab_stop(TEXT_WIDTH, WD_TAB_ALIGNMENT.RIGHT)
        run = p.add_run(left)
        run.bold, run.italic = left_bold, left_italic
        if right:
            date_run = p.add_run("\t" + right)
            date_run.font.color.rgb = MUTED
            date_run.font.size = Pt(10)
        return p

    def bullet(self, text: str) -> None:
        self.doc.add_paragraph(text, style="List Bullet")

    def hyperlink(self, paragraph, text: str, url: str) -> None:
        rel_id = paragraph.part.relate_to(
            url,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            is_external=True,
        )
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), rel_id)
        run = OxmlElement("w:r")
        props = OxmlElement("w:rPr")
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "1F4E79")
        props.append(color)
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), "19")
        props.append(size)
        run.append(props)
        node = OxmlElement("w:t")
        node.text = text
        run.append(node)
        link.append(run)
        paragraph._p.append(link)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.core_properties.title = "CV"
        self.doc.save(str(path))


def render_docx(cv: dict, path: str | Path) -> Path:
    path = Path(path)
    d = CvDocument()
    basics = cv["basics"]

    # Header
    d.paragraph(basics["name"], size=20, bold=True, color=ACCENT)
    if basics.get("headline"):
        d.paragraph(basics["headline"], size=11.5, color=TEXT, space_after=2)
    # Line 1: location, email, phone. Line 2: links (kept apart so long URLs don't wrap mid-link).
    details = [p for p in (basics.get("location"), basics.get("email"), basics.get("phone")) if p]
    if details:
        run = d.paragraph(space_after=1).add_run("  |  ".join(details))
        run.font.size = Pt(9.5)
        run.font.color.rgb = MUTED
    links = basics.get("links", [])
    if links:
        line = d.paragraph(space_after=2)
        for n, link in enumerate(links):
            if n:
                sep = line.add_run("  |  ")
                sep.font.size = Pt(9.5)
                sep.font.color.rgb = MUTED
            shown = link["url"].removeprefix("https://").removeprefix("www.").rstrip("/")
            d.hyperlink(line, shown, link["url"])

    if cv.get("summary"):
        d.heading("Profile")
        d.paragraph(" ".join(str(cv["summary"]).split()))

    if cv.get("skills"):
        d.heading("Skills")
        for group in included(cv["skills"]):
            p = d.paragraph(space_after=1.5)
            p.add_run(f"{group['group']}: ").bold = True
            p.add_run(", ".join(group["items"]))

    jobs = included(cv.get("experience"))
    if jobs:
        d.heading("Experience")
        for n, job in enumerate(jobs):
            org = job["org"] + (f", {job['location']}" if job.get("location") else "")
            d.line_with_date(org, period(job), space_before=0 if n == 0 else 6)
            for role in included(job.get("roles")):
                d.line_with_date(
                    role["title"], period(role), left_bold=True, left_italic=True, space_before=3
                )
                for b in included(
                    [b if isinstance(b, dict) else {"text": b} for b in role.get("bullets", [])]
                ):
                    d.bullet(bullet_text(b))

    projects = included(cv.get("projects"))
    if projects:
        d.heading("Projects")
        for n, project in enumerate(projects):
            d.line_with_date(project["name"], str(project.get("year", "")), space_before=0 if n == 0 else 4)
            if project.get("url"):
                p = d.paragraph()
                p.paragraph_format.keep_with_next = True
                d.hyperlink(p, project["url"].removeprefix("https://"), project["url"])
            for b in project.get("bullets", []):
                d.bullet(bullet_text(b))

    if cv.get("education"):
        d.heading("Education")
        for item in included(cv["education"]):
            d.line_with_date(
                item["title"],
                period(item) if "period" in item or "start" in item else "",
                keep_with_next=False,
                space_before=1,
            )
            d.paragraph(item["org"], color=MUTED, space_after=0 if item.get("note") else 2)
            if item.get("note"):
                d.paragraph(item["note"], color=MUTED, space_after=2)

    if cv.get("certifications"):
        d.heading("Certifications")
        for cert in included(cv["certifications"]):
            extra = ", ".join(str(x) for x in (cert.get("org"), cert.get("year")) if x)
            d.bullet(cert["title"] + (f" – {extra}" if extra else ""))

    d.save(path)
    return path


def load_cv(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m job_hunter.render <cv.yaml> <output.docx>", file=sys.stderr)
        return 2
    out = render_docx(load_cv(argv[1]), argv[2])
    print(f"Wrote {out}")
    return 0


def cli() -> None:
    raise SystemExit(main(sys.argv))


if __name__ == "__main__":
    cli()
