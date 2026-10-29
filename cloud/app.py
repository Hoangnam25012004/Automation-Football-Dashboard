"""Web app (FastAPI) của bản cloud — design doc cloud §7, §9.

Chạy thử:  python -m cloud            (web + worker trong cùng tiến trình, chỉ để dev)
Triển khai: uvicorn cloud.app:app (container `web`) + python -m cloud.worker (container `worker`)
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from fastapi import Body, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from crawler.errors import CrawlError

from . import auth, config, datasource, jobs, library
from .db import audit, connect, get_setting, migrate, now_ts, set_setting, tx
from .errors import ApiError

log = logging.getLogger("cloud.web")
ROOT = config.ROOT
INDEX_HTML = ROOT / "cloud" / "static" / "index.html"
REPORT_HTML = ROOT / "match_report.html"
MAX_BODY = 64 * 1024
JOB_ID = re.compile(r"^[a-f0-9]{16}$")
MID = re.compile(r"^[A-Za-z0-9]{6,12}$")
HEARTBEAT_STALE_S = 60

CSP = ("default-src 'self'; "
       "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; worker-src 'self' blob: https://cdn.jsdelivr.net; "
       "connect-src 'self' https://cdn.jsdelivr.net https://tessdata.projectnaptha.com; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
# Trang báo cáo cần thêm 'unsafe-eval': Tesseract.js (OCR của nút demo — LineupOCR, vùng đóng băng) đánh giá chuỗi JS.
# Trang đăng nhập/thư viện/admin giữ CSP chặt hơn.
CSP_REPORT = CSP.replace("script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'", "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    boot = connect(settings.db_path)
    migrate(boot)
    boot.close()

    app = FastAPI(title="Match Performance", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings

    # ---------- middleware: kích thước body, header bảo mật, log không có query string ----------
    @app.middleware("http")
    async def guard(request: Request, call_next):
        started = time.monotonic()
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = MAX_BODY + 1
        if length > MAX_BODY:
            response: Response = _error(ApiError("E_PAYLOAD_TOO_LARGE"))
        else:
            response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if settings.secure_cookies:
            response.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, (time.monotonic() - started) * 1000)
        return response

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError):
        return _error(exc)

    @app.exception_handler(CrawlError)
    async def _crawl_error(_request: Request, exc: CrawlError):
        return JSONResponse({"error": exc.to_dict()}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, _exc: RequestValidationError):
        return _error(ApiError("E_BAD_REQUEST"))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException):
        code = "E_NOT_FOUND" if exc.status_code == 404 else "E_BAD_REQUEST"
        return _error(ApiError(code, status=exc.status_code))

    # ---------- dependencies ----------
    def get_conn():
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def client_ip(request: Request) -> str:
        if settings.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()[:64]
        return (request.client.host if request.client else "unknown")[:64]

    def check_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin and origin != settings.origin:
            raise ApiError("E_FORBIDDEN", "Requests from other websites are not allowed.")

    def optional_session(request: Request, conn=Depends(get_conn)):
        return auth.session_user(conn, request.cookies.get(auth.SESSION_COOKIE))

    def member(sess=Depends(optional_session)):
        if not sess:
            raise ApiError("E_AUTH_REQUIRED")
        return sess

    def member_write(request: Request, sess=Depends(member)):
        check_origin(request)
        from .security import same
        if not same(request.headers.get("x-csrf-token", ""), sess["csrf"]):
            raise ApiError("E_CSRF")
        return sess

    def admin(sess=Depends(member)):
        if sess["user"]["role"] != "admin":
            raise ApiError("E_FORBIDDEN")
        return sess

    def admin_write(request: Request, sess=Depends(member_write)):
        if sess["user"]["role"] != "admin":
            raise ApiError("E_FORBIDDEN")
        return sess

    def body_field(body: Any, name: str, required: bool = True):
        if not isinstance(body, dict) or (required and name not in body):
            raise ApiError("E_BAD_REQUEST")
        return body.get(name)

    def set_auth_cookies(response: Response, token: str, csrf: str) -> None:
        max_age = settings.session_days * 86400
        response.set_cookie(auth.SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=settings.secure_cookies,
                            samesite="lax", path="/")
        response.set_cookie(auth.CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=settings.secure_cookies,
                            samesite="lax", path="/")

    # ---------- trang ----------
    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))

    @app.get("/report", response_class=HTMLResponse)
    @app.get("/match_report.html", response_class=HTMLResponse)
    def report():
        return _report_page()

    @app.get("/m/{mid}", response_class=HTMLResponse)
    def report_for_match(mid: str):
        if not MID.match(mid):
            raise ApiError("E_NOT_FOUND")
        return _report_page()

    # ---------- health ----------
    @app.get("/api/health")
    def health(conn=Depends(get_conn)):
        beat = get_setting(conn, "worker_heartbeat", 0) or 0
        age = round(now_ts() - float(beat), 1) if beat else None
        healthy = age is not None and age < HEARTBEAT_STALE_S
        payload = {"ok": healthy, "db": True, "workerHeartbeatAgeS": age, "queue": jobs.stats(conn),
                   "sourcePaused": jobs.breaker_open(conn)}
        return JSONResponse(payload, status_code=200 if healthy else 503)

    # ---------- tài khoản ----------
    @app.post("/api/auth/register")
    def register(request: Request, body: Any = Body(None), conn=Depends(get_conn)):
        check_origin(request)
        return auth.register(conn, settings, body_field(body, "email"), body_field(body, "password"), client_ip(request))

    @app.post("/api/auth/verify")
    def verify(request: Request, body: Any = Body(None), conn=Depends(get_conn)):
        check_origin(request)
        return auth.verify_email(conn, settings, body_field(body, "token"))

    @app.post("/api/auth/login")
    def login(request: Request, body: Any = Body(None), conn=Depends(get_conn)):
        check_origin(request)
        token, data = auth.login(conn, settings, body_field(body, "email"), body_field(body, "password"),
                                 client_ip(request), request.headers.get("user-agent", ""))
        response = JSONResponse(data)
        set_auth_cookies(response, token, data["csrf"])
        return response

    @app.post("/api/auth/logout")
    def logout(sess=Depends(member_write), conn=Depends(get_conn)):
        auth.logout(conn, sess["session_id"])
        response = JSONResponse({"ok": True})
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        response.delete_cookie(auth.CSRF_COOKIE, path="/")
        return response

    @app.post("/api/auth/forgot")
    def forgot(request: Request, body: Any = Body(None), conn=Depends(get_conn)):
        check_origin(request)
        return auth.forgot(conn, settings, body_field(body, "email"), client_ip(request))

    @app.post("/api/auth/reset")
    def reset(request: Request, body: Any = Body(None), conn=Depends(get_conn)):
        check_origin(request)
        return auth.reset_password(conn, body_field(body, "token"), body_field(body, "password"))

    @app.get("/api/me")
    def me(sess=Depends(member), conn=Depends(get_conn)):
        user = sess["user"]
        return {"user": auth.public_user(user), "csrf": sess["csrf"],
                "quota": {"limit": None if user["role"] == "admin" else jobs.user_quota(settings, user),
                          "used": jobs.used_today(conn, user["id"])},
                "sourcePaused": jobs.breaker_open(conn)}

    @app.delete("/api/me")
    def delete_me(body: Any = Body(None), sess=Depends(member_write), conn=Depends(get_conn)):
        auth.delete_account(conn, sess["user"], body_field(body, "password"))
        response = JSONResponse({"ok": True})
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        response.delete_cookie(auth.CSRF_COOKIE, path="/")
        return response

    @app.get("/api/config")
    def public_config(conn=Depends(get_conn)):
        return {"registration": auth.registration_mode(conn, settings)}

    # ---------- báo cáo: job + thư viện ----------
    @app.post("/api/matches", status_code=202)
    def create_job(body: Any = Body(None), sess=Depends(member_write), conn=Depends(get_conn)):
        return jobs.submit(conn, settings, sess["user"], body_field(body, "url"))

    @app.get("/api/matches/{job_id}")
    def get_job(job_id: str, sess=Depends(member), conn=Depends(get_conn)):
        if not JOB_ID.match(job_id):
            raise ApiError("E_JOB_NOT_FOUND")
        return jobs.get(conn, job_id)

    @app.get("/api/library")
    def list_library(q: str = "", page: int = 1, sess=Depends(member), conn=Depends(get_conn)):
        return library.search(conn, sess["user"], q, page)

    @app.get("/api/library/{mid}")
    def library_result(mid: str, request: Request, s: str = "", sess=Depends(optional_session), conn=Depends(get_conn)):
        if not MID.match(mid):
            raise ApiError("E_MATCH_NOT_IN_LIBRARY")
        source = datasource.get().name
        if not sess and not library.check_share(conn, source, mid, s):
            raise ApiError("E_AUTH_REQUIRED")
        result = library.get_result(conn, source, mid)
        m = library.find(conn, source, mid)
        return {"result": result, "entry": library.entry(m, sess["user"] if sess else None), "shared": not sess}

    @app.post("/api/library/{mid}/refresh", status_code=202)
    def refresh(mid: str, sess=Depends(member_write), conn=Depends(get_conn)):
        if not MID.match(mid):
            raise ApiError("E_MATCH_NOT_IN_LIBRARY")
        return jobs.refresh(conn, settings, sess["user"], datasource.get().name, mid)

    @app.post("/api/library/{mid}/share")
    def share(mid: str, body: Any = Body(None), sess=Depends(member_write), conn=Depends(get_conn)):
        if not MID.match(mid):
            raise ApiError("E_MATCH_NOT_IN_LIBRARY")
        enabled = body_field(body, "enabled")
        if not isinstance(enabled, bool):
            raise ApiError("E_BAD_REQUEST")
        with tx(conn):
            return library.set_share(conn, sess["user"], datasource.get().name, mid, enabled)

    # ---------- quản trị ----------
    @app.get("/api/admin/users")
    def admin_users(sess=Depends(admin), conn=Depends(get_conn)):
        return {"users": auth.list_users(conn)}

    @app.post("/api/admin/users")
    def admin_invite(body: Any = Body(None), sess=Depends(admin_write), conn=Depends(get_conn)):
        return auth.admin_create_user(conn, settings, sess["user"], body_field(body, "email"),
                                      body_field(body, "role", required=False) or "member")

    @app.post("/api/admin/users/{user_id}")
    def admin_update(user_id: int, body: Any = Body(None), sess=Depends(admin_write), conn=Depends(get_conn)):
        if not isinstance(body, dict) or not set(body) <= {"status", "role", "dailyQuota"} or not body:
            raise ApiError("E_BAD_REQUEST")
        return auth.admin_update_user(conn, settings, sess["user"], user_id, body)

    @app.get("/api/admin/settings")
    def admin_settings(sess=Depends(admin), conn=Depends(get_conn)):
        beat = get_setting(conn, "worker_heartbeat", 0) or 0
        return {"registration": auth.registration_mode(conn, settings), "breaker": jobs.breaker(conn),
                "sourcePaused": jobs.breaker_open(conn), "queue": jobs.stats(conn),
                "workerHeartbeatAgeS": round(now_ts() - float(beat), 1) if beat else None,
                "quotas": {"userDaily": settings.quota_user_daily, "globalHourly": settings.quota_global_hourly,
                           "queueMax": settings.queue_max}, "mailMode": settings.mail_mode}

    @app.post("/api/admin/settings")
    def admin_settings_update(body: Any = Body(None), sess=Depends(admin_write), conn=Depends(get_conn)):
        if not isinstance(body, dict) or not body or not set(body) <= {"registration", "resetBreaker"}:
            raise ApiError("E_BAD_REQUEST")
        with tx(conn):
            if "registration" in body:
                if body["registration"] not in ("approval", "open", "invite"):
                    raise ApiError("E_BAD_REQUEST")
                set_setting(conn, "registration", body["registration"])
                audit(conn, sess["user"]["id"], "set_registration", body["registration"])
            if body.get("resetBreaker") is True:
                jobs.reset_breaker(conn, sess["user"]["id"])
        return admin_settings(sess, conn)

    @app.get("/api/admin/audit")
    def admin_audit(limit: int = 100, sess=Depends(admin), conn=Depends(get_conn)):
        limit = max(1, min(limit, 500))
        rows = conn.execute("SELECT a.at, a.action, a.detail, u.email FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
                            "ORDER BY a.id DESC LIMIT ?", (limit,)).fetchall()
        return {"items": [dict(r) for r in rows]}

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
    def unknown_api(rest: str):
        raise ApiError("E_NOT_FOUND", "Unknown API endpoint.")

    return app


def _report_page() -> HTMLResponse:
    return HTMLResponse(REPORT_HTML.read_text(encoding="utf-8"), headers={"Content-Security-Policy": CSP_REPORT})


def _error(exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": exc.to_dict()}, status_code=exc.status)


def __getattr__(name: str):
    # `uvicorn cloud.app:app` — tạo app khi được truy cập lần đầu (đọc cấu hình từ môi trường)
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
