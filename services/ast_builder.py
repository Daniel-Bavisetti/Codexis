from __future__ import annotations

from services.file_summary_service import FileSummaryService
from services.knowledge_graph import KnowledgeGraphBuilder
from services.language_engine import LanguageEngine


def build_semantic_ast(analysis_output: dict | None = None, codebase: dict[str, str] | None = None) -> dict:
    if codebase is None:
        codebase = {}
        if analysis_output and isinstance(analysis_output, dict):
            codebase = analysis_output.get("codebase", {}) or {}

    language_engine = LanguageEngine()
    parsed_files = language_engine.parse_codebase(codebase)
    graph_builder = KnowledgeGraphBuilder(language_engine)
    graph = graph_builder.build_from_parsed(parsed_files)
    summary_service = FileSummaryService()
    file_summaries = summary_service.get_or_create_summaries(codebase, parsed_files)

    modules = []
    for parsed in parsed_files.values():
        module = parsed.to_module_dict()
        module["summary"] = file_summaries.get(parsed.path, "Summary not available.")
        modules.append(module)
    stats = {
        "files": len(parsed_files),
        "classes": sum(len(parsed.classes) for parsed in parsed_files.values()),
        "functions": sum(len(parsed.functions) for parsed in parsed_files.values()),
        "imports": sum(len(parsed.imports) for parsed in parsed_files.values()),
        "summaries_cached": sum(1 for path in parsed_files if file_summaries.get(path)),
    }

    return {
        "modules": modules,
        "graph": {
            "nodes": graph["nodes"],
            "edges": graph["edges"],
            "networkx": graph["networkx"],
        },
        "parsed_files": parsed_files,
        "file_summaries": file_summaries,
        "stats": stats,
    }
