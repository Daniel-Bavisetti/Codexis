from __future__ import annotations

import difflib
import json
import os
import time
from pathlib import Path

from agents.generator_agent import GeneratorAgent
from agents.reviewer_agent import ReviewerAgent
from services.ast_builder import build_semantic_ast
from services.change_manager import (
    ensure_change,
    get_attempt_count,
    get_change_by_requirement,
    get_latest_feedback,
    log_event,
    record_attempt,
    record_impact_analysis,
    save_graph_snapshot,
)
from services.impact_analyzer import ImpactAnalyzer
from services.learning_engine import LearningEngine
from services.loader import load_codebase
from services.parser import parse_requirements
from services.validator import validate_code
from services.vector_store import SemanticVectorStore
from utils.llm import llm_status


MAX_ATTEMPTS = int(os.environ.get("MAX_PIPELINE_ATTEMPTS", "3"))
ANALYSIS_ARTIFACT_DIRNAME = ".req-to-code"


def _display_module_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/")
    if not normalized:
        return "Unknown module"

    if "data/codebase/" in normalized:
        return normalized.split("data/codebase/", 1)[1]

    parts = [part for part in normalized.split("/") if part]
    for index, part in enumerate(parts):
        if part.startswith("req-to-code-upload-") or part.startswith("req-to-code-"):
            if index + 1 < len(parts):
                return "/".join(parts[index + 1:])

    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return normalized


def _build_module_summaries(modules: list[dict]) -> list[dict]:
    summaries: list[dict] = []
    for module in sorted(modules, key=lambda item: item.get("path") or item.get("name") or ""):
        classes = module.get("classes") or []
        functions = module.get("functions") or []
        imports = module.get("imports") or []
        summary_text = (module.get("summary") or "Summary not available.").strip()
        display_path = _display_module_path(module.get("path") or module.get("name") or "Unknown module")
        summaries.append(
            {
                "path": display_path,
                "summary": summary_text,
                "class_count": len(classes),
                "function_count": len(functions),
                "import_count": len(imports),
                "summary_available": not summary_text.startswith("LLM summary unavailable"),
            }
        )
    return summaries


def _first_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""

    for marker in [". ", "! ", "? "]:
        if marker in cleaned:
            return cleaned.split(marker, 1)[0].strip() + marker.strip()
    return cleaned


def _friendly_project_name(codebase_path: str) -> str:
    raw_name = Path(codebase_path).name or "project"
    parts = [part for part in raw_name.split("__") if part]
    if len(parts) >= 2:
        return parts[1].replace("-", " ").replace("_", " ").strip() or "project"
    return raw_name.replace("-", " ").replace("_", " ").strip() or "project"


def _build_overview_summary(module_summaries: list[dict], stats: dict) -> str:
    summary_parts = []
    available = [item for item in module_summaries if item["summary_available"]]
    if available and len(available) == 1:
        summary_parts.append(_first_sentence(available[0]["summary"]))
    elif available:
        summary_sentences = []
        for item in available[:3]:
            sentence = _first_sentence(item["summary"])
            if sentence and sentence not in summary_sentences:
                summary_sentences.append(sentence)
        if summary_sentences:
            summary_parts.append(" ".join(summary_sentences))

    if not summary_parts:
        summary_parts.append(
            f"{_friendly_project_name(stats.get('codebase_path', 'project')).capitalize()} contains {stats['files']} module(s), {stats['classes']} class(es), and {stats['functions']} function(s)."
        )
    else:
        summary_parts.append(
            f"The codebase is organized into {stats['files']} module(s), {stats['classes']} class(es), and {stats['functions']} function(s)."
        )

    if stats["imports"]:
        summary_parts.append(f"It includes {stats['imports']} import relationship(s) across the analyzed modules.")

    unavailable_count = len([item for item in module_summaries if not item["summary_available"]])
    if unavailable_count:
        summary_parts.append(f"{unavailable_count} module summary or summaries fell back to basic analysis because the LLM did not return a usable summary.")

    return " ".join(summary_parts)


def _analysis_artifact_dir(codebase_path: str) -> Path:
    return Path(codebase_path) / ANALYSIS_ARTIFACT_DIRNAME


def _write_analysis_artifacts(
    codebase_path: str,
    semantic: dict,
    overall_summary: str,
    module_summaries: list[dict],
) -> str:
    artifact_dir = _analysis_artifact_dir(codebase_path)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    knowledge_graph_payload = {
        "nodes": semantic["graph"].get("nodes", []),
        "edges": semantic["graph"].get("edges", []),
        "networkx": semantic["graph"].get("networkx", {}),
    }
    semantic_ast_payload = semantic.get("modules", [])
    summary_payload = {
        "overall_summary": overall_summary,
        "module_summaries": module_summaries,
        "graph_stats": semantic.get("stats", {}),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    (artifact_dir / "knowledge_graph.json").write_text(json.dumps(knowledge_graph_payload, indent=2), encoding="utf-8")
    (artifact_dir / "semantic_ast.json").write_text(json.dumps(semantic_ast_payload, indent=2), encoding="utf-8")
    (artifact_dir / "analysis_summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    return str(artifact_dir)


def run_analysis(codebase_path: str = "data/codebase"):
    codebase = load_codebase(codebase_path)
    if not codebase:
        return {"error": "No files found", "files": [], "knowledge_graph": {"nodes": [], "edges": []}}

    semantic = build_semantic_ast(codebase=codebase)
    stats = semantic["stats"]
    stats["codebase_path"] = codebase_path
    module_summaries = _build_module_summaries(semantic["modules"])
    overall_summary = _build_overview_summary(module_summaries, stats)
    artifact_dir = _write_analysis_artifacts(codebase_path, semantic, overall_summary, module_summaries)
    return {
        "overall_summary": overall_summary,
        "module_summaries": module_summaries,
        "files": list(codebase.keys()),
        "semantic_ast": semantic["modules"],
        "knowledge_graph": semantic["graph"],
        "graph_stats": stats,
        "codebase_path": codebase_path,
        "analysis_artifact_dir": artifact_dir,
    }


def _compute_diff(orig: str, new: str, file_path: str) -> str:
    orig_lines = orig.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(orig_lines, new_lines, fromfile=file_path, tofile=file_path)
    return "".join(list(diff))


def _flatten_requirements(reqs: dict) -> list[tuple[str, dict]]:
    items: list[tuple[str, dict]] = []
    for mode in ["FIT", "PARTIAL", "GAP"]:
        for req in reqs.get(mode, []):
            items.append((mode, req))
    return items


def _resolve_file_path(file_hint: str, codebase: dict[str, str], code_path: str) -> tuple[str, str]:
    if file_hint in codebase:
        return file_hint, codebase[file_hint]
    candidate = os.path.join(code_path, file_hint)
    if candidate in codebase:
        return candidate, codebase[candidate]
    for path, content in codebase.items():
        if path.endswith(file_hint):
            return path, content
    return candidate, ""


def _build_confidence(review: dict, validation_ok: bool, impact_score: float, feedback_used: str | None) -> tuple[float, str]:
    confidence = float(review.get("confidence", 0.65))
    confidence -= min(len(review.get("issues", [])) * 0.08, 0.4)
    confidence -= min(len(review.get("dependency_violations", [])) * 0.07, 0.21)
    confidence -= min(len(review.get("security_findings", [])) * 0.1, 0.3)
    if not validation_ok:
        confidence -= 0.25
    confidence -= impact_score * 0.2
    if feedback_used:
        confidence += 0.05
    confidence = max(0.0, min(confidence, 1.0))

    reasons = []
    if review.get("issues"):
        reasons.append(f"{len(review['issues'])} review issue(s)")
    if review.get("dependency_violations"):
        reasons.append(f"{len(review['dependency_violations'])} dependency concern(s)")
    if review.get("security_findings"):
        reasons.append(f"{len(review['security_findings'])} security concern(s)")
    reasons.append("syntax valid" if validation_ok else "syntax invalid")
    reasons.append(f"impact risk {round(impact_score, 2)}")
    if feedback_used:
        reasons.append("feedback-aware retry")
    return confidence, ", ".join(reasons)


def run_pipeline(
    req_path: str = "data/reqs.json",
    codebase_path: str = "data/codebase",
    req_text: str | None = None,
):
    start_time = time.time()
    logs: list[str] = []

    def log(message: str) -> None:
        print(message)
        logs.append(message)

    log("[10%] Loading multi-language codebase...")
    codebase = load_codebase(codebase_path)
    if not codebase:
        return {"status": "error", "logs": ["No files found in target codebase."], "time_seconds": 0}

    log("[20%] Building semantic AST + knowledge graph...")
    semantic = build_semantic_ast(codebase=codebase)
    graph = semantic["graph"]
    parsed_files = semantic["parsed_files"]
    semantic["stats"]["codebase_path"] = codebase_path
    module_summaries = _build_module_summaries(semantic["modules"])
    overall_summary = _build_overview_summary(module_summaries, semantic["stats"])
    artifact_dir = _write_analysis_artifacts(codebase_path, semantic, overall_summary, module_summaries)
    snapshot_id = save_graph_snapshot(codebase_path, graph)
    log(f"   Graph snapshot saved: {snapshot_id}")
    log(f"   Analysis artifacts written to: {artifact_dir}")

    log("[30%] Indexing semantic vectors...")
    vector_store = SemanticVectorStore()
    vector_store.index_codebase(codebase, parsed_files=parsed_files)

    log("[40%] Parsing requirements...")
    requirements = _flatten_requirements(parse_requirements(filepath=req_path, raw_text=req_text))
    if not requirements:
        return {
            "status": "error",
            "logs": ["No requirements found."],
            "time_seconds": 0,
            "codebase_path": codebase_path,
            "analysis_artifact_dir": artifact_dir,
        }

    llm_runtime = llm_status()
    if not llm_runtime["ready"] and not llm_runtime["mock_enabled"]:
        reason_parts = []
        if not llm_runtime["api_key_present"]:
            reason_parts.append("GEMINI_API_KEY is not set")
        reason = "; ".join(reason_parts) or "LLM runtime is not ready"
        log(f"[45%] Pipeline halted: {reason}.")
        return {
            "status": "error",
            "logs": logs,
            "time_seconds": round(time.time() - start_time, 2),
            "codebase_path": codebase_path,
            "analysis_artifact_dir": artifact_dir,
        }

    generator = GeneratorAgent()
    reviewer = ReviewerAgent()
    impact_analyzer = ImpactAnalyzer()
    learning_engine = LearningEngine()

    log("[50%] Processing requirements...")

    for mode, req in requirements:
        requirement_id = req["id"]
        existing = get_change_by_requirement(requirement_id)
        if existing and existing["status"] == "ACCEPTED":
            log(f"-> Skipping {requirement_id}: already accepted.")
            continue
        if existing and existing["status"] == "PENDING" and existing.get("latest_attempt"):
            log(f"-> Waiting on HITL for {requirement_id}: latest attempt is still pending.")
            continue

        feedback_used = get_latest_feedback(existing["id"]) if existing else None
        file_hint = req.get("file_hint", "new_module.py")
        target_file_path, original_code = _resolve_file_path(file_hint, codebase, codebase_path)
        change_id = ensure_change(requirement_id, target_file_path, original_code)
        attempt_number = get_attempt_count(change_id) + 1

        if attempt_number > MAX_ATTEMPTS:
            log(f"-> Max attempts reached for {requirement_id}.")
            log_event("MAX_ATTEMPTS_REACHED", {"requirement_id": requirement_id}, change_id=change_id)
            continue

        log(f"-> Processing {mode}: {requirement_id} (attempt {attempt_number}/{MAX_ATTEMPTS})")
        retrieved_context = vector_store.retrieve(req.get("description", ""), top_k=4, file_hint=target_file_path)
        learning_context = learning_engine.get_context(requirement_id)

        try:
            gen_result = generator.generate(
                requirement=req,
                context=retrieved_context,
                ast={"modules": semantic["modules"], "stats": semantic["stats"]},
                mode=mode,
                feedback=feedback_used,
                past_rejections=existing["rejection_history"] if existing else None,
                knowledge_graph=graph,
                learning_context=learning_context,
            )
            generated_code = gen_result["output"]
            if generated_code.startswith("Error:"):
                raise RuntimeError(generated_code)
            if mode == "FIT":
                log(f"   {requirement_id} is analysis-only; storing as accepted insight.")
                record_attempt(
                    change_id=change_id,
                    attempt_number=attempt_number,
                    generated_code=generated_code,
                    diff_text=generated_code,
                    review={"issues": [], "suggestions": [], "confidence": 1.0, "verdict": "PASS"},
                    validation_message="FIT analysis does not require syntax validation.",
                    confidence=1.0,
                    confidence_explanation="analysis-only fit requirement",
                    context=retrieved_context,
                    feedback_used=feedback_used or "",
                    impact_analysis={"impacted_files": [], "impacted_functions": [], "dependency_chain": [], "risk_score": 0.0, "summary": "No code impact."},
                    status="ACCEPTED",
                )
                learning_engine.record_success(requirement_id, target_file_path, {"verdict": "PASS", "confidence": 1.0})
                continue

            validation_ok, validation_message = validate_code(target_file_path, generated_code)
            review = reviewer.run(
                generated_code,
                requirement=req,
                context=retrieved_context,
                knowledge_graph=graph,
                file_path=target_file_path,
            )
            if not validation_ok:
                review.setdefault("issues", []).append(validation_message)
                review["verdict"] = "FAIL"

            diff_text = _compute_diff(original_code, generated_code, target_file_path)
            if not diff_text.strip():
                diff_text = "\n".join([f"+{line}" for line in generated_code.splitlines()]) or "+# no-op"

            impact = impact_analyzer.analyze(target_file_path, diff_text, graph)
            confidence, confidence_explanation = _build_confidence(review, validation_ok, impact["risk_score"], feedback_used)
            status = "PENDING"
            attempt_id = record_attempt(
                change_id=change_id,
                attempt_number=attempt_number,
                generated_code=generated_code,
                diff_text=diff_text,
                review=review,
                validation_message=validation_message,
                confidence=confidence,
                confidence_explanation=confidence_explanation,
                context=retrieved_context,
                feedback_used=feedback_used or "",
                impact_analysis=impact,
                status=status,
            )
            record_impact_analysis(change_id, attempt_id, impact)
            learning_engine.record_attempt(requirement_id, target_file_path, attempt_number, confidence, status)
            log(f"   Saved attempt {attempt_number}; awaiting HITL review.")

        except Exception as exc:
            log(f"Error processing {requirement_id}: {exc}")
            log_event("PIPELINE_ERROR", {"requirement_id": requirement_id, "error": str(exc)}, change_id=change_id)

    duration = round(time.time() - start_time, 2)
    log(f"[100%] Pipeline completed in {duration}s.")
    return {
        "status": "success",
        "logs": logs,
        "time_seconds": duration,
        "codebase_path": codebase_path,
        "analysis_artifact_dir": artifact_dir,
    }
