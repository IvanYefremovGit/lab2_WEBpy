from datetime import datetime, timedelta, time as dtime
from pydantic import BaseModel

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..deps import get_db
from ..auth import login_user, logout_user, get_current_user
from ..ai_assistant import ask_ai

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

STEP_MINUTES = 10
LEAD_MINUTES = 30

WORK_START = dtime(8, 0)
WORK_END_LAST_SLOT = dtime(16, 50)
DAYS_AHEAD = 14

BLOCKING_STATUSES = {"waiting", "approved", "served", "no_show"}

class AIRequest(BaseModel):
    message: str

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


def build_free_times(conn, date_str: str):
    cursor = conn.cursor()

    all_times = build_all_times()

    day_start = datetime.strptime(f"{date_str} 00:00", "%Y-%m-%d %H:%M")
    day_end = day_start + timedelta(days=1)

    cursor.execute(
        """
        SELECT scheduled_for FROM tickets
        WHERE scheduled_for >= %s
        AND scheduled_for < %s
        AND status = ANY(%s)
        """,
        (day_start, day_end, list(BLOCKING_STATUSES)),
    )

    tickets = cursor.fetchall()

    booked = {t[0].strftime("%H:%M") for t in tickets}
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


def render_index(request: Request, conn, user, error: str | None = None):
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, description FROM services WHERE is_active = TRUE")
    services = cursor.fetchall()

    dates = build_dates(DAYS_AHEAD)

    selected_service_id = services[0][0] if services else None
    selected_date = dates[0] if dates else None

    qp = request.query_params
    if "service_id" in qp:
        try:
            selected_service_id = int(qp["service_id"])
        except ValueError:
            pass
    if "date" in qp:
        selected_date = qp["date"]

    times = []
    if selected_date:
        times = build_free_times(conn, selected_date)

    services_list = [
        {"id": s[0], "name": s[1], "description": s[2]} for s in services
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


@router.get("/", response_class=HTMLResponse, tags=["Public"])
def index(request: Request, conn=Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=303)

    user = get_current_user(request, conn)

    if user["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)

    return render_index(request, conn, user)


@router.get("/free-times", tags=["Public"])
def free_times_api(request: Request, date: str, conn=Depends(get_db)):
    if not request.session.get("user_id"):
        return JSONResponse({"times": []})

    user = get_current_user(request, conn)

    if user["role"] != "user":
        return JSONResponse({"times": []})

    if date not in build_dates(DAYS_AHEAD):
        return JSONResponse({"times": []})

    times = build_free_times(conn, date)
    return JSONResponse({"times": times})


@router.get("/login", response_class=HTMLResponse, tags=["Auth"])
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "user": None})


@router.post("/login", tags=["Auth"])
def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    conn=Depends(get_db),
):
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, role FROM users WHERE username=%s AND password=%s",
        (username, password),
    )

    user = cursor.fetchone()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Невірний логін або пароль", "user": None},
        )

    user_id, role = user

    login_user(request, user_id)

    if role == "admin":
        return RedirectResponse("/admin", status_code=303)

    return RedirectResponse("/", status_code=303)


@router.post("/logout", tags=["Auth"])
def logout_action(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


@router.post("/tickets/create", tags=["Tickets"])
def create_ticket(
    request: Request,
    service_id: int = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    conn=Depends(get_db),
):
    user = get_current_user(request, conn)

    if user["role"] != "user":
        return RedirectResponse("/admin", status_code=303)

    cursor = conn.cursor()

    cursor.execute("SELECT id FROM services WHERE is_active = TRUE")
    services = [s[0] for s in cursor.fetchall()]

    if service_id not in services:
        return render_index(request, conn, user, error="Невірна послуга.")

    allowed_dates = build_dates(DAYS_AHEAD)
    if date not in allowed_dates:
        return render_index(request, conn, user, error="Невірна дата.")

    try:
        scheduled_for = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return render_index(request, conn, user, error="Невірний формат дати/часу.")

    now = datetime.now()

    lead_cutoff = now + timedelta(minutes=LEAD_MINUTES)
    if scheduled_for < lead_cutoff:
        return render_index(request, conn, user, error=f"Запис можливий мінімум за {LEAD_MINUTES} хвилин.")

    t = scheduled_for.time()
    if not (WORK_START <= t <= WORK_END_LAST_SLOT):
        return render_index(request, conn, user, error="Невірний час.")

    if scheduled_for.minute % STEP_MINUTES != 0:
        return render_index(request, conn, user, error="Хвилини мають бути кратні 10.")

    cursor.execute(
        """
        SELECT id FROM tickets
        WHERE scheduled_for=%s
        AND status = ANY(%s)
        """,
        (scheduled_for, list(BLOCKING_STATUSES)),
    )

    if cursor.fetchone():
        return render_index(request, conn, user, error="Цей час уже зайнятий.")

    ticket_number = f"A{int(datetime.now().timestamp())}"

    cursor.execute(
        """
        INSERT INTO tickets
        (ticket_number, user_id, service_id, scheduled_for, status)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (ticket_number, user["id"], service_id, scheduled_for, "waiting"),
    )

    conn.commit()

    return RedirectResponse("/my/tickets", status_code=303)


@router.get("/my/tickets", response_class=HTMLResponse, tags=["Tickets"])
@router.get("/my/tickets", response_class=HTMLResponse, tags=["Tickets"])
def my_tickets(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)

    if user["role"] != "user":
        return RedirectResponse("/admin", status_code=303)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            t.id,
            t.ticket_number,
            s.name,
            t.scheduled_for,
            t.status
        FROM tickets t
        JOIN services s ON s.id = t.service_id
        WHERE t.user_id = %s
        ORDER BY t.scheduled_for DESC
        """,
        (user["id"],),
    )

    tickets = cursor.fetchall()

    tickets_list = [
        {
            "id": t[0],
            "ticket_number": t[1],
            "service": {"name": t[2]},
            "scheduled_for": t[3],
            "status": t[4],
        }
        for t in tickets
    ]

    return templates.TemplateResponse(
        "my_tickets.html",
        {"request": request, "user": user, "tickets": tickets_list},
    )


@router.post("/tickets/{ticket_id}/cancel", tags=["Tickets"])
def cancel_ticket(ticket_id: int, request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)

    if user["role"] != "user":
        return RedirectResponse("/admin", status_code=303)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT status FROM tickets
        WHERE id=%s AND user_id=%s
        """,
        (ticket_id, user["id"]),
    )

    ticket = cursor.fetchone()

    if ticket and ticket[0] in {"waiting", "approved"}:
        cursor.execute(
            """
            UPDATE tickets
            SET status='canceled', canceled_by='user'
            WHERE id=%s
            """,
            (ticket_id,),
        )
        conn.commit()

    return RedirectResponse("/my/tickets", status_code=303)


@router.get("/my/statistics", response_class=HTMLResponse)
def my_statistics(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM tickets
        WHERE user_id=%s
    """, (user["id"],))
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM tickets
        WHERE user_id=%s AND status='served'
    """, (user["id"],))
    served = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM tickets
        WHERE user_id=%s AND status='canceled'
    """, (user["id"],))
    canceled = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM tickets
        WHERE user_id=%s AND status='no_show'
    """, (user["id"],))
    no_show = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM tickets
        WHERE user_id=%s AND status IN ('waiting','approved')
    """, (user["id"],))
    active = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            s.name,
            COUNT(t.id) AS total,
            COUNT(*) FILTER (WHERE t.status='served') AS served,
            COUNT(*) FILTER (WHERE t.status='canceled') AS canceled,
            COUNT(*) FILTER (WHERE t.status='no_show') AS no_show
        FROM services s
        LEFT JOIN tickets t
            ON t.service_id = s.id
            AND t.user_id = %s
        GROUP BY s.name
        ORDER BY s.name
    """, (user["id"],))

    service_stats = cursor.fetchall()

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


@router.post("/ai/chat")
def ai_chat(req: AIRequest):

    answer = ask_ai(req.message)

    return {"answer": answer}


@router.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request, conn=Depends(get_db)):

    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=303)

    user = get_current_user(request, conn)

    return templates.TemplateResponse(
        "ai_chat.html",
        {
            "request": request,
            "user": user
        }
    )