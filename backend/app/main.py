import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import (
    admin,
    auth,
    categories,
    chat,
    faqs,
    imports,
    library,
    logs,
    settings as settings_router,
    unanswered,
    uploads,
    usage,
    users,
    vault,
)
from app.services.harvest_resume import schedule_resume_pending_sources

app = FastAPI(title="Helpdesk RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(categories.router)
# imports.router defines static paths (/api/faqs/template, /api/faqs/import) that
# must be registered before faqs.router's /api/faqs/{faq_id} or the dynamic route
# would shadow them.
app.include_router(imports.router)
app.include_router(faqs.router)
app.include_router(uploads.router)
app.include_router(unanswered.router)
app.include_router(logs.router)
app.include_router(settings_router.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(vault.router)
app.include_router(library.router)
app.include_router(usage.router)


@app.on_event("startup")
async def _resume_pending_library_sources() -> None:
    schedule_resume_pending_sources()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
