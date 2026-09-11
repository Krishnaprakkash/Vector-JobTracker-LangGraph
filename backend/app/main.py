from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from . import resumes, users, jobs, notion_oauth, notion_setup, notion_webhook

app = FastAPI(title=os.getenv("APP_NAME", "Vector"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "app": os.getenv("APP_NAME", "Vector")}

app.include_router(resumes.router)
app.include_router(users.router)
app.include_router(jobs.router)
app.include_router(notion_oauth.router)
app.include_router(notion_setup.router)
app.include_router(notion_webhook.router)