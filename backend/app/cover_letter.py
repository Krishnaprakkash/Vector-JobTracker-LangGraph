import json
import re
import uuid
import os
import fitz 
from .config import settings
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Job, Resume, ResumeChunk, CoverLetter
from .rate_limiter import route_call, route_call_with_tools
from .tavily_search import tavily_search_cover_letter
from .embeddings import embed_query

STOPWORDS = {
    "the", "and", "for", "with", "you", "our", "are", "will", "have", "this",
    "that", "your", "from", "who", "can", "all", "not", "but", "has", "was",
    "role", "job", "work", "team", "company", "years", "experience",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for company information to personalize a cover letter.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]

MAX_TOOL_ITERATIONS = 2
MAX_REVIEW_ITERATIONS = 3

PDF_DIR = os.path.join(settings.STORAGE_DIR, "cover_letters")
os.makedirs(PDF_DIR, exist_ok=True)


def extract_keywords(description: str, top_n: int = 15) -> list[str]:
    words = re.findall(r"\b[a-zA-Z][a-zA-Z\+\#\.]{2,}\b", description.lower())
    filtered = [w for w in words if w not in STOPWORDS]
    counts = Counter(filtered)
    return [w for w, _ in counts.most_common(top_n)]


async def _get_top_resume_chunks(db: AsyncSession, resume_id: uuid.UUID, job_description: str, k: int = 5) -> list[str]:
    query_vector = embed_query(job_description)
    stmt = (
        select(ResumeChunk.content)
        .where(ResumeChunk.resume_id == resume_id)
        .order_by(ResumeChunk.embedding.cosine_distance(query_vector))
        .limit(k)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def _research_company(company: str) -> str:
    messages = [
        {"role": "system", "content": "You research companies for cover letter personalization using web_search, then summarize findings in 2-3 sentences."},
        {"role": "user", "content": f"Research {company}: recent news, mission, or notable products."},
    ]

    for _ in range(MAX_TOOL_ITERATIONS):
        result = await route_call_with_tools("cover_letter", messages, TOOLS, est_tokens=600, max_tokens=250)
        if result["status"] != "ok":
            return ""

        message = result["message"]
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content", "")

        messages.append(message)
        for call in tool_calls:
            args = json.loads(call["function"]["arguments"])
            search_result = await tavily_search_cover_letter(args.get("query", f"{company} company"))
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": search_result or "No results found.",
            })

    return ""


async def _generate_draft(job_title: str, company: str, keywords: list[str], resume_chunks: list[str], company_research: str) -> str | None:
    prompt = (
        f"Write a concise, professional cover letter for a {job_title} position at {company}.\n"
        f"Key terms to naturally incorporate (only if genuinely relevant to the candidate's background): {', '.join(keywords[:10])}\n"
        f"Company context: {company_research or 'Not available'}\n\n"
        f"Candidate background (from resume):\n{chr(10).join(resume_chunks)}\n\n"
        f"Write 3-4 paragraphs. Do not fabricate experience not present in the candidate background."
    )
    messages = [
        {"role": "system", "content": "You are a professional cover letter writer. Never invent experience not present in the provided background."},
        {"role": "user", "content": prompt},
    ]
    result = await route_call("cover_letter", messages, est_tokens=1200, max_tokens=600)
    return result["content"] if result["status"] == "ok" else None


async def _critique_draft(draft: str, job_title: str, keywords: list[str]) -> dict | None:
    prompt = (
        f"Critique this cover letter for a {job_title} role. Check: professionalism, relevance to keywords "
        f"({', '.join(keywords[:10])}), and whether it avoids generic filler.\n\n"
        f"Letter:\n{draft}\n\n"
        f"Respond ONLY with JSON: {{\"needs_revision\": bool, \"feedback\": str}}"
    )
    messages = [
        {"role": "system", "content": "You are a critical cover letter reviewer. Be concise."},
        {"role": "user", "content": prompt},
    ]
    result = await route_call("cover_letter", messages, est_tokens=800, max_tokens=200)
    if result["status"] != "ok":
        return None
    try:
        cleaned = re.sub(r"```json|```", "", result["content"]).strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


async def generate_cover_letter(db: AsyncSession, job_id: uuid.UUID, resume_id: uuid.UUID) -> CoverLetter | None:
    job = await db.get(Job, job_id)
    resume = await db.get(Resume, resume_id)
    if not job or not resume:
        return None

    keywords = extract_keywords(job.description or "")
    resume_chunks = await _get_top_resume_chunks(db, resume_id, job.description or "")
    company_research = await _research_company(job.company)

    draft = await _generate_draft(job.title, job.company, keywords, resume_chunks, company_research)
    if draft is None:
        return None

    needs_manual_edit = False
    iteration = 1

    for _ in range(MAX_REVIEW_ITERATIONS - 1):
        critique = await _critique_draft(draft, job.title, keywords)
        if critique is None or not critique.get("needs_revision"):
            break

        iteration += 1
        prompt = (
            f"Revise this cover letter based on feedback: {critique.get('feedback', '')}\n\n"
            f"Original letter:\n{draft}"
        )
        messages = [
            {"role": "system", "content": "You are a professional cover letter writer. Never invent experience not present in the original letter's implied background."},
            {"role": "user", "content": prompt},
        ]
        result = await route_call("cover_letter", messages, est_tokens=1200, max_tokens=600)
        if result["status"] != "ok":
            needs_manual_edit = True
            break
        draft = result["content"]

    if iteration >= MAX_REVIEW_ITERATIONS:
        needs_manual_edit = True

    letter_id = uuid.uuid4()
    pdf_path = render_cover_letter_pdf(letter_id, draft)

    letter = CoverLetter(
        id=letter_id,
        job_id=job_id,
        resume_id=resume_id,
        content=draft,
        iteration_count=iteration,
        needs_manual_edit=needs_manual_edit,
        pdf_path=pdf_path,
    )
    db.add(letter)
    await db.commit()
    await db.refresh(letter)
    return letter

def render_cover_letter_pdf(letter_id: uuid.UUID, content: str) -> str:
    path = os.path.join(PDF_DIR, f"{letter_id}.pdf")
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
    page.insert_textbox(rect, content, fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()
    return path