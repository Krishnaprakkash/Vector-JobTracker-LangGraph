import hashlib
import json
import re
import uuid

import httpx
from sqlalchemy import select

from .db import AsyncSessionLocal
from .models import Job, Profile, ProfileItem, Resume, User
from .rate_limiter import route_call
from .resumes import _resume_path
from .notion_rate_limiter import throttle_notion

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"

SECTIONS = ["skills", "experience", "education", "projects", "certifications"]
MAX_ATTEMPTS = 3

GENERATE_SYSTEM_PROMPT = (
    "You are a resume optimizer. You will be given a candidate's Profile (factual items grouped by section) "
    "and a target Job Description. Rewrite the resume to be ATS-optimized for this job.\n\n"
    "STRICT RULE: only rephrase, reorder, or emphasize skills/experience/education/projects/certifications "
    "that are explicitly present in the Profile. NEVER invent or infer skills, tools, titles, or experience "
    "not present in the Profile, even if the job requires them.\n\n"
    "Respond ONLY with JSON: {\"skills\": str, \"experience\": str, \"education\": str, \"projects\": str, "
    "\"certifications\": str}. Each section is the rewritten resume text for that section "
    "(empty string if the Profile has nothing for it). No prose, no markdown fences."
)

REVIEW_SYSTEM_PROMPT = (
    "You are a resume reviewer. Given a job description and a draft resume, judge whether the resume is "
    "well-targeted for this job: does it surface the right keywords for ATS screening, match current hiring "
    "conventions, and emphasize the most job-relevant content? Do NOT check factual accuracy, only fit and framing.\n\n"
    "Respond ONLY with JSON: {\"pass\": bool, \"feedback\": str}. \"feedback\" is empty if pass is true, "
    "otherwise 1-3 sentences of specific, actionable revision instructions. No prose, no markdown fences."
)

VERIFY_SYSTEM_PROMPT = (
    "You are a fact-checker. Given a candidate's actual profile items for one resume section, and a rewritten "
    "version of that section, identify any claim in the rewritten text that is NOT supported by the profile "
    "items — fabricated skills, invented metrics, exaggerated scope, etc.\n\n"
    "Respond ONLY with JSON: {\"supported\": bool, \"unsupported_claims\": [str]}. No prose, no markdown fences."
)

FILENAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def _strip_json_fences(text: str) -> str:
    return re.sub(r"```json|```", "", text).strip()


def _safe(s: str) -> str:
    return FILENAME_UNSAFE.sub("_", s or "").strip("_")[:40] or "x"


async def _fetch_profile_items_by_section(db, user_id) -> dict[str, list[str]]:
    result = await db.execute(select(Profile.id).where(Profile.user_id == user_id))
    profile_id = result.scalar_one_or_none()
    if not profile_id:
        return {}

    result = await db.execute(
        select(ProfileItem.section, ProfileItem.content).where(ProfileItem.profile_id == profile_id)
    )
    grouped: dict[str, list[str]] = {}
    for section, content in result.all():
        grouped.setdefault(section.value, []).append(content)
    return grouped


def _build_profile_text(grouped: dict[str, list[str]]) -> str:
    lines = []
    for section in SECTIONS:
        items = grouped.get(section, [])
        if not items:
            continue
        lines.append(f"## {section.title()}")
        lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


