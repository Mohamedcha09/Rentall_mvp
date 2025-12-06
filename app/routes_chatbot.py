# app/routes_chatbot.py

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import os
import json
from functools import lru_cache

router = APIRouter(tags=["chatbot"])

# -----------------------------
#  TEMPLATES SETUP
# -----------------------------
templates = Jinja2Templates(directory="app/templates")

# -----------------------------
#  PATH OF JSON TREE
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.path.join(BASE_DIR, "chatbot", "tree.json")

# -----------------------------
#  LOAD JSON WITH CACHE
# -----------------------------
@lru_cache(maxsize=1)
def load_tree():
    """Load chatbot tree.json only once."""
    if not os.path.exists(TREE_PATH):
        raise FileNotFoundError(f"tree.json not found at {TREE_PATH}")
    with open(TREE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# -----------------------------
#  API → RETURN THE JSON TREE
# -----------------------------
@router.get("/chatbot/tree")
def get_chatbot_tree():
    """Return chatbot JSON structure."""
    try:
        data = load_tree()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------
#  PAGE → chatbot.html
# -----------------------------
@router.get("/chatbot")
def chatbot_page(request: Request):
    """
    Serve the chatbot HTML page.
    This page contains the 3-column interface (Sections / Questions / Answers)
    and the JS that fetches: /chatbot/tree
    """
    return templates.TemplateResponse("chatbot.html", {"request": request})
