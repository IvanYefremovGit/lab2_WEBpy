from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.deps import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def login_user(request: Request, user_id: int):
    request.session["user_id"] = user_id


def logout_user(request: Request):
    request.session.clear()


def get_current_user(request: Request, conn):
    user_id = request.session.get("user_id")

    if not user_id:
        return None

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, username, role FROM users WHERE id=%s",
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:
        return None

    return {
        "id": user[0],
        "username": user[1],
        "role": user[2]
    }


def require_admin(user):
    if not user or user["role"] != "admin":
        raise Exception("Admin access required")


@router.post("/login")
def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    conn=Depends(get_db)
):

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, role FROM users WHERE username=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Невірний логін або пароль",
                "user": None
            }
        )

    user_id, role = user

    login_user(request, user_id)

    if role == "admin":
        return RedirectResponse("/admin", status_code=303)

    return RedirectResponse("/", status_code=303)