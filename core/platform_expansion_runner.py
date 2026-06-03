from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from pathlib import Path

from adapters.minimal_platform import MinimalAdapterConfig
from adapters.registry import PlatformDefinition, get_platform
from core.chromium_cdp import ensure_chromium_cdp
from core.crawl_state import begin_crawl_job, ensure_crawl_target, finish_crawl_job, should_skip_crawl, target_id
from core.db import DEFAULT_DB_PATH, PROJECT_ROOT, connect, initialize_database
from core.edge_builder import build_edges
from core.graph_renderer import render_graph_html
from core.minicrawler import (
    build_incremental_crawl_plan,
    known_comment_ids,
    sync_comment_records,
    sync_profile_post_records,
)


DEFAULT_GRAPH = PROJECT_ROOT / "data" / "processed" / "osge_graph.html"


@dataclass(frozen=True)
class PreparedPlatformExpansion:
    platform: str
    account: str
    platform_user_id: str
    target_id: str
    profile_url: str
    db_path: Path
    graph_output: Path
    max_notes: int
    max_comments: int
    get_sub_comments: bool
    force: bool
    requested_by: str
    log_path: Path
    incremental_plan: dict[str, object]
    job_id: str | None = None
    skipped: bool = False
    reason: str = ""


def prepare_platform_expansion(
    platform: str,
    account: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    graph_output: Path | str = DEFAULT_GRAPH,
    max_notes: int = 5,
    max_comments: int = 10,
    get_sub_comments: bool = False,
    force: bool = False,
    requested_by: str = "cli",
    create_job: bool = True,
) -> PreparedPlatformExpansion:
    definition = get_platform(platform)
    platform_user_id, profile_url = definition.normalize_profile_input(account)
    tid = target_id(definition.platform_id, platform_user_id)
    db = Path(db_path)
    graph = Path(graph_output)

    initialize_database(db)
    ensure_crawl_target(db, definition.platform_id, platform_user_id, profile_url)
    hidden_before_crawl = _is_account_hidden(db, tid)
    skip, reason = should_skip_crawl(db, tid, force=force)
    if skip and "already crawled/imported" in reason:
        skip = False
        reason = "incremental refresh requested for previously crawled target"
    if hidden_before_crawl and skip and "already crawled/imported" in reason:
        skip = False
        reason = "hidden account recrawl requested"

    incremental_plan = build_incremental_crawl_plan(
        db,
        platform=definition.platform_id,
        target_account_id=tid,
        max_notes=max_notes,
        max_comments=max_comments,
        get_sub_comments=get_sub_comments,
    ).as_dict()
    log_path = _crawl_log_path(definition, platform_user_id)

    prepared = PreparedPlatformExpansion(
        platform=definition.platform_id,
        account=account,
        platform_user_id=platform_user_id,
        target_id=tid,
        profile_url=profile_url,
        db_path=db,
        graph_output=graph,
        max_notes=max_notes,
        max_comments=max_comments,
        get_sub_comments=get_sub_comments,
        force=force,
        requested_by=requested_by,
        log_path=log_path,
        incremental_plan=incremental_plan,
        skipped=skip,
        reason=reason,
    )
    if skip or not create_job:
        return prepared

    notes_before, comments_before = osge_counts(db, definition.platform_id, tid)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    job_id = begin_crawl_job(
        db_path=db,
        tid=tid,
        platform=definition.platform_id,
        profile_url=profile_url,
        source_db=f"osge:minimal-adapter:{definition.platform_id}",
        output_db=str(db),
        graph_output=str(graph),
        log_path=str(log_path),
        max_notes=max_notes,
        max_comments=max_comments,
        get_sub_comments=get_sub_comments,
        force=force,
        notes_before=notes_before,
        comments_before=comments_before,
        requested_by=requested_by,
    )
    return replace(prepared, job_id=job_id, skipped=False)


