from __future__ import annotations

import json
import logging
import re
import time
import uuid
import hashlib
from pathlib import Path
from typing import Any

import requests
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.models.schemas import (
    DocsResponse,
    HealthResponse,
    JobStatus,
    RepoInput,
    TokenVerifyInput,
    TokenVerifyResponse,
    ReviewResponse,
    WebhookAck,
)
from backend.services.doc_service import DocumentationService
from backend.services.ingestion import (
    IngestionError,
    cleanup_workspace,
    create_workspace,
    ingest_from_url,
    ingest_zip_bytes,
)
from backend.services.review_service import ReviewService
from backend.services.state_store import StateStore
from backend.services.token_crypto import decrypt_token, encrypt_token
from backend.utils.settings import settings
from docs.parser import parse_repository
from docs.repo_loader import TEXT_EXTENSIONS, iter_code_files
from github.commenter import (
    format_inline_comments,
    post_pr_review,
    push_readme_to_github,
    verify_docs_token_access,
)
from github.diff_fetcher import GitHubDiffError, fetch_pr_diff
from github.pr_handler import build_virtual_files_from_diff
from github.webhook import SignatureValidationError, validate_github_signature
from rag.rag_pipeline import RAGPipeline

# ── App setup ─────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Developer Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Services & state ──────────────────────────────────────────────────────────

rag_pipeline = RAGPipeline()
review_service = ReviewService(rag_pipeline)
doc_service = DocumentationService(rag_pipeline)
state_store = StateStore()


