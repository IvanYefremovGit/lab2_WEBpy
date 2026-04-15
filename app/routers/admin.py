from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from bson import ObjectId

from fastapi import UploadFile, File
from pyzbar.pyzbar import decode
from PIL import Image
import io

from ..deps import get_db
from ..auth import get_current_user, require_admin

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin", tags=["Admin"])



def log_action(db, action: str, user: dict, details: dict = None):
    db.logs.insert_one({
        "action": action,
        "user_id": user["id"],
        "role": user["role"],
        "time": datetime.now(),
        "details": details or {}
    })


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    services = list(db.services.find().sort("_id", 1))

    services_list = [
        {
            "id": str(s["_id"]),
            "name": s["name"],
            "description": s.get("description", ""),
            "is_active": s.get("is_active", True)
        }
        for s in services
    ]

    waiting = db.tickets.count_documents({"status": "waiting"})

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "user": user,
            "services": services_list,
            "waiting": waiting,
        },
    )


@router.get("/tickets", response_class=HTMLResponse)
def tickets_list(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    tickets = list(db.tickets.find().sort("scheduled_for", 1))

    tickets_list = []

    for t in tickets:
        user_data = db.users.find_one({"_id": ObjectId(t["user_id"])})
        service_data = db.services.find_one({"_id": ObjectId(t["service_id"])})

        tickets_list.append({
            "id": str(t["_id"]),
            "ticket_number": t.get("ticket_number"),
            "user": {"username": user_data["username"] if user_data else "?"},
            "service": {
                "name": service_data["name"] if service_data else t.get("service_name", "Видалено"),
                "is_active": service_data.get("is_active", False) if service_data else False
            },
            "scheduled_for": t.get("scheduled_for"),
            "status": t.get("status"),
            "canceled_by": t.get("canceled_by"),
        })

    return templates.TemplateResponse(
        "admin_tickets.html",
        {"request": request, "user": user, "tickets": tickets_list},
    )


@router.post("/tickets/{ticket_id}/status")
@router.post("/tickets/{ticket_id}/status")
def set_ticket_status(
    ticket_id: str,
    request: Request,
    status: str = Form(...),
    db=Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    ticket = db.tickets.find_one({"_id": ObjectId(ticket_id)})

    if not ticket:
        return RedirectResponse("/admin/tickets", status_code=303)

    current_status = ticket["status"]

    allowed_transitions = {
        "waiting": ["approved", "canceled"],
        "approved": ["served", "no_show", "canceled"],
        "served": [],
        "no_show": [],
        "canceled": []
    }

    if status not in allowed_transitions.get(current_status, []):
        return RedirectResponse("/admin/tickets", status_code=303)

    update_data = {"status": status}

    if status == "canceled":
        update_data["canceled_by"] = "admin"

    db.tickets.update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": update_data}
    )

    log_action(db, "update_ticket_status", user, {
        "ticket_id": ticket_id,
        "from": current_status,
        "to": status
    })

    return RedirectResponse("/admin/tickets", status_code=303)


@router.get("/services", response_class=HTMLResponse)
def services_list(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    services = list(db.services.find().sort("_id", -1))

    services_list = [
        {
            "id": str(s["_id"]),
            "name": s["name"],
            "description": s.get("description", ""),
            "is_active": s.get("is_active", True)
        }
        for s in services
    ]

    return templates.TemplateResponse(
        "services_list.html",
        {"request": request, "user": user, "services": services_list},
    )


@router.post("/services/new")
def service_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    is_active: str = Form(None),
    db=Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    db.services.insert_one({
        "name": name,
        "description": description,
        "is_active": True if is_active == "on" else False
    })

    log_action(db, "create_service", user, {"name": name})

    return RedirectResponse("/admin/services", status_code=303)


@router.get("/services/{service_id}/edit", response_class=HTMLResponse)
def service_edit_form(service_id: str, request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    service = db.services.find_one({"_id": ObjectId(service_id)})

    if service:
        service["id"] = str(service["_id"])

    return templates.TemplateResponse(
        "service_form.html",
        {"request": request, "user": user, "service": service},
    )


@router.post("/services/{service_id}/edit")
def service_update(
    service_id: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    is_active: str = Form(None),
    db=Depends(get_db),
):
    user = get_current_user(request, db)
    require_admin(user)

    db.services.update_one(
        {"_id": ObjectId(service_id)},
        {
            "$set": {
                "name": name,
                "description": description,
                "is_active": is_active == "on"
            }
        }
    )

    log_action(db, "update_service", user, {"service_id": service_id})

    return RedirectResponse("/admin/services", status_code=303)


@router.post("/services/{service_id}/delete")
def service_delete(service_id: str, request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    db.services.delete_one({"_id": ObjectId(service_id)})

    log_action(db, "delete_service", user, {"service_id": service_id})

    return RedirectResponse("/admin/services", status_code=303)


@router.get("/statistics", response_class=HTMLResponse)
def statistics(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    status_stats = []
    for status in ["waiting", "approved", "served", "no_show", "canceled"]:
        count = db.tickets.count_documents({"status": status})
        status_stats.append((status, count))

    services = list(db.services.find())
    service_stats = []

    for s in services:
        count = db.tickets.count_documents({"service_id": str(s["_id"])})
        service_stats.append((s["name"], count))

    tickets = list(db.tickets.find())
    day_dict = {}

    for t in tickets:
        if "scheduled_for" in t:
            day = t["scheduled_for"].date()
            day_dict[day] = day_dict.get(day, 0) + 1

    day_stats = sorted(day_dict.items())

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


@router.get("/services/new", response_class=HTMLResponse)
def service_new_form(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    return templates.TemplateResponse(
        "service_form.html",
        {"request": request, "user": user, "service": None},
    )


@router.get("/logs", response_class=HTMLResponse)
def view_logs(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    logs = list(db.logs.find().sort("time", -1))

    return templates.TemplateResponse(
        "admin_logs.html",
        {"request": request, "user": user, "logs": logs}
    )


@router.get("/scan/{ticket_id}", response_class=HTMLResponse)
def scan_ticket(ticket_id: str, request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    ticket = db.tickets.find_one({"_id": ObjectId(ticket_id)})

    if not ticket:
        return templates.TemplateResponse(
            "scan_result.html",
            {"request": request, "message": "Талон не знайдено"}
        )

    if ticket["status"] in ["approved", "served", "no_show", "canceled"]:
        return templates.TemplateResponse(
            "scan_result.html",
            {"request": request, "message": f"Талон вже оброблений ({ticket['status']})"}
        )

    db.tickets.update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": {"status": "approved"}}
    )

    db.logs.insert_one({
        "action": "scan_ticket",
        "user_id": user["id"],
        "role": user["role"],
        "time": datetime.now(),
        "details": {"ticket_id": ticket_id}
    })

    return templates.TemplateResponse(
        "scan_result.html",
        {"request": request, "message": "Талон підтверджено"}
    )


@router.post("/scan-image")
async def scan_qr_image(
    request: Request,
    file: UploadFile = File(...),
    db=Depends(get_db)
):
    user = get_current_user(request, db)
    require_admin(user)

    contents = await file.read()
    image = Image.open(io.BytesIO(contents))

    decoded = decode(image)

    if not decoded:
        return templates.TemplateResponse(
            "scan_result.html",
            {"request": request, "message": "QR не знайдено ❌"}
        )

    qr_data = decoded[0].data.decode()

    ticket_id = qr_data.split("/")[-1]

    return RedirectResponse(f"/admin/scan/{ticket_id}", status_code=303)


@router.get("/scanner", response_class=HTMLResponse)
def scanner_page(request: Request, db=Depends(get_db)):
    user = get_current_user(request, db)
    require_admin(user)

    return templates.TemplateResponse(
        "scanner.html",
        {"request": request, "user": user}
    )