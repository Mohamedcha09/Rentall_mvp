# app/routes_chatbot.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import os
import json
from functools import lru_cache

router = APIRouter(tags=["chatbot"])

# تحديد مكان ملف الشات بوت
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TREE_PATH = os.path.join(BASE_DIR, "chatbot", "tree.json")

@lru_cache(maxsize=1)
def load_tree():
    """تحميل JSON مرة واحدة وتسريعه."""
    if not os.path.exists(TREE_PATH):
        raise FileNotFoundError(f"tree.json not found at {TREE_PATH}")
    with open(TREE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("/chatbot/tree")
def get_chatbot_tree():
    """API تُرجع كل الأسئلة للشات بوت."""
    try:
        data = load_tree()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