@app.on_event("startup")
async def on_startup() -> None:
    logger.info(
        "Server started | host=%s port=%s keep_workspaces=%s nim_enabled=%s models=[%s, %s, %s]",
        settings.backend_host,
        settings.backend_port,
        settings.keep_workspaces,
        bool(settings.nim_api_key),
        settings.nim_model_neotron,
        settings.nim_model_qwen_docs,
        settings.nim_model_qwen_review,
    )


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    logger.info("API call started | method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "API call completed | method=%s path=%s status=%s elapsed_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.exception(
            "API call failed | method=%s path=%s elapsed_ms=%d",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        cache_runs=0,
        rag_chunks=len(rag_pipeline.store.items),
    )


# ── Job polling ───────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str) -> JobStatus:
    """Poll this endpoint until status == 'done' or 'error'."""
    job = state_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        message=job.get("message", ""),
        result=job.get("result"),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_workspace(repo_root: Path) -> list[dict[str, Any]]:
    files = iter_code_files(repo_root)
    logger.info("Workspace scan complete | root=%s supported_files=%d", repo_root, len(files))
    if not files:
        supported = ", ".join(sorted(TEXT_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=(
                "No supported source files found in repository. "
                f"Supported extensions: {supported}"
            ),
        )
    parsed = parse_repository(files)
    for item in parsed:
        raw_path = item.get("path", "")
        try:
            item["path"] = Path(raw_path).resolve().relative_to(repo_root.resolve()).as_posix()
        except Exception:
            item["path"] = Path(raw_path).name
    logger.info("Repository parse complete | parsed_files=%d", len(parsed))
    return parsed


def _extract_repo_name(repo_url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub URL."""
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+)", repo_url)
    if not m:
        return None
    return m.group(1).removesuffix(".git")


def _build_result_cache_key(mode: str, repo_url: str, persona: str) -> str:
    normalized = repo_url.strip().lower()
    digest = hashlib.sha256(f"{mode}|{normalized}|{persona}".encode("utf-8")).hexdigest()
    return f"{mode}:{digest}"


def _is_pr_open(repo_full_name: str, pr_number: int, token: str) -> bool:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code >= 400:
            logger.warning(
                "PR state check failed for %s#%d: HTTP %d",
                repo_full_name,
                pr_number,
                resp.status_code,
            )
            # Fail-open to avoid dropping comments during transient GH API issues.
            return True
        state = str(resp.json().get("state", "")).lower()
        return state == "open"
    except Exception as exc:
        logger.warning("PR state check exception for %s#%d: %s", repo_full_name, pr_number, exc)
        # Fail-open for resilience.
        return True


def _resolve_docs_token(encrypted_docs_token: str | None) -> str:
    docs_token = settings.github_docs_token
    if encrypted_docs_token:
        try:
            docs_token = decrypt_token(encrypted_docs_token)
        except ValueError:
            logger.warning("Invalid encrypted docs token payload")
    return docs_token


def _push_readme_if_available(
    repo_full_name: str | None,
    readme_content: str | None,
    encrypted_docs_token: str | None,
) -> None:
    if not repo_full_name or not readme_content:
        return
    docs_token = _resolve_docs_token(encrypted_docs_token)
    if not docs_token:
        logger.warning("No docs token available — skipping README push to %s", repo_full_name)
        return
    pushed = push_readme_to_github(
        repo_full_name=repo_full_name,
        token=docs_token,
        readme_content=readme_content,
    )
    logger.info("README push to %s: %s", repo_full_name, "OK" if pushed else "failed")


# ── Background job workers ────────────────────────────────────────────────────

async def _job_review(
    job_id: str,
    persona: str,
    workspace: Path,
    repo_root: Path,
    result_cache_key: str | None = None,
) -> None:
    try:
        logger.info("Job started | type=review job_id=%s persona=%s", job_id, persona)
        parsed_files = _parse_workspace(repo_root)
        state_store.set_job(job_id, {"status": "processing", "message": "Review processing started", "result": None})
        logger.info("Job phase | type=review job_id=%s phase=model_processing", job_id)
        result = await review_service.review(parsed_files, persona)
        run_id = str(uuid.uuid4())
        response = ReviewResponse(run_id=run_id, persona=persona, **result)  # type: ignore[arg-type]
        response_payload = response.model_dump()
        state_store.set_run(run_id, response_payload)
        state_store.set_job(job_id, {"status": "done", "result": response_payload, "message": "Review complete"})
        if result_cache_key:
            state_store.set_result_cache(result_cache_key, response_payload)
        logger.info("Job completed | type=review job_id=%s run_id=%s", job_id, run_id)
    except Exception as exc:
        logger.exception("Job %s (review) failed: %s", job_id, exc)
        state_store.set_job(job_id, {"status": "error", "message": str(exc), "result": None})
    finally:
        if not settings.keep_workspaces:
            cleanup_workspace(workspace)


async def _job_docs(
    job_id: str,
    persona: str,
    workspace: Path,
    repo_root: Path,
    repo_full_name: str | None = None,
    encrypted_docs_token: str | None = None,
    result_cache_key: str | None = None,
) -> None:
    try:
        logger.info("Job started | type=docs job_id=%s persona=%s repo=%s", job_id, persona, repo_full_name or "upload")
        parsed_files = _parse_workspace(repo_root)
        state_store.set_job(job_id, {"status": "processing", "message": "Docs processing started", "result": None})
        logger.info("Job phase | type=docs job_id=%s phase=model_processing", job_id)
        result = await doc_service.generate(parsed_files, persona)
        run_id = str(uuid.uuid4())
        response = DocsResponse(run_id=run_id, persona=persona, **result)  # type: ignore[arg-type]
        response_payload = response.model_dump()
        state_store.set_run(run_id, response_payload)
        state_store.set_job(job_id, {"status": "done", "result": response_payload, "message": "Docs generated"})
        if result_cache_key:
            state_store.set_result_cache(result_cache_key, response_payload)
        logger.info("Job completed | type=docs job_id=%s run_id=%s", job_id, run_id)

        _push_readme_if_available(repo_full_name, result.get("readme"), encrypted_docs_token)

    except Exception as exc:
        logger.exception("Job %s (docs) failed: %s", job_id, exc)
        state_store.set_job(job_id, {"status": "error", "message": str(exc), "result": None})
    finally:
        if not settings.keep_workspaces:
            cleanup_workspace(workspace)


# ── Review endpoints ──────────────────────────────────────────────────────────

@app.post("/api/review/repo", response_model=JobStatus)
def review_repo(payload: RepoInput, background_tasks: BackgroundTasks) -> JobStatus:
    logger.info("API payload accepted | endpoint=/api/review/repo repo_url=%s persona=%s", payload.repo_url, payload.persona)
    result_cache_key = _build_result_cache_key("review", payload.repo_url, payload.persona)
    cached = state_store.get_result_cache(result_cache_key)
    if cached:
        return JobStatus(job_id="cached-review", status="done", message="Review served from cache", result=cached)
    workspace = create_workspace()
    try:
        repo_root = ingest_from_url(payload.repo_url, workspace, github_token=settings.github_review_token)
    except IngestionError as exc:
        cleanup_workspace(workspace)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    state_store.set_job(job_id, {"status": "processing", "message": "Review queued", "result": None})
    background_tasks.add_task(_job_review, job_id, payload.persona, workspace, repo_root, result_cache_key)
    logger.info("Job queued | type=review source=repo job_id=%s", job_id)
    return JobStatus(job_id=job_id, status="processing", message="Review queued — poll /api/jobs/{job_id}")


@app.post("/api/review/upload", response_model=JobStatus)
async def review_upload(
    background_tasks: BackgroundTasks,
    persona: str = Form(...),
    file: UploadFile = File(...),
) -> JobStatus:
    logger.info("API payload accepted | endpoint=/api/review/upload persona=%s filename=%s", persona, file.filename)
    blob = await file.read()
    workspace = create_workspace()
    try:
        repo_root = ingest_zip_bytes(blob, workspace)
    except IngestionError as exc:
        cleanup_workspace(workspace)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    state_store.set_job(job_id, {"status": "processing", "message": "Review queued", "result": None})
    background_tasks.add_task(_job_review, job_id, persona, workspace, repo_root)
    logger.info("Job queued | type=review source=upload job_id=%s", job_id)
    return JobStatus(job_id=job_id, status="processing", message="Review queued — poll /api/jobs/{job_id}")


# ── Docs endpoints ────────────────────────────────────────────────────────────

@app.post("/api/docs/repo", response_model=JobStatus)
def docs_repo(payload: RepoInput, background_tasks: BackgroundTasks) -> JobStatus:
    logger.info("API payload accepted | endpoint=/api/docs/repo repo_url=%s persona=%s", payload.repo_url, payload.persona)
    repo_full_name = _extract_repo_name(payload.repo_url)
    # Always regenerate docs for repo runs so README quality updates are reflected immediately.
    result_cache_key = None
    workspace = create_workspace()
    try:
        repo_root = ingest_from_url(payload.repo_url, workspace, github_token=settings.github_review_token)
    except IngestionError as exc:
        cleanup_workspace(workspace)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    state_store.set_job(job_id, {"status": "processing", "message": "Docs generation queued", "result": None})
    background_tasks.add_task(
        _job_docs,
        job_id,
        payload.persona,
        workspace,
        repo_root,
        repo_full_name,
        payload.encrypted_docs_token,
        result_cache_key,
    )
    logger.info("Job queued | type=docs source=repo job_id=%s repo=%s", job_id, repo_full_name or "unknown")
    msg = f"Docs queued — README will be pushed to {repo_full_name}" if repo_full_name else "Docs queued"
    return JobStatus(job_id=job_id, status="processing", message=msg)


@app.post("/api/github/verify-docs-token", response_model=TokenVerifyResponse)
def verify_docs_token(payload: TokenVerifyInput) -> TokenVerifyResponse:
    repo_full_name = _extract_repo_name(payload.repo_url)
    if not repo_full_name:
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")

    valid, default_branch, message = verify_docs_token_access(repo_full_name, payload.token)
    if not valid:
        return TokenVerifyResponse(
            valid=False,
            repo_full_name=repo_full_name,
            default_branch=default_branch or None,
            message=message,
        )

    return TokenVerifyResponse(
        valid=True,
        repo_full_name=repo_full_name,
        default_branch=default_branch or None,
        encrypted_token=encrypt_token(payload.token),
        message=message,
    )


@app.post("/api/docs/upload", response_model=JobStatus)
async def docs_upload(
    background_tasks: BackgroundTasks,
    persona: str = Form(...),
    file: UploadFile = File(...),
) -> JobStatus:
    logger.info("API payload accepted | endpoint=/api/docs/upload persona=%s filename=%s", persona, file.filename)
    blob = await file.read()
    workspace = create_workspace()
    try:
        repo_root = ingest_zip_bytes(blob, workspace)
    except IngestionError as exc:
        cleanup_workspace(workspace)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = str(uuid.uuid4())
    state_store.set_job(job_id, {"status": "processing", "message": "Docs generation queued", "result": None})
    background_tasks.add_task(_job_docs, job_id, persona, workspace, repo_root)
    logger.info("Job queued | type=docs source=upload job_id=%s", job_id)
    return JobStatus(job_id=job_id, status="processing", message="Docs queued — poll /api/jobs/{job_id}")


# ── GitHub webhook ────────────────────────────────────────────────────────────

async def _run_pr_review_background(
    repo_name: str,
    pr_number: int,
    run_id: str,
) -> None:
    """Background task: fetch diff → review → post comments."""
    try:
        diff_text = fetch_pr_diff(repo_name, pr_number, settings.github_review_token)
    except GitHubDiffError as exc:
        logger.warning("PR review: diff fetch failed for %s#%d: %s", repo_name, pr_number, exc)
        return

    parsed_files = build_virtual_files_from_diff(diff_text)
    if not parsed_files:
        logger.info("PR review: no reviewable files in diff for %s#%d", repo_name, pr_number)
        return

    try:
        result = await review_service.review_pr_fast(parsed_files, persona="Backend Developer")
    except Exception as exc:
        logger.exception("PR review: review_service failed for %s#%d: %s", repo_name, pr_number, exc)
        return

    if not _is_pr_open(repo_name, pr_number, settings.github_review_token):
        logger.info("PR review skipped posting because PR is closed: %s#%d", repo_name, pr_number)
        return

    state_store.set_run(run_id, {
        "type": "github_pr_review",
        "repo": repo_name,
        "pr_number": pr_number,
        "review": result,
        "comments": format_inline_comments(result["findings"]),
    })

    posted = post_pr_review(
        repo_full_name=repo_name,
        pr_number=pr_number,
        token=settings.github_review_token,
        findings=result["findings"],
        summary=result.get("summary", ""),
    )
    logger.info(
        "PR review done for %s#%d — %d findings, posted: %s",
        repo_name, pr_number, len(result["findings"]), posted,
    )


@app.post("/api/github/webhook", response_model=WebhookAck)
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> WebhookAck:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event = request.headers.get("X-GitHub-Event", "")
    logger.info("GitHub webhook received | event=%s", event)

    try:
        validate_github_signature(raw_body, settings.github_webhook_secret, signature)
    except SignatureValidationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if event != "pull_request":
        return WebhookAck(accepted=True, action="ignored", message=f"Event {event!r} ignored")

    action = payload.get("action", "")
    logger.info("GitHub webhook action | event=%s action=%s", event, action)
    if action not in {"opened", "synchronize", "reopened"}:
        logger.info("GitHub webhook ignored | unsupported action=%s", action)
        return WebhookAck(accepted=True, action="ignored", message=f"Action {action!r} ignored")

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name")
    pr_number = pr.get("number")

    if not repo_name or not pr_number:
        raise HTTPException(status_code=400, detail="Invalid pull_request payload")
    logger.info("GitHub webhook PR payload parsed | repo=%s pr=%s", repo_name, pr_number)

    if not settings.github_review_token:
        logger.warning("GITHUB_REVIEW_TOKEN not set — cannot post PR review for %s#%d", repo_name, pr_number)
        return WebhookAck(accepted=True, action="ignored", message="No review token configured")

    run_id = str(uuid.uuid4())
    background_tasks.add_task(_run_pr_review_background, repo_name, pr_number, run_id)
    logger.info("GitHub webhook queued PR review | repo=%s pr=%s run_id=%s", repo_name, pr_number, run_id)

    return WebhookAck(
        accepted=True,
        action=action,
        message="PR queued for review — comment will appear shortly.",
        run_id=run_id,
    )
