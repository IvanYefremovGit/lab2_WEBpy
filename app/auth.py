from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime

from app.deps import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def login_user(request: Request, user_id: str):
    request.session["user_id"] = user_id


def logout_user(request: Request):
    request.session.clear()


def get_current_user(request: Request, db):
    user_id = request.session.get("user_id")

    if not user_id:
        return None

    user = db.users.find_one({"_id": ObjectId(user_id)})

    if not user:
        return None

    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "role": user["role"]
    }


def require_admin(user):
    if not user or user["role"] != "admin":
        raise Exception("Admin access required")


@router.post("/login")
def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db)
):
    user = db.users.find_one({
        "username": username,
        "password": password
    })

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Невірний логін або пароль",
                "user": None
            }
        )

    login_user(request, str(user["_id"]))

    if user["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)

    db.logs.insert_one({
        "action": "login",
        "username": username,
        "time": datetime.now()
    })

    return RedirectResponse("/", status_code=303)