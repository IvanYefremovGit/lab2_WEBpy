from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.routers import public, admin

tags_metadata = [
    {"name": "Public", "description": "Публічні сторінки HTML"},
    {"name": "Auth", "description": "Вхід/вихід користувача"},
    {"name": "Tickets", "description": "Робота з талонами електронної черги"},
    {"name": "Admin", "description": "Адміністративні функції"},
]

app = FastAPI(
    title="Electronic Queue",
    version="2.0.0",
    description="Електронна черга на FastAPI + PostgreSQL + psycopg",
    openapi_tags=tags_metadata,
    docs_url="/swagger",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(SessionMiddleware, secret_key="super-secret-key-change-me")

app.include_router(public.router)
app.include_router(admin.router)

# uvicorn app.main:app --reload
