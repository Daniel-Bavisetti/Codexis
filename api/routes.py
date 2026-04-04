import os
import shutil
import subprocess
import tempfile
import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from starlette.responses import JSONResponse
from services.pipeline import run_pipeline, run_analysis
from services.requirements_store import get_requirements_snapshot, save_requirements_snapshot
from services.change_manager import (
    apply_diff,
    clear_codebase_dependent_state,
    get_changes,
    read_runtime_state,
    sync_codebase_runtime_state,
    update_status,
)

router = APIRouter()

DEFAULT_CODEBASE_PATH = "data/codebase"
LOCAL_APPDATA_PATH = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
PERSISTENT_REPO_ROOT = Path(os.environ.get("REQ_TO_CODE_REPO_ROOT") or (LOCAL_APPDATA_PATH / "ReqToCode" / "github-repos"))

class RejectReq(BaseModel):
    comment: str

class CodebaseSourceReq(BaseModel):
    type: str
    path: str | None = None
    repo_url: str | None = None
    branch: str = "main"

class AnalyzeReq(BaseModel):
    path: str = DEFAULT_CODEBASE_PATH
    codebase_source: CodebaseSourceReq | None = None

class PipelineReq(BaseModel):
    code_path: str = DEFAULT_CODEBASE_PATH
    requirements_text: str | None = None
    requirements_path: str = "data/reqs.json"
    codebase_source: CodebaseSourceReq | None = None


class CodebaseChangeReq(BaseModel):
    source_key: str | None = None
    codebase_path: str | None = None
    source_type: str | None = None
    repo_url: str | None = None
    branch: str | None = None


class SaveRequirementsReq(BaseModel):
    raw_text: str
    mode: str | None = None
    source_key: str | None = None
    source_type: str | None = None
    source_label: str | None = None


@dataclass
class ResolvedCodebase:
    path: str
    cleanup_path: str | None = None


def _run_git_clone(repo_url: str, destination: str, branch: str | None = None) -> None:
    branch_label = branch or "<default>"
    print(f"[github-clone] starting repo={repo_url} branch={branch_label} destination={destination}")
    command = ["git", "clone", "--depth", "1"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([repo_url, destination])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    stderr = (result.stderr or "").strip()
    if stderr:
        print(f"[github-clone] git output: {stderr}")
    print(f"[github-clone] completed repo={repo_url} branch={branch_label}")


def _run_git_command(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    cwd_label = cwd or "<none>"
    print(f"[github-clone] git {' '.join(args)} cwd={cwd_label}")
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    stderr = (result.stderr or "").strip()
    if stderr:
        print(f"[github-clone] git output: {stderr}")
    return result


def _sanitize_path_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "repo"


def _repo_storage_directory(repo_url: str, branch: str) -> Path:
    parsed = urlparse(repo_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    owner = _sanitize_path_part(path_parts[0]) if len(path_parts) >= 2 else "github"
    repo_name = _sanitize_path_part(path_parts[-1].removesuffix(".git")) if path_parts else "repo"
    branch_part = _sanitize_path_part(branch or "default")
    repo_hash = hashlib.sha1(f"{repo_url}::{branch}".encode("utf-8")).hexdigest()[:8]
    return PERSISTENT_REPO_ROOT / f"{owner}__{repo_name}__{branch_part}__{repo_hash}"


def _get_remote_default_branch(repo_url: str) -> str | None:
    try:
        result = _run_git_command(["ls-remote", "--symref", repo_url, "HEAD"])
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or str(exc)).strip()
        print(f"[github-clone] unable to detect default branch for repo={repo_url}: {stderr}")
        return None

    for line in result.stdout.splitlines():
        if line.startswith("ref: ") and "\tHEAD" in line:
            ref = line.split("\t", 1)[0].split("ref: ", 1)[1].strip()
            if ref.startswith("refs/heads/"):
                return ref.split("refs/heads/", 1)[1]
    return None


def _clone_or_update_github_repo(repo_url: str, branch: str) -> tuple[str, str]:
    PERSISTENT_REPO_ROOT.mkdir(parents=True, exist_ok=True)
    target_dir = _repo_storage_directory(repo_url, branch)
    target_dir_str = str(target_dir)
    requested_branch = branch.strip() or "main"
    active_branch = requested_branch

    print(f"[github-clone] using persistent repo store root={PERSISTENT_REPO_ROOT}")
    print(f"[github-clone] target directory={target_dir_str}")

    def sync_branch(branch_name: str) -> None:
        _run_git_command(["remote", "set-url", "origin", repo_url], cwd=target_dir_str)
        _run_git_command(["fetch", "--depth", "1", "origin", branch_name], cwd=target_dir_str)
        _run_git_command(["checkout", "-B", branch_name, "FETCH_HEAD"], cwd=target_dir_str)

    if (target_dir / ".git").exists():
        print(f"[github-clone] existing clone found at {target_dir_str}, updating in place")
        try:
            sync_branch(requested_branch)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or str(exc)).strip()
            branch_not_found = "couldn't find remote ref" in stderr.lower() or ("remote branch" in stderr.lower() and "not found" in stderr.lower())
            if not branch_not_found:
                raise RuntimeError(f"GitHub clone failed: {stderr}") from exc

            default_branch = _get_remote_default_branch(repo_url)
            if not default_branch:
                raise RuntimeError(f"GitHub clone failed: {stderr}") from exc

            print(f"[github-clone] requested branch {requested_branch} missing; using default branch {default_branch}")
            sync_branch(default_branch)
            active_branch = default_branch
        return target_dir_str, active_branch

    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

    try:
        _run_git_clone(repo_url, target_dir_str, branch=requested_branch)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or str(exc)).strip()
        branch_not_found = "remote branch" in stderr.lower() and "not found" in stderr.lower()
        if not branch_not_found:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"GitHub clone failed: {stderr}") from exc

        default_branch = _get_remote_default_branch(repo_url)
        if not default_branch:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"GitHub clone failed: {stderr}") from exc

        print(f"[github-clone] requested branch {requested_branch} missing; cloning default branch {default_branch}")
        shutil.rmtree(target_dir, ignore_errors=True)
        _run_git_clone(repo_url, target_dir_str, branch=default_branch)
        active_branch = default_branch

    return target_dir_str, active_branch


def _normalize_directory_path(path: str | None) -> str:
    raw_path = path or os.path.expanduser("~")
    expanded_path = os.path.abspath(os.path.expanduser(raw_path))
    if not os.path.exists(expanded_path):
        raise HTTPException(status_code=404, detail=f"Path does not exist: {expanded_path}")
    if not os.path.isdir(expanded_path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {expanded_path}")
    return expanded_path


def _resolve_codebase_source(
    codebase_source: CodebaseSourceReq | None,
    fallback_path: str,
) -> ResolvedCodebase:
    if codebase_source is None:
        return ResolvedCodebase(path=fallback_path)

    source_type = (codebase_source.type or "").strip().lower()
    if source_type == "local":
        if not codebase_source.path:
            raise ValueError("Local codebase path is required.")
        resolved_path = os.path.abspath(os.path.expanduser(codebase_source.path))
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"Path does not exist: {resolved_path}")
        if not os.path.isdir(resolved_path):
            raise NotADirectoryError(f"Path is not a directory: {resolved_path}")
        return ResolvedCodebase(path=resolved_path)

    if source_type == "github":
        if not codebase_source.repo_url:
            raise ValueError("GitHub repo URL is required.")
        branch = (codebase_source.branch or "main").strip() or "main"
        try:
            clone_target, active_branch = _clone_or_update_github_repo(codebase_source.repo_url, branch)
        except FileNotFoundError as exc:
            print("[github-clone] failed: git executable was not found")
            raise RuntimeError("GitHub clone failed: git executable was not found.") from exc
        print(f"[github-clone] ready path={clone_target} active_branch={active_branch}")
        return ResolvedCodebase(path=clone_target)

    raise ValueError("Invalid codebase source type. Expected 'local' or 'github'.")


def _json_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def _build_source_key(codebase_source: CodebaseSourceReq | None, fallback_path: str) -> str:
    if codebase_source is None:
        return f"local:{os.path.abspath(os.path.expanduser(fallback_path))}"

    source_type = (codebase_source.type or "").strip().lower()
    if source_type == "github":
        branch = (codebase_source.branch or "main").strip() or "main"
        return f"github:{codebase_source.repo_url or ''}#{branch}"

    resolved_path = os.path.abspath(os.path.expanduser(codebase_source.path or fallback_path))
    return f"local:{resolved_path}"


def _common_root_name(paths: list[str]) -> str | None:
    first_parts = []
    for path in paths:
        normalized = path.replace("\\", "/").strip("/")
        if not normalized:
            continue
        first_parts.append(normalized.split("/", 1)[0])
    if not first_parts:
        return None
    candidate = first_parts[0]
    if all(part == candidate for part in first_parts):
        return candidate
    return None


@router.post("/codebase/upload")
async def upload_codebase(files: list[UploadFile] = File(...)):
    if not files:
        return _json_error(400, "No files were uploaded.")

    temp_dir = tempfile.mkdtemp(prefix="req-to-code-upload-")
    relative_paths: list[str] = []
    try:
        for upload in files:
            relative_path = (upload.filename or "").replace("\\", "/").lstrip("/")
            if not relative_path:
                continue

            destination = Path(temp_dir, relative_path).resolve()
            temp_root = Path(temp_dir).resolve()
            if temp_root not in destination.parents and destination != temp_root:
                raise ValueError(f"Invalid upload path: {relative_path}")

            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as target:
                shutil.copyfileobj(upload.file, target)
            relative_paths.append(relative_path)

        if not relative_paths:
            raise ValueError("Uploaded folder did not contain any usable files.")

        root_name = _common_root_name(relative_paths)
        resolved_path = str(Path(temp_dir, root_name).resolve()) if root_name else temp_dir
        return {
            "path": resolved_path,
            "label": root_name or os.path.basename(temp_dir),
            "file_count": len(relative_paths),
        }
    except ValueError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _json_error(400, str(exc))
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return _json_error(500, f"Codebase upload failed: {exc}")
    finally:
        for upload in files:
            await upload.close()


@router.post("/codebase/change")
def change_codebase(req: CodebaseChangeReq):
    current = read_runtime_state()
    previous_key = current.get("source_key")
    previous_path = current.get("codebase_path")
    next_key = req.source_key or ""

    if previous_key == next_key:
        sync_codebase_runtime_state(
            source_key=next_key,
            codebase_path=req.codebase_path or previous_path,
            source_meta={
                "source_type": req.source_type,
                "repo_url": req.repo_url,
                "branch": req.branch,
            },
        )
        return {
            "changed": False,
            "message": "Codebase unchanged.",
        }

    result = clear_codebase_dependent_state(previous_path)
    sync_codebase_runtime_state(
        source_key=next_key,
        codebase_path=req.codebase_path,
        source_meta={
            "source_type": req.source_type,
            "repo_url": req.repo_url,
            "branch": req.branch,
        },
    )
    return {
        "changed": True,
        "message": "Codebase changed. Cleared database records and generated artifacts.",
        "removed_paths": result.get("removed_paths", []),
    }


@router.post("/requirements/save")
def save_requirements(req: SaveRequirementsReq):
    try:
        result = save_requirements_snapshot(
            raw_text=req.raw_text,
            source_key=req.source_key,
            source_type=req.source_type,
            source_label=req.source_label,
            mode=req.mode,
        )
        return {
            "message": f"Saved {result['item_count']} requirement(s) to the database.",
            **result,
        }
    except ValueError as exc:
        return _json_error(400, str(exc))
    except Exception as exc:
        return _json_error(500, f"Failed to save requirements: {exc}")


@router.get("/requirements/load")
def load_requirements(source_key: str | None = Query(default=None)):
    try:
        snapshot = get_requirements_snapshot(source_key)
        if not snapshot:
            return {"found": False}
        return {
            "found": True,
            **snapshot,
        }
    except Exception as exc:
        return _json_error(500, f"Failed to load requirements: {exc}")

@router.post("/analyze-codebase")
def analyze(req: AnalyzeReq | None = None):
    req = req or AnalyzeReq()
    cleanup_path = None
    try:
        resolved = _resolve_codebase_source(req.codebase_source, req.path)
        cleanup_path = resolved.cleanup_path
        sync_codebase_runtime_state(
            source_key=_build_source_key(req.codebase_source, req.path),
            codebase_path=resolved.path,
            source_meta={
                "source_type": (req.codebase_source.type if req.codebase_source else "local"),
                "repo_url": (req.codebase_source.repo_url if req.codebase_source else None),
                "branch": (req.codebase_source.branch if req.codebase_source else None),
            },
        )
        return run_analysis(resolved.path)
    except FileNotFoundError as exc:
        return _json_error(400, str(exc))
    except NotADirectoryError as exc:
        return _json_error(400, str(exc))
    except ValueError as exc:
        return _json_error(400, str(exc))
    except RuntimeError as exc:
        return _json_error(500, str(exc))
    finally:
        if cleanup_path:
            shutil.rmtree(cleanup_path, ignore_errors=True)

@router.post("/run-pipeline")
def pipeline(req: PipelineReq | None = None):
    if req is None:
        sync_codebase_runtime_state(
            source_key=f"local:{os.path.abspath(os.path.expanduser(DEFAULT_CODEBASE_PATH))}",
            codebase_path=DEFAULT_CODEBASE_PATH,
            source_meta={"source_type": "local"},
        )
        return run_pipeline()
    cleanup_path = None
    try:
        resolved = _resolve_codebase_source(req.codebase_source, req.code_path)
        cleanup_path = resolved.cleanup_path
        sync_codebase_runtime_state(
            source_key=_build_source_key(req.codebase_source, req.code_path),
            codebase_path=resolved.path,
            source_meta={
                "source_type": (req.codebase_source.type if req.codebase_source else "local"),
                "repo_url": (req.codebase_source.repo_url if req.codebase_source else None),
                "branch": (req.codebase_source.branch if req.codebase_source else None),
            },
        )
        return run_pipeline(
            req_path=req.requirements_path,
            codebase_path=resolved.path,
            req_text=req.requirements_text,
        )
    except FileNotFoundError as exc:
        return _json_error(400, str(exc))
    except NotADirectoryError as exc:
        return _json_error(400, str(exc))
    except ValueError as exc:
        return _json_error(400, str(exc))
    except RuntimeError as exc:
        return _json_error(500, str(exc))
    finally:
        if cleanup_path:
            shutil.rmtree(cleanup_path, ignore_errors=True)

@router.get("/changes")
def list_changes():
    return get_changes()


@router.get("/filesystem/directories")
def list_directories(path: str | None = Query(default=None)):
    current_path = _normalize_directory_path(path)
    entries: list[dict[str, str]] = []
    try:
        for entry in os.scandir(current_path):
            if entry.is_dir():
                entries.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                    }
                )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied for directory: {current_path}",
        ) from exc

    entries.sort(key=lambda item: item["name"].lower())
    parent_path = os.path.dirname(current_path)
    return {
        "current_path": current_path,
        "parent_path": parent_path if parent_path and parent_path != current_path else None,
        "directories": entries,
    }

@router.post("/changes/{id}/accept")
def accept(id: int):
    success, msg = apply_diff(id)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
    return {"status": "accepted", "message": msg}

@router.post("/changes/{id}/reject")
def reject(id: int, req: RejectReq):
    update_status(id, "REJECTED", req.comment)
    return {"status": "rejected"}
