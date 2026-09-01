import fitz


def extract_resume_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    try:
        pages = [page.get_text("text", sort=True) for page in doc]
    finally:
        doc.close()
    return "\n".join(pages).strip()