async def _call_generate(profile_text: str, job_title: str, company: str, description: str, feedback: list[str]) -> dict | None:
    prompt = (
        f"Job Title: {job_title}\nCompany: {company}\nJob Description: {(description or '')[:3000]}\n\n"
        f"Candidate Profile:\n{profile_text[:4000]}"
    )
    if feedback:
        prompt += "\n\nRevision instructions from previous attempt:\n" + "\n".join(f"- {f}" for f in feedback)

    messages = [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    result = await route_call("resume_optimize", messages, est_tokens=3000, max_tokens=1800)
    if result["status"] != "ok":
        return None
    try:
        return json.loads(_strip_json_fences(result["content"]))
    except json.JSONDecodeError:
        return None


async def _call_review(draft: dict, job_title: str, company: str, description: str) -> dict:
    draft_text = "\n\n".join(f"{s.upper()}:\n{draft.get(s, '')}" for s in SECTIONS if draft.get(s))
    prompt = f"Job Title: {job_title}\nCompany: {company}\nJob Description: {(description or '')[:3000]}\n\nDraft Resume:\n{draft_text[:4000]}"
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    result = await route_call("resume_review", messages, est_tokens=1500, max_tokens=400)
    if result["status"] != "ok":
        return {"pass": True, "feedback": ""}  # fail-open: infra failure doesn't block delivery
    try:
        data = json.loads(_strip_json_fences(result["content"]))
        return {"pass": bool(data.get("pass", True)), "feedback": str(data.get("feedback", ""))}
    except json.JSONDecodeError:
        return {"pass": True, "feedback": ""}


async def _call_verify_section(section: str, profile_items: list[str], section_text: str) -> dict:
    if not section_text.strip():
        return {"supported": True, "unsupported_claims": []}  # nothing generated, nothing to check

    profile_text = "\n".join(f"- {i}" for i in profile_items) if profile_items else "(no items in this section)"
    prompt = f"Section: {section}\n\nProfile items:\n{profile_text}\n\nRewritten section:\n{section_text}"
    messages = [
        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    result = await route_call("resume_verify", messages, est_tokens=800, max_tokens=300)
    if result["status"] != "ok":
        return {"supported": True, "unsupported_claims": []}  # fail-open
    try:
        data = json.loads(_strip_json_fences(result["content"]))
        return {"supported": bool(data.get("supported", True)), "unsupported_claims": list(data.get("unsupported_claims", []))}
    except (json.JSONDecodeError, TypeError):
        return {"supported": True, "unsupported_claims": []}


async def _generate_verified_resume(grouped: dict[str, list[str]], job_title: str, company: str, description: str) -> dict | None:
    profile_text = _build_profile_text(grouped)
    if not profile_text:
        return None

    feedback: list[str] = []
    draft = None

    for _attempt in range(MAX_ATTEMPTS):
        draft = await _call_generate(profile_text, job_title, company, description, feedback)
        if draft is None:
            return None  # Groq/parse failure on generation itself — accepted gap, no partial resume

        review = await _call_review(draft, job_title, company, description)

        unsupported_by_section = {}
        for section in SECTIONS:
            section_text = (draft.get(section) or "").strip()
            if not section_text:
                continue
            verify = await _call_verify_section(section, grouped.get(section, []), section_text)
            if not verify["supported"]:
                unsupported_by_section[section] = verify["unsupported_claims"]

        if review["pass"] and not unsupported_by_section:
            return draft  # both gates clear

        feedback = []
        if not review["pass"] and review["feedback"]:
            feedback.append(f"Reviewer: {review['feedback']}")
        for section, claims in unsupported_by_section.items():
            feedback.append(f"Remove these unsupported claims from {section}: {'; '.join(claims)}")

    return draft  # attempts exhausted — best-effort accept per locked decision


def _wrap_text(text: str, size: int, max_width: float, fontname: str) -> list[str]:
    import fitz
    words = text.split()
    lines = []
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        if line and fitz.get_text_length(test, fontname=fontname, fontsize=size) > max_width:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    return lines


def _render_pdf(sections: dict, job_title: str, company: str, out_path: str) -> None:
    import fitz

    margin = 50
    doc = fitz.open()
    page = doc.new_page()
    width = page.rect.width - 2 * margin
    height = page.rect.height
    y = margin

    def new_page():
        nonlocal page, y
        page = doc.new_page()
        y = margin

    def write_block(text: str, size: int, fontname: str, gap: int):
        nonlocal y
        for line in _wrap_text(text, size, width, fontname):
            if y + size > height - margin:
                new_page()
            page.insert_text((margin, y), line, fontsize=size, fontname=fontname)
            y += size + 4
        y += gap

    write_block(f"{job_title} — {company}", 14, "hebo", 10)
    for section in SECTIONS:
        text = (sections.get(section) or "").strip()
        if not text:
            continue
        write_block(section.upper(), 11, "hebo", 2)
        for para in text.split("\n"):
            if para.strip():
                write_block(para.strip(), 10, "helv", 4)

    doc.save(out_path)
    doc.close()


async def _reset_checkbox(token: str | None, page_id: str | None, workspace_id: str) -> None:
    if not token or not page_id:
        return
    await throttle_notion(workspace_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"},
            json={"properties": {"Optimize Resume": {"checkbox": False}}},
        )


async def _upload_file_to_notion(token: str, workspace_id: str, file_path: str, filename: str) -> str | None:
    headers_json = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}

    await throttle_notion(workspace_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        create_resp = await client.post(
            f"{NOTION_API}/file_uploads", headers=headers_json,
            json={"filename": filename, "content_type": "application/pdf"},
        )
        if create_resp.status_code >= 400:
            return None
        upload = create_resp.json()
        file_upload_id, upload_url = upload["id"], upload["upload_url"]

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        await throttle_notion(workspace_id)
        send_resp = await client.post(
            upload_url,
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
            files={"file": (filename, file_bytes, "application/pdf")},
        )
        if send_resp.status_code >= 400:
            return None

    return file_upload_id


async def _create_resume_notion_page(token: str, workspace_id: str, resumes_ds_id: str, job_page_id: str, filename: str, pdf_path: str) -> str | None:
    file_upload_id = await _upload_file_to_notion(token, workspace_id, pdf_path, filename)
    if not file_upload_id:
        return None  # accepted gap: Notion sync failure doesn't block the local Resume record

    payload = {
        "parent": {"type": "data_source_id", "data_source_id": resumes_ds_id},
        "properties": {
            "Name": {"title": [{"text": {"content": filename}}]},
            "Job": {"relation": [{"id": job_page_id}]},
            "File": {"files": [{"type": "file_upload", "file_upload": {"id": file_upload_id}, "name": filename}]},
        },
    }
    await throttle_notion(workspace_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{NOTION_API}/pages",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        return None
    return resp.json()["id"]


async def optimize_resume_for_job(user_id: uuid.UUID, job_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        user = await db.get(User, user_id)
        if not job or not user or job.user_id != user_id:
            return

        workspace_id = user.notion_workspace_id or str(user.id)

        if not job.description:
            await _reset_checkbox(user.notion_access_token, job.notion_page_id, workspace_id)
            return  # accepted gap: no JD to optimize against

        grouped = await _fetch_profile_items_by_section(db, user_id)
        if not grouped:
            await _reset_checkbox(user.notion_access_token, job.notion_page_id, workspace_id)
            return  # accepted gap: empty Profile

        result = await _generate_verified_resume(grouped, job.title, job.company, job.description)
        if not result:
            await _reset_checkbox(user.notion_access_token, job.notion_page_id, workspace_id)
            return  # accepted gap: generation failure, no auto-retry beyond the 3-attempt loop

        resume_id = uuid.uuid4()
        shorthash = hashlib.sha256(str(job.id).encode()).hexdigest()[:8]
        filename = f"{_safe(user.email or str(user.id))}_{_safe(job.company)}_{_safe(job.title)}_{shorthash}.pdf"
        pdf_path = _resume_path(resume_id)

        _render_pdf(result, job.title, job.company, pdf_path)

        resume = Resume(id=resume_id, user_id=user_id, job_id=job.id, filename=filename, pdf_path=pdf_path)
        db.add(resume)
        job.optimized_resume_id = resume.id
        await db.commit()

        if user.notion_access_token and user.notion_resumes_data_source_id and job.notion_page_id:
            notion_page_id = await _create_resume_notion_page(
                user.notion_access_token, workspace_id, user.notion_resumes_data_source_id,
                job.notion_page_id, filename, pdf_path,
            )
            if notion_page_id:
                resume.notion_page_id = notion_page_id
                await db.commit()

        await _reset_checkbox(user.notion_access_token, job.notion_page_id, workspace_id)