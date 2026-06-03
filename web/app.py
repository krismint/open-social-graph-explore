from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from adapters.minimal_platform import PROFILE_SESSION_ERROR_MARKER
from adapters.registry import DEFAULT_PLATFORM_ID, detect_platform, platform_display_name
from core.avatar_cache import DEFAULT_AVATAR_CACHE_DIR, avatar_public_url, cache_avatar_url
from core.chromium_cdp import DEFAULT_CDP_PORT, DEFAULT_CDP_PROFILE, probe_cdp
from core.db import PROJECT_ROOT, connect, initialize_database
from core.graph_renderer import render_graph_html
from core.graph_analyzer import analyze_graph
from core.identity import account_identity_detail
from core.node_deletion import delete_platform_account_node, prune_adjacent_orphan_nodes
from core.platform_expansion_runner import DEFAULT_GRAPH, prepare_platform_expansion, run_prepared_platform_expansion, update_platform_profile


APP_DB = Path(os.environ.get("OSGE_DB", PROJECT_ROOT / "data" / "database" / "osge_overlay.db"))
APP_GRAPH = Path(os.environ.get("OSGE_GRAPH", DEFAULT_GRAPH))

app = FastAPI(title="Open Social Graph Explorer", version="0.2.0")
DEFAULT_AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets/avatar_cache", StaticFiles(directory=DEFAULT_AVATAR_CACHE_DIR), name="avatar_cache")
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="osge-expansion")


class ExpandRequest(BaseModel):
    account_id: str = Field(..., min_length=1, description="Platform account id, profile URL, or share URL")
    platform: str = Field("", description="Optional platform hint")
    max_notes: int = Field(5, ge=1, le=50)
    max_comments: int = Field(10, ge=1, le=200)
    get_sub_comments: bool = False
    force: bool = False


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse("/graph")


@app.get("/graph", response_class=HTMLResponse)
def graph(center: str = "", platform: str = DEFAULT_PLATFORM_ID) -> FileResponse:
    initialize_database(APP_DB)
    source_platform = _platform_for_account(center, platform)
    render_graph_html(
        APP_DB,
        APP_GRAPH,
        center_id=center,
        api_enabled=True,
        source_platform=source_platform,
    )
    return FileResponse(APP_GRAPH, media_type="text/html")


@app.get("/osge_graph.html", response_class=HTMLResponse)
def current_graph(platform: str = DEFAULT_PLATFORM_ID) -> FileResponse:
    render_graph_html(APP_DB, APP_GRAPH, api_enabled=True, source_platform=_platform_for_account("", platform))
    return FileResponse(APP_GRAPH, media_type="text/html")


@app.get("/api/health")
def health() -> dict[str, object]:
    cdp = probe_cdp(DEFAULT_CDP_PORT, DEFAULT_CDP_PROFILE)
    return {
        "ok": True,
        "db": str(APP_DB),
        "graph": str(APP_GRAPH),
        "cdp": {
            "ok": cdp.ok,
            "port": cdp.port,
            "url": cdp.url,
            "browser": cdp.browser,
            "profile_dir": cdp.profile_dir,
            "error": cdp.error,
        },
    }


@app.post("/api/expand")
def expand(request: ExpandRequest) -> dict[str, object]:
    if request.max_notes > 10 or request.max_comments > 50 or request.get_sub_comments:
        # Keep the default path conservative; operators can still change limits deliberately.
        pass
    platform = _platform_for_account(request.account_id, request.platform)
    try:
        prepared = prepare_platform_expansion(
            platform,
            account=request.account_id,
            db_path=APP_DB,
            graph_output=APP_GRAPH,
            max_notes=request.max_notes,
            max_comments=request.max_comments,
            get_sub_comments=request.get_sub_comments,
            force=request.force,
            requested_by="web",
        )
        runner = run_prepared_platform_expansion
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if prepared.skipped:
        return {
            "skipped": True,
            "target_id": prepared.target_id,
            "reason": prepared.reason,
        }

    executor.submit(runner, prepared)
    return {
        "skipped": False,
        "job_id": prepared.job_id,
        "target_id": prepared.target_id,
        "status": "running",
        "log_path": str(prepared.log_path),
    }


@app.get("/api/accounts/search")
def search_accounts(q: str, limit: int = 12, platform: str = DEFAULT_PLATFORM_ID) -> dict[str, object]:
    query = q.strip()
    if not query:
        return {"query": query, "results": []}
    safe_limit = max(1, min(limit, 50))
    pattern = f"%{query}%"
    initialize_database(APP_DB)
    with connect(APP_DB) as conn:
        rows = conn.execute(
            """
            SELECT account_id, platform, platform_user_id, source_record_id,
                   username, nickname, profile_url, avatar_url, avatar_local_path,
                   location, gender, crawl_level, source
            FROM accounts
            WHERE hidden_at IS NULL
              AND (
                   account_id LIKE ?
                OR platform_user_id LIKE ?
                OR username LIKE ?
                OR nickname LIKE ?
              )
            ORDER BY
                CASE
                    WHEN username = ? THEN 0
                    WHEN platform_user_id = ? THEN 1
                    WHEN nickname = ? THEN 2
                    ELSE 3
                END,
                is_target DESC,
                last_seen DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, query, query, query, safe_limit),
        ).fetchall()
    return {"query": query, "results": [_with_avatar_public_url(dict(row)) for row in rows]}


@app.get("/api/account-identity/{account_id:path}")
def account_identity(account_id: str) -> dict[str, object]:
    try:
        detail = account_identity_detail(APP_DB, account_id)
        detail["selected_account"] = _with_avatar_public_url(detail["selected_account"])
        detail["linked_accounts"] = [
            _with_avatar_public_url(account)
            for account in detail["linked_accounts"]
        ]
        return detail
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/account-profile-refresh/{account_id:path}")
def refresh_account_profile(account_id: str) -> dict[str, object]:
    platform = _platform_for_account(account_id)
    try:
        return update_platform_profile(platform, account_id, db_path=APP_DB, graph_output=APP_GRAPH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/account-avatar-refresh/{account_id:path}")
def refresh_account_avatar(account_id: str) -> dict[str, object]:
    initialize_database(APP_DB)
    with connect(APP_DB) as conn:
        row = conn.execute(
            """
            SELECT account_id, platform, avatar_url
            FROM accounts
            WHERE account_id = ?
              AND hidden_at IS NULL
            """,
            (account_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Account not found")
        avatar_url = str(row["avatar_url"] or "")
        if not avatar_url:
            raise HTTPException(status_code=400, detail="Account has no remote avatar URL")

        result = cache_avatar_url(avatar_url, platform=str(row["platform"] or ""))
        if result.local_path:
            conn.execute(
                """
                UPDATE accounts
                SET avatar_local_path = ?,
                    avatar_cached_at = CURRENT_TIMESTAMP,
                    avatar_cache_checked_at = CURRENT_TIMESTAMP,
                    avatar_cache_error = ''
                WHERE account_id = ?
                """,
                (result.local_path, account_id),
            )
        else:
            conn.execute(
                """
                UPDATE accounts
                SET avatar_cache_checked_at = CURRENT_TIMESTAMP,
                    avatar_cache_error = ?
                WHERE account_id = ?
                """,
                (result.error or "avatar cache failed", account_id),
            )
    return {
        "ok": bool(result.local_path),
        "account_id": account_id,
        "avatar_local_path": result.local_path,
        "avatar_local_url": avatar_public_url(result.local_path) if result.local_path else "",
        "error": result.error,
    }


@app.delete("/api/accounts/{account_id:path}")
def delete_account(account_id: str) -> dict[str, object]:
    initialize_database(APP_DB)
    try:
        result = delete_platform_account_node(APP_DB, account_id)
        platform = _platform_for_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    metrics = analyze_graph(APP_DB)
    rendered = render_graph_html(APP_DB, APP_GRAPH, api_enabled=True, source_platform=platform)
    return {
        "ok": True,
        "deleted": result,
        "metrics": metrics,
        "graph": rendered["output"],
    }


@app.post("/api/account-orphans/{account_id:path}/prune")
def prune_account_orphans(account_id: str) -> dict[str, object]:
    initialize_database(APP_DB)
    try:
        result = prune_adjacent_orphan_nodes(APP_DB, account_id)
        platform = _platform_for_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    metrics = analyze_graph(APP_DB)
    rendered = render_graph_html(APP_DB, APP_GRAPH, center_id=account_id, api_enabled=True, source_platform=platform)
    return {
        "ok": True,
        "pruned": result,
        "metrics": metrics,
        "graph": rendered["output"],
    }


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    with connect(APP_DB) as conn:
        row = conn.execute(
            """
            SELECT j.*, t.status AS target_status, t.crawl_count,
                   t.last_crawled_at, t.last_imported_at
            FROM crawl_jobs j
            LEFT JOIN crawl_targets t ON t.target_id = j.target_id
            WHERE j.job_id = ?
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = dict(row)
    payload["done"] = payload["status"] in {"completed", "failed"}
    log_tail = _read_log_tail(payload.get("log_path") or "")
    payload["log_tail"] = log_tail
    payload["detail"] = _job_detail(payload, log_tail)
    return payload


@app.get("/api/targets/{target_id:path}")
def target_status(target_id: str) -> dict[str, object]:
    with connect(APP_DB) as conn:
        row = conn.execute("SELECT * FROM crawl_targets WHERE target_id = ?", (target_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return dict(row)


def _read_log_tail(log_path: str, limit: int = 4000) -> str:
    if not log_path:
        return ""
    path = Path(log_path)
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def _platform_for_account(account: str, hint: str = "") -> str:
    return detect_platform(account, hint).platform_id


def _with_avatar_public_url(account: dict[str, object]) -> dict[str, object]:
    local_path = str(account.get("avatar_local_path") or "")
    account["avatar_local_url"] = avatar_public_url(local_path) if local_path else ""
    return account


def _job_detail(payload: dict[str, object], log_tail: str) -> str:
    status = payload.get("status")
    if status == "completed":
        return "已完成：数据已导入、建边、分析并重新渲染图谱。 / Completed: imported, analyzed, and rendered."
    if status == "failed":
        error_text = f"{payload.get('error') or ''}\n{log_tail}"
        if "Cannot connect to existing browser on port 9222" in log_tail:
            return "失败：无法连接 Pi 上的 Chromium CDP 9222 端口。请保持 Chromium 以远程调试模式运行。 / Failed: Chromium CDP 9222 is not reachable."
        if "Executable doesn't exist" in log_tail and "playwright install" in log_tail:
            return "失败：CDP 不可用，且 Playwright fallback 浏览器未安装。请重新打开远程调试 Chromium，或安装 Playwright 浏览器。 / Failed: CDP unavailable and fallback browser is missing."
        if _is_profile_session_error(error_text):
            return _profile_session_detail(payload)
        if "Login state result: False" in log_tail or "login failed , have not found qrcode" in log_tail or "qrcode-img" in log_tail:
            return _profile_session_detail(payload)
        latest = _latest_log_line(log_tail)
        return f"失败：{latest or payload.get('error') or '请查看日志。'} / Failed: check the latest log."
    latest = _latest_log_line(log_tail)
    if "stage=browser" in latest:
        return "正在准备浏览器：检查或启动本地 Chromium，并复用长期登录 profile。 / Preparing local Chromium with persistent login profile."
    if "stage=minimal-adapter" in latest:
        return "正在采集：OSGE minimal adapter 正在抓取该账号的作品和评论。 / Crawling with the OSGE minimal adapter."
    if "stage=minimal-sync" in latest or "stage=graph-sync" in latest:
        return "正在同步图谱：写入 OSGE overlay 并应用身份/图谱状态。 / Syncing graph data through the OSGE overlay."
    if "stage=edges" in latest:
        return "正在建边：根据评论/回复生成关系边。 / Building relation edges."
    if "stage=analyze" in latest:
        return "正在分析：计算 PageRank、加权度和社区。 / Analyzing graph metrics."
    if "stage=render" in latest:
        return "正在渲染：生成新的图谱页面。 / Rendering the graph."
    return "正在排队或运行任务。 / Job is queued or running."


def _is_profile_session_error(text: str) -> bool:
    return PROFILE_SESSION_ERROR_MARKER in text


def _profile_session_detail(payload: dict[str, object]) -> str:
    platform = _platform_display_name(str(payload.get("platform") or "platform"))
    return (
        f"失败：未能获取 {platform} profile。当前 OSGE Chromium 会话未登录，或被平台验证/风控拦截。"
        f"请在打开的 Chromium 页面中打开 {platform}，完成登录或验证，确认页面可正常访问后再重试采集。 / "
        f"Failed: {platform} profile could not be fetched. Log in or complete verification in the current OSGE Chromium window, then retry."
    )


def _platform_display_name(platform: str) -> str:
    return platform_display_name(platform)


def _latest_log_line(log_tail: str) -> str:
    lines = [line.strip() for line in log_tail.splitlines() if line.strip()]
    return lines[-1] if lines else ""
