# app/routes_chatbot.py

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import os
import json
from functools import lru_cache

from .utils import display_currency

router = APIRouter(tags=["chatbot"])

templates = Jinja2Templates(directory="app/templates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.path.join(BASE_DIR, "chatbot", "tree.json")

@lru_cache(maxsize=1)
def load_tree():
    if not os.path.exists(TREE_PATH):
        raise FileNotFoundError(f"tree.json not found at {TREE_PATH}")
    with open(TREE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("/chatbot/tree")
def get_chatbot_tree():
    try:
        data = load_tree()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chatbot")
def chatbot_page(request: Request):
    return templates.TemplateResponse("chatbot.html", {
        "request": request,
        "session_user": getattr(request.state, "user", None),
        "display_currency": display_currency
    })
