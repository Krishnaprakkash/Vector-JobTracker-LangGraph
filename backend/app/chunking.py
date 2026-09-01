import re

SECTION_HEADERS = {
    "skills": ["skills", "technical skills", "core competencies"],
    "experience": ["experience", "work experience", "employment history", "professional experience"],
    "education": ["education", "academic background"],
}

HEADER_PATTERN = re.compile(
    r"^\s*(" + "|".join(h for group in SECTION_HEADERS.values() for h in group) + r")\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _label_for_header(header: str) -> str:
    header_lower = header.strip().lower()
    for label, variants in SECTION_HEADERS.items():
        if header_lower in variants:
            return label
    return "other"


def chunk_resume_text(text: str) -> list[dict]:
    """Split resume text into semantic section chunks.
    Returns [{"section": str, "content": str}]
    """
    matches = list(HEADER_PATTERN.finditer(text))
    if not matches:
        return [{"section": "other", "content": text.strip()}] if text.strip() else []

    chunks = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            chunks.append({"section": "other", "content": preamble})

    for i, match in enumerate(matches):
        section_label = _label_for_header(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            chunks.append({"section": section_label, "content": content})

    return chunks