def run_prepared_platform_expansion(prepared: PreparedPlatformExpansion) -> dict[str, object]:
    if prepared.skipped:
        return {
            "target_id": prepared.target_id,
            "skipped": True,
            "reason": prepared.reason,
        }
    if prepared.job_id is None:
        raise ValueError("Prepared expansion is missing job_id")
    definition = get_platform(prepared.platform)

    try:
        with prepared.log_path.open("w", encoding="utf-8") as handle:
            handle.write(f"[OSGE] stage=browser ensuring local Chromium CDP target={prepared.target_id}\n")
            handle.flush()
            cdp_status = ensure_chromium_cdp(log_path=PROJECT_ROOT / "logs" / "chromium_cdp.log")
            if not cdp_status.ok:
                raise RuntimeError(f"Chromium CDP is not available: {cdp_status.error}")
            handle.write(
                "[OSGE] stage=browser-ready "
                f"port={cdp_status.port} started={cdp_status.started} "
                f"browser={cdp_status.browser or 'unknown'} profile={cdp_status.profile_dir}\n"
            )
            handle.flush()
            handle.write(
                "[OSGE] stage=minimal-adapter "
                f"platform={prepared.platform} target={prepared.target_id} "
                f"max_notes={prepared.max_notes} max_comments={prepared.max_comments}\n"
            )
            handle.write(f"[OSGE] stage=incremental-plan {prepared.incremental_plan}\n")
            handle.flush()
            profile, posts, comment_records = asyncio.run(_crawl_with_minimal_adapter(prepared, definition))

        restored_hidden: list[str] = []
        minimal_result = sync_profile_post_records(
            prepared.db_path,
            prepared.platform,
            profile,
            posts,
            target_account_id=prepared.target_id,
        )
        minimal_result["interactions"] = sync_comment_records(
            prepared.db_path,
            prepared.platform,
            comment_records,
            target_account_id=prepared.target_id,
            crawl_job_id=prepared.job_id,
        )
        _append_log(prepared.log_path, f"[OSGE] stage=minimal-sync result={minimal_result}")
        edge_result = build_edges(prepared.db_path)
        graph_result = {"db_edges": edge_result["edges"], "db_evidences": edge_result["evidences"], **edge_result}
        _append_log(prepared.log_path, f"[OSGE] stage=render rendering graph metrics={graph_result}")
        render_result = render_graph_html(
            prepared.db_path,
            prepared.graph_output,
            center_id=prepared.target_id,
            api_enabled=True,
            source_platform=prepared.platform,
        )
        notes_after, comments_after = osge_counts(prepared.db_path, prepared.platform, prepared.target_id)
        _append_log(
            prepared.log_path,
            f"[OSGE] stage=completed {definition.item_label}={notes_after} comments={comments_after}",
        )
        finish_crawl_job(prepared.db_path, prepared.job_id, prepared.target_id, "completed", notes_after, comments_after)
    except Exception as exc:
        notes_after, comments_after = osge_counts(prepared.db_path, prepared.platform, prepared.target_id)
        _append_log(prepared.log_path, f"[OSGE] stage=failed error={exc}")
        finish_crawl_job(prepared.db_path, prepared.job_id, prepared.target_id, "failed", notes_after, comments_after, error=str(exc))
        raise

    return {
        "job_id": prepared.job_id,
        "target_id": prepared.target_id,
        "skipped": False,
        "source": {"notes": notes_after, "comments": comments_after},
        "edges": {"edges": graph_result["db_edges"], "evidences": graph_result["db_evidences"]},
        "graph": graph_result,
        "incremental_plan": prepared.incremental_plan,
        "minimal": minimal_result,
        "rendered": render_result["output"],
        "restored_hidden": restored_hidden,
        "notes_after": notes_after,
        "comments_after": comments_after,
        "log_path": str(prepared.log_path),
    }


def expand_platform_account(platform: str, **kwargs: object) -> dict[str, object]:
    prepared = prepare_platform_expansion(platform, **kwargs)
    return run_prepared_platform_expansion(prepared)


def update_platform_profile(
    platform: str,
    account: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    graph_output: Path | str = DEFAULT_GRAPH,
) -> dict[str, object]:
    definition = get_platform(platform)
    platform_user_id, profile_url = definition.normalize_profile_input(account)
    db = Path(db_path)
    graph = Path(graph_output)
    target = target_id(definition.platform_id, platform_user_id)

    initialize_database(db)
    ensure_crawl_target(db, definition.platform_id, platform_user_id, profile_url)
    cdp_status = ensure_chromium_cdp(log_path=PROJECT_ROOT / "logs" / "chromium_cdp.log")
    if not cdp_status.ok:
        raise RuntimeError(f"Chromium CDP is not available: {cdp_status.error}")

    profile = asyncio.run(_fetch_profile_with_minimal_adapter(definition, profile_url))
    minimal_result = sync_profile_post_records(
        db,
        definition.platform_id,
        profile,
        [],
        target_account_id=target,
    )
    graph_result = build_edges(db)
    render_result = render_graph_html(db, graph, center_id=target, api_enabled=True, source_platform=definition.platform_id)
    return {
        "ok": True,
        "target_id": target,
        "platform": definition.platform_id,
        "profile_url": profile_url,
        "minimal": minimal_result,
        "graph": graph_result,
        "rendered": render_result["output"],
    }


async def _fetch_profile_with_minimal_adapter(definition: PlatformDefinition, profile_url: str):
    adapter = definition.create_adapter(MinimalAdapterConfig())
    return await adapter.fetch_profile(profile_url)


async def _crawl_with_minimal_adapter(prepared: PreparedPlatformExpansion, definition: PlatformDefinition):
    adapter = definition.create_adapter(MinimalAdapterConfig())
    platform_context = definition.context_from_url(prepared.profile_url)
    async with adapter.browser_session() as session:
        profile = await adapter.fetch_profile_in_session(session, prepared.profile_url)
        posts = await adapter.fetch_posts_in_session(
            session,
            prepared.platform_user_id,
            prepared.max_notes,
            platform_context=platform_context,
        )
        comments = []
        if prepared.force or prepared.incremental_plan.get("should_get_comments"):
            for post in posts:
                comment_context = post.platform_context if definition.requires_comment_context else {}
                if definition.requires_comment_context and not comment_context:
                    continue
                known = (
                    set()
                    if prepared.force
                    else known_comment_ids(
                        prepared.db_path,
                        platform=prepared.platform,
                        platform_post_ids=[post.platform_post_id],
                    )
                )
                result = await adapter.fetch_comments_in_session(
                    session,
                    post.platform_post_id,
                    prepared.max_comments,
                    platform_context=comment_context,
                    get_sub_comments=prepared.get_sub_comments,
                    known_comment_ids=known,
                )
                comments.extend(result.comments)
    return profile, posts, comments


def osge_counts(db_path: Path | str, platform: str, target_account_id: str) -> tuple[int, int]:
    with connect(db_path) as conn:
        notes = conn.execute(
            """
            SELECT COUNT(*)
            FROM posts
            WHERE platform = ?
              AND author_account_id = ?
            """,
            (platform, target_account_id),
        ).fetchone()[0]
        comments = conn.execute(
            """
            SELECT COUNT(DISTINCT i.source_record_id)
            FROM interactions i
            JOIN posts p ON p.post_id = i.post_id
            WHERE i.platform = ?
              AND p.author_account_id = ?
              AND i.source_record_id IS NOT NULL
              AND i.source_record_id != ''
              AND i.interaction_type IN ('comment', 'reply')
            """,
            (platform, target_account_id),
        ).fetchone()[0]
    return int(notes or 0), int(comments or 0)


def _crawl_log_path(definition: PlatformDefinition, platform_user_id: str) -> Path:
    log_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", platform_user_id)
    return PROJECT_ROOT / "data" / "processed" / "crawl_logs" / f"{definition.log_prefix}{log_name}.log"


def _is_account_hidden(db_path: Path | str, account_id: str) -> bool:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ? AND hidden_at IS NOT NULL LIMIT 1",
            (account_id,),
        ).fetchone()
    return row is not None


def _append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")
