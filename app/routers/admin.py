from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..deps import get_db
from ..auth import get_current_user, require_admin
templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute("SELECT id, name, description, is_active FROM services ORDER BY id ASC")
    services = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status='waiting'")
    waiting = cursor.fetchone()[0]

    services_list = [
        {"id": s[0], "name": s[1], "description": s[2], "is_active": s[3]}
        for s in services
    ]

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "user": user, "services": services_list, "waiting": waiting},
    )


@router.get("/tickets", response_class=HTMLResponse)
def tickets_list(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            t.id,
            t.ticket_number,
            u.username,
            s.name,
            s.is_active,
            t.scheduled_for,
            t.status,
            t.canceled_by
        FROM tickets t
        JOIN users u ON u.id = t.user_id
        JOIN services s ON s.id = t.service_id
        ORDER BY t.scheduled_for ASC
        """
    )

    tickets = cursor.fetchall()

    tickets_list = [
        {
            "id": t[0],
            "ticket_number": t[1],
            "user": {"username": t[2]},
            "service": {
                "name": t[3],
                "is_active": t[4]
            },
            "scheduled_for": t[5],
            "status": t[6],
            "canceled_by": t[7],
        }
        for t in tickets
    ]

    return templates.TemplateResponse(
        "admin_tickets.html",
        {"request": request, "user": user, "tickets": tickets_list},
    )


@router.post("/tickets/{ticket_id}/status")
def set_ticket_status(
    ticket_id: int,
    request: Request,
    status: str = Form(...),
    conn=Depends(get_db),
):
    user = get_current_user(request, conn)
    require_admin(user)

    allowed = {"approved", "served", "no_show", "canceled"}
    if status not in allowed:
        return RedirectResponse("/admin/tickets", status_code=303)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT status, canceled_by FROM tickets WHERE id=%s",
        (ticket_id,),
    )

    ticket = cursor.fetchone()

    if not ticket:
        return RedirectResponse("/admin/tickets", status_code=303)

    current_status, canceled_by = ticket

    if current_status == "canceled" and canceled_by == "user":
        return RedirectResponse("/admin/tickets", status_code=303)

    if current_status == "canceled":
        return RedirectResponse("/admin/tickets", status_code=303)

    if current_status in {"served", "no_show"}:
        return RedirectResponse("/admin/tickets", status_code=303)

    if status == "canceled":
        cursor.execute(
            """
            UPDATE tickets
            SET status=%s, canceled_by='admin'
            WHERE id=%s
            """,
            (status, ticket_id),
        )
    else:
        cursor.execute(
            """
            UPDATE tickets
            SET status=%s
            WHERE id=%s
            """,
            (status, ticket_id),
        )

    conn.commit()

    return RedirectResponse("/admin/tickets", status_code=303)


@router.get("/services", response_class=HTMLResponse)
def services_list(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, description, is_active FROM services ORDER BY id DESC"
    )

    services = cursor.fetchall()

    services_list = [
        {"id": s[0], "name": s[1], "description": s[2], "is_active": s[3]}
        for s in services
    ]

    return templates.TemplateResponse(
        "services_list.html",
        {"request": request, "user": user, "services": services_list},
    )


@router.get("/services/new", response_class=HTMLResponse)
def service_new_form(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    return templates.TemplateResponse(
        "service_form.html",
        {"request": request, "user": user, "service": None},
    )


@router.post("/services/new")
def service_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    is_active: str = Form(None),
    conn=Depends(get_db),
):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO services (name, description, is_active)
        VALUES (%s,%s,%s)
        """,
        (name, description, is_active == "on"),
    )

    conn.commit()

    return RedirectResponse("/admin/services", status_code=303)


@router.get("/services/{service_id}/edit", response_class=HTMLResponse)
def service_edit_form(service_id: int, request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, description, is_active FROM services WHERE id=%s",
        (service_id,),
    )

    service = cursor.fetchone()

    if service:
        service = {
            "id": service[0],
            "name": service[1],
            "description": service[2],
            "is_active": service[3],
        }

    return templates.TemplateResponse(
        "service_form.html",
        {"request": request, "user": user, "service": service},
    )


@router.post("/services/{service_id}/edit")
def service_update(
    service_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    is_active: str = Form(None),
    conn=Depends(get_db),
):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE services
        SET name=%s, description=%s, is_active=%s
        WHERE id=%s
        """,
        (name, description, is_active == "on", service_id),
    )

    conn.commit()

    return RedirectResponse("/admin/services", status_code=303)


@router.post("/services/{service_id}/delete")
def service_delete(service_id: int, request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM services WHERE id=%s",
        (service_id,),
    )

    conn.commit()

    return RedirectResponse("/admin/services", status_code=303)


@router.get("/statistics", response_class=HTMLResponse)
def statistics(request: Request, conn=Depends(get_db)):
    user = get_current_user(request, conn)
    require_admin(user)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*)
        FROM tickets
        GROUP BY status
    """)
    status_stats = cursor.fetchall()

    cursor.execute("""
        SELECT s.name, COUNT(t.id)
        FROM services s
        LEFT JOIN tickets t ON s.id = t.service_id
        GROUP BY s.name
    """)
    service_stats = cursor.fetchall()

    cursor.execute("""
        SELECT DATE(scheduled_for), COUNT(*)
        FROM tickets
        GROUP BY DATE(scheduled_for)
        ORDER BY DATE(scheduled_for)
    """)
    day_stats = cursor.fetchall()

    return templates.TemplateResponse(
        "admin_statistics.html",
        {
            "request": request,
            "user": user,
            "status_stats": status_stats,
            "service_stats": service_stats,
            "day_stats": day_stats
        }
    )