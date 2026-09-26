"""Temporary local-only visual fixture for Home responsive QA."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "venv" / "Lib" / "site-packages"))
from jinja2 import Environment, FileSystemLoader


TEMPLATES = ROOT / "app" / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
env.globals.update(
    url_for=lambda name, **values: "/static/" + values.get("path", "") if name == "static" else "/",
    current_lang=lambda: "en",
    display_currency="CAD",
)


def listing(index: int) -> dict:
    pictures = ["/static/img/1.jpg", "/static/img/2.jpg", "/static/img/3.jpg", "/static/img/6.jpg"]
    names = ["Compact camera", "Weekend bike", "Kitchen mixer", "Camping kit"]
    return {
        "id": index,
        "title": names[(index - 1) % len(names)],
        "image_path": pictures[(index - 1) % len(pictures)],
        "city": "Toronto",
        "category": "Tools",
        "subcategory": "Tools",
        "price_per_day": 20 + index,
        "display_price": 20 + index,
        "display_symbol": "$",
        "rating_avg": 4.6 + ((index % 3) / 10),
        "rating_count": 6 + index,
        "currency": "CAD",
        "owner_name": "Preview owner",
        "owner_avatar_path": "",
        "owner_initial": "P",
    }


def render_home() -> str:
    request = SimpleNamespace(
        url=SimpleNamespace(path="/"),
        query_params={},
        state=SimpleNamespace(unread_messages=2),
        session={},
        cookies={"disp_cur": "CAD", "geo_manual_done": "1"},
        headers={},
    )
    nearby = [listing(index) for index in range(1, 7)]
    template = env.get_template("home.html")
    return template.render(
        request=request,
        title="Home preview",
        session_user={
            "id": 1,
            "first_name": "Preview",
            "last_name": "User",
            "username": "preview",
            "avatar_path": "",
            "role": "user",
            "status": "approved",
            "is_mod": False,
            "is_support": False,
            "cs_enabled": False,
            "can_manage_deposits": False,
            "payouts_enabled": False,
        },
        show_tabbar=True,
        is_home=True,
        immersive=False,
        no_ui=False,
        focused_conversation=False,
        message=None,
        nearby_items=nearby,
        items_by_category={"Tools": [listing(index) for index in range(7, 12)]},
        all_items=[listing(index) for index in range(12, 24)],
        banners=["/static/img/11.jpg", "/static/img/12.jpg"],
        top_strip_cols=[[], [], []],
        selected_city="Toronto",
        lat=None,
        lng=None,
        radius_km=25,
        category_label=lambda value: value,
        favorites_ids=[2],
    )


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "app"), **kwargs)

    def do_GET(self):
        if urlparse(self.path).path == "/":
            body = render_home().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8766), PreviewHandler).serve_forever()
