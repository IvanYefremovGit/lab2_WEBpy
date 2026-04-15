from datetime import datetime, timedelta, time as dtime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId

import qrcode
import base64
from io import BytesIO

from ..deps import get_db
from ..auth import login_user, logout_user, get_current_user

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

STEP_MINUTES = 10
LEAD_MINUTES = 30

WORK_START = dtime(8, 0)
WORK_END_LAST_SLOT = dtime(16, 50)
DAYS_AHEAD = 14

BLOCKING_STATUSES = {"waiting", "approved", "served", "no_show"}


def log_action(db, action: str, user: dict, details: dict = None):
    db.logs.insert_one({
        "action": action,
        "user_id": user["id"],
        "role": user["role"],
        "time": datetime.now(),
        "details": details or {}
    })


def generate_qr(data: str):
    qr = qrcode.make(data)

    buffer = BytesIO()
    qr.save(buffer, format="PNG")

    return base64.b64encode(buffer.getvalue()).decode()


def build_dates(days_ahead: int = DAYS_AHEAD):
    dates = []
    now = datetime.now()
    today = now.date()

    for i in range(days_ahead):
        d = today + timedelta(days=i)

        if d.weekday() in (5, 6):
            continue

        if d == today and now.time() > WORK_END_LAST_SLOT:
            continue

        dates.append(d.strftime("%Y-%m-%d"))

    return dates


def build_all_times():
    times = []
    h, m = WORK_START.hour, WORK_START.minute

    while True:
        times.append(f"{h:02d}:{m:02d}")

        m += STEP_MINUTES
        if m >= 60:
            h += 1
            m -= 60

        if h > WORK_END_LAST_SLOT.hour or (h == WORK_END_LAST_SLOT.hour and m > WORK_END_LAST_SLOT.minute):
            break

    return times


def build_free_times(db, date_str: str):
    all_times = build_all_times()

    day_start = datetime.strptime(f"{date_str} 00:00", "%Y-%m-%d %H:%M")
    day_end = day_start + timedelta(days=1)

    tickets = list(db.tickets.find({
        "scheduled_for": {"$gte": day_start, "$lt": day_end},
        "status": {"$in": list(BLOCKING_STATUSES)}
    }))

    booked = {t["scheduled_for"].strftime("%H:%M") for t in tickets if "scheduled_for" in t}
    free_times = [t for t in all_times if t not in booked]

    now = datetime.now()
    lead_cutoff = now + timedelta(minutes=LEAD_MINUTES)
    today_str = now.strftime("%Y-%m-%d")

    if date_str == today_str:
        free_times = [
            t for t in free_times
            if datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M") >= lead_cutoff
        ]

    return free_times


def render_index(request: Request, db, user, error: str | None = None):
    services = list(db.services.find({"is_active": True}))

    dates = build_dates(DAYS_AHEAD)

    selected_service_id = str(services[0]["_id"]) if services else None
    selected_date = dates[0] if dates else None

    qp = request.query_params
    if "service_id" in qp:
        selected_service_id = qp["service_id"]

    if "date" in qp:
        selected_date = qp["date"]

    times = []
    if selected_date:
        times = build_free_times(db, selected_date)

    services_list = [
        {
            "id": str(s["_id"]),
            "name": s["name"],
            "description": s.get("description", "")
        }
        for s in services
    ]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "services": services_list,
            "dates": dates,
            "times": times,
            "selected_service_id": selected_service_id,
            "selected_date": selected_date,
            "error": error,
        },
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db=Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=303)

    user = get_current_user(request, db)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if user["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)

    return render_index(request, db, user)


@router.get("/free-times")
def free_times_api(request: Request, date: str, db=Depends(get_db)):
    if not request.session.get("user_id"):
        return JSONResponse({"times": []})

    user = get_current_user(request, db)

    if user["role"] != "user":
        return JSONResponse({"times": []})

    if date not in build_dates(DAYS_AHEAD):
        return JSONResponse({"times": []})

    times = build_free_times(db, date)
    return JSONResponse({"times": times})



@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "user": None})


@router.post("/login")
def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    user = db.users.find_one({
        "username": username,
        "password": password
    })

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Невірний логін або пароль", "user": None},
        )

    login_user(request, str(user["_id"]))

    log_action(db, "login", {
        "id": str(user["_id"]),
        "role": user["role"]
    })

    if user["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)

    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout_action(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


@router.post("/tickets/create")
def create_ticket(
    request: Request,
    service_id: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    db=Depends(get_db),
):
    user = get_current_user(request, db)

    service = db.services.find_one({"_id": ObjectId(service_id), "is_active": True})
    if not service:
        return render_index(request, db, user, error="Невірна послуга.")

    scheduled_for = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")

    ticket_number = f"A{int(datetime.now().timestamp())}"

    db.tickets.insert_one({
        "ticket_number": ticket_number,
        "user_id": user["id"],
        "service_id": service_id,
        "service_name": service["name"],
        "scheduled_for": scheduled_for,
        "status": "waiting"
    })

    log_action(db, "create_ticket", user, {"ticket_number": ticket_number})

    return RedirectResponse("/my/tickets", status_code=303)


@router.get("/my/tickets", response_class=HTMLResponse)
def my_tickets(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)

    tickets = list(db.tickets.find({"user_id": user["id"]}).sort("scheduled_for", -1))

    tickets_list = []

    for t in tickets:
        service = db.services.find_one({"_id": ObjectId(t["service_id"])})
        qr_data = f"http://127.0.0.1:8000/admin/scan/{t['_id']}"

        tickets_list.append({
            "id": str(t["_id"]),
            "ticket_number": t["ticket_number"],
            "service": {"name": service["name"] if service else "Видалено"},
            "scheduled_for": t["scheduled_for"],
            "status": t["status"],
            "qr": generate_qr(qr_data)
        })

    return templates.TemplateResponse(
        "my_tickets.html",
        {"request": request, "user": user, "tickets": tickets_list},
    )


@router.post("/tickets/{ticket_id}/cancel")
def cancel_ticket(ticket_id: str, request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)

    ticket = db.tickets.find_one({
        "_id": ObjectId(ticket_id),
        "user_id": user["id"]
    })

    if ticket and ticket["status"] in {"waiting", "approved"}:
        db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"status": "canceled", "canceled_by": "user"}}
        )

        log_action(db, "cancel_ticket", user, {"ticket_id": ticket_id})

    return RedirectResponse("/my/tickets", status_code=303)


@router.get("/my/statistics", response_class=HTMLResponse)
def my_statistics(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)

    tickets = list(db.tickets.find({"user_id": user["id"]}))

    total = len(tickets)
    served = len([t for t in tickets if t["status"] == "served"])
    canceled = len([t for t in tickets if t["status"] == "canceled"])
    no_show = len([t for t in tickets if t["status"] == "no_show"])
    active = len([t for t in tickets if t["status"] in ["waiting", "approved"]])

    services = list(db.services.find())
    service_stats = []

    for s in services:
        service_tickets = [t for t in tickets if t["service_id"] == str(s["_id"])]

        service_stats.append((
            s["name"],
            len(service_tickets),
            len([t for t in service_tickets if t["status"] == "served"]),
            len([t for t in service_tickets if t["status"] == "canceled"]),
            len([t for t in service_tickets if t["status"] == "no_show"]),
        ))

    return templates.TemplateResponse(
        "user_statistics.html",
        {
            "request": request,
            "user": user,
            "total": total,
            "served": served,
            "canceled": canceled,
            "no_show": no_show,
            "active": active,
            "service_stats": service_stats
        }
    )