# app/routes_static.py
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["static-pages"])

@router.get("/delete-account", include_in_schema=False)
def delete_account_page(request: Request):
    return templates.TemplateResponse(
        "delete_account.html",
        {"request": request}
    )
