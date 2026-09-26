from __future__ import annotations

import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

REPOSITORY = Path(r"C:\Users\chachoua\Documents\GitHub\Rentall_mvp")
STATIC_ROOT = (REPOSITORY / "app" / "static").resolve()
sys.path.insert(0, str(REPOSITORY / "venv" / "Lib" / "site-packages"))

from jinja2 import Environment, FileSystemLoader


class URL:
    path = "/owner/items/new"

    def __str__(self) -> str:
        return "http://127.0.0.1:8016/owner/items/new"


class Request:
    url = URL()
    session = {
        "user": {
            "id": 1,
            "first_name": "Avery",
            "last_name": "Owner",
            "role": "user",
            "status": "approved",
            "payouts_enabled": False,
        }
    }
    state = SimpleNamespace(unread_messages=0)
    query_params = {}
    cookies = {}
    headers = {}


environment = Environment(loader=FileSystemLoader(str(REPOSITORY / "app" / "templates")))
environment.globals.update(
    url_for=lambda name, **values: "/" + values.get("path", ""),
    current_lang=lambda: "en",
    display_currency="CAD",
)
template = environment.get_template("items_new.html")


def render_listing_form() -> bytes:
    html = template.render(
        request=Request(),
        title="Add Item",
        session_user=Request.session["user"],
        account_limited=False,
        website_error=False,
        categories=[
            {"id": 1, "name": "Vehicles"},
            {"id": 2, "name": "Electronics"},
            {"id": 3, "name": "Home & Garden"},
        ],
        subcats_map={
            1: [{"id": 11, "name": "Cars"}, {"id": 12, "name": "Bikes"}],
            2: [{"id": 21, "name": "Cameras"}, {"id": 22, "name": "Phones"}],
            3: [],
        },
    )
    return html.encode("utf-8")


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/owner/items/new":
            body = render_listing_form()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith("/static/"):
            requested = (STATIC_ROOT / path.removeprefix("/static/")).resolve()
            if STATIC_ROOT in requested.parents and requested.is_file():
                content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
                data = requested.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        self.send_error(404)

    def do_POST(self) -> None:
        self.send_error(405, "Preview server never creates listings")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8016), PreviewHandler).serve_forever()
