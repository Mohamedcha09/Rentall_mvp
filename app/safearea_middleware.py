from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SafeAreaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)

        if response.headers.get("content-type", "").startswith("text/html"):
            body = response.body.decode("utf-8")

            if "</head>" in body:
                body = body.replace(
                    "</head>",
                    '<link rel="stylesheet" href="/static/app-safearea.css"></head>'
                )
                response.body = body.encode("utf-8")
                response.headers["content-length"] = str(len(response.body))

        return response
