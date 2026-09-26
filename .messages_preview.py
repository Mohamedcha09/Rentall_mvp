from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "venv" / "Lib" / "site-packages"))
from jinja2 import Environment, FileSystemLoader


class URL:
    def __init__(self, path: str):
        self.path = path

    def __str__(self) -> str:
        return "http://127.0.0.1:8023" + self.path


class Request:
    def __init__(self, path: str):
        self.url = URL(path)
        self.state = SimpleNamespace(unread_messages=0)
        self.query_params = {}
        self.cookies = {}
        self.session = {}
        self.headers = {}


env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")))
env.globals.update(
    url_for=lambda name, **values: "/static/" + values.get("path", ""),
    current_lang=lambda: "en",
    display_currency="CAD",
)

session_user = {
    "id": 7,
    "first_name": "Ari",
    "last_name": "Demo",
    "username": "ari",
    "avatar_path": "",
    "role": "user",
    "status": "approved",
    "is_mod": False,
    "is_support": False,
    "cs_enabled": False,
    "can_manage_deposits": False,
    "payouts_enabled": False,
}

now = datetime(2026, 9, 26, 10, 23)
other = SimpleNamespace(
    id=22,
    first_name="Zas",
    last_name="Dcv with an intentionally long profile name",
    is_verified=True,
    avatar_path="/static/img/1.jpg",
    created_at=now - timedelta(days=400),
)
item = SimpleNamespace(
    id=91,
    title="Momo — a deliberately long listing title to test safe truncation",
    image_path="/static/img/1.jpg",
    price_per_day=25,
    price=25,
    currency="CAD",
    city="Montréal",
)
thread = SimpleNamespace(id=22, item_id=item.id, item=item)
messages = [
    SimpleNamespace(id=1, sender_id=22, body="Hello! How can I help?", created_at=now - timedelta(minutes=11), is_read=True),
    SimpleNamespace(id=2, sender_id=7, body="Is it available this weekend?", created_at=now - timedelta(minutes=9), is_read=True),
    SimpleNamespace(id=3, sender_id=22, body="Yes, it is still available. I can reserve it for you.", created_at=now - timedelta(minutes=7), is_read=True),
    SimpleNamespace(id=4, sender_id=22, body="From Saturday to Sunday works well.", created_at=now - timedelta(minutes=5), is_read=True),
    SimpleNamespace(id=5, sender_id=7, body="Perfect. I will reserve it for you.", created_at=now - timedelta(minutes=2), is_read=False),
]

threads = [
    {
        "id": 22,
        "other_fullname": "Zas Dcv with an intentionally long profile name",
        "last_message_at": now,
        "item_title": "Momo — a deliberately long listing title to test truncation",
        "item_image": "/static/img/1.jpg",
        "unread_count": 2,
        "other_verified": True,
        "other_avatar": "/static/img/1.jpg",
        "other_created_iso": (now - timedelta(days=400)).isoformat(),
        "last_message_text": "A longer preview shows that the row keeps its hierarchy intact.",
    },
    {
        "id": 23,
        "other_fullname": "Moh Hami",
        "last_message_at": now - timedelta(days=1),
        "item_title": "cd ps4",
        "item_image": "/static/img/2.jpg",
        "unread_count": 1,
        "other_verified": False,
        "other_avatar": "/static/placeholder.svg",
        "other_created_iso": "",
        "last_message_text": "Is it still available?",
    },
    {
        "id": 24,
        "other_fullname": "Sara K.",
        "last_message_at": now - timedelta(days=3),
        "item_title": "Road bicycle",
        "item_image": "/static/placeholder.svg",
        "unread_count": 0,
        "other_verified": False,
        "other_avatar": "/static/placeholder.svg",
        "other_created_iso": "",
        "last_message_text": "Sounds good — see you then.",
    },
]
chatbot_tickets = [
    SimpleNamespace(id=53, subject="I need help with a booking", updated_at=now - timedelta(hours=3), unread_for_user=True),
]


def render(path: str) -> str:
    request = Request(path)
    if path == "/messages":
        return env.get_template("inbox.html").render(
            request=request,
            title="Messages",
            threads=threads,
            chatbot_tickets=chatbot_tickets,
            tickets_count=len(chatbot_tickets),
            session_user=session_user,
            account_limited=False,
        )
    return env.get_template("thread.html").render(
        request=request,
        title="Conversation",
        thread=thread,
        messages=messages,
        other=other,
        other_avatar="/static/img/1.jpg",
        item_title=item.title,
        item_image=item.image_path,
        session_user=session_user,
        account_limited=False,
        focused_conversation=True,
    )


class Handler(SimpleHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/messages" or path == "/messages/22":
            body = render(path).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.endswith("/typing_status"):
            self._json({"typing": False})
            return
        if path.endswith("/poll"):
            self._json({"messages": []})
            return
        if path.startswith("/static/"):
            self.path = path[len("/static"):]
            return super().do_GET()
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.endswith("/typing"):
            self._json({"ok": True})
            return
        self.send_error(405)


if __name__ == "__main__":
    handler = partial(Handler, directory=str(ROOT / "app" / "static"))
    ThreadingHTTPServer(("127.0.0.1", 8023), handler).serve_forever()
