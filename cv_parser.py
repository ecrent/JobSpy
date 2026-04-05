"""Parse a .docx CV into named sections for tailoring."""

SECTION_HEADINGS = [
    "PROFESSIONAL SUMMARY",
    "EDUCATION",
    "EXPERIENCE",
    "PROJECTS",
    "TECHNICAL SKILLS",
]

SECTION_HEADINGS_UPPER = {h.upper() for h in SECTION_HEADINGS}
MUTABLE_SECTIONS = {"PROFESSIONAL SUMMARY", "PROJECTS", "TECHNICAL SKILLS"}


def find_sections(doc):
    """Find section boundaries by scanning for known heading text.

    Returns dict mapping section name to:
        heading_idx: paragraph index of the heading
        start: first content paragraph index
        end: last content paragraph index
    """
    sections = {}
    heading_order = []

    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip().upper()
        if text in SECTION_HEADINGS_UPPER:
            sections[text] = {"heading_idx": i}
            heading_order.append(text)

    for j, name in enumerate(heading_order):
        start = sections[name]["heading_idx"] + 1
        if j + 1 < len(heading_order):
            end = sections[heading_order[j + 1]]["heading_idx"] - 1
        else:
            end = len(doc.paragraphs) - 1
        sections[name]["start"] = start
        sections[name]["end"] = end

    return sections


def extract_section_text(doc, section_info):
    """Extract non-empty paragraph text from a section."""
    texts = []
    for i in range(section_info["start"], section_info["end"] + 1):
        text = doc.paragraphs[i].text.strip()
        if text:
            texts.append(text)
    return texts
