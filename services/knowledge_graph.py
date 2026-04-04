from __future__ import annotations

from dataclasses import asdict

from services.language_engine import LanguageEngine, ParsedEntity, ParsedFile


class KnowledgeGraphBuilder:
    def __init__(self, language_engine: LanguageEngine | None = None) -> None:
        self.language_engine = language_engine or LanguageEngine()

    def build(self, codebase: dict[str, str]) -> dict:
        parsed_files = self.language_engine.parse_codebase(codebase)
        return self.build_from_parsed(parsed_files)

    def build_from_parsed(self, parsed_files: dict[str, ParsedFile]) -> dict:
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        symbol_index: dict[str, list[str]] = {}

        for path, parsed in parsed_files.items():
            file_id = self._file_id(path)
            nodes[file_id] = {"id": file_id, "type": "file", "path": path, "language": parsed.language}

            for dependency in parsed.imports:
                dep_id = f"import:{dependency}"
                nodes.setdefault(dep_id, {"id": dep_id, "type": "import", "name": dependency})
                edges.append({"from": file_id, "to": dep_id, "type": "IMPORTS"})

            for variable in parsed.variables:
                var_id = f"var:{path}::{variable}"
                nodes.setdefault(var_id, {"id": var_id, "type": "variable", "name": variable, "path": path})
                edges.append({"from": file_id, "to": var_id, "type": "DEFINES"})

            for entity in [*parsed.classes, *parsed.functions]:
                nodes[entity.entity_id] = {
                    "id": entity.entity_id,
                    "type": entity.kind,
                    "name": entity.name,
                    "qualname": entity.qualname,
                    "path": path,
                    "line": entity.line,
                    "end_line": entity.end_line,
                }
                edges.append({"from": file_id, "to": entity.entity_id, "type": "DEFINES"})
                symbol_index.setdefault(entity.name, []).append(entity.entity_id)
                symbol_index.setdefault(entity.qualname, []).append(entity.entity_id)

                for variable in entity.variables:
                    var_id = f"var:{path}::{entity.qualname}::{variable}"
                    nodes.setdefault(var_id, {"id": var_id, "type": "variable", "name": variable, "path": path})
                    edges.append({"from": entity.entity_id, "to": var_id, "type": "DEFINES"})

                if entity.kind == "class":
                    for base in entity.bases:
                        base_id = self._resolve_symbol(base, symbol_index) or f"class_ref:{base}"
                        nodes.setdefault(base_id, {"id": base_id, "type": "class_ref", "name": base})
                        edges.append({"from": entity.entity_id, "to": base_id, "type": "INHERITS"})

        for parsed in parsed_files.values():
            for entity in [*parsed.classes, *parsed.functions]:
                for call in entity.calls:
                    callee_id = self._resolve_symbol(call.split(".")[-1], symbol_index) or f"func_ref:{call}"
                    nodes.setdefault(callee_id, {"id": callee_id, "type": "function_ref", "name": call})
                    edges.append({"from": entity.entity_id, "to": callee_id, "type": "CALLS"})

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "networkx": {
                "nodes": list(nodes.values()),
                "links": [{"source": edge["from"], "target": edge["to"], "type": edge["type"]} for edge in edges],
            },
            "parsed_files": {path: self._parsed_to_dict(parsed) for path, parsed in parsed_files.items()},
        }

    def _parsed_to_dict(self, parsed: ParsedFile) -> dict:
        return {
            "path": parsed.path,
            "language": parsed.language,
            "imports": parsed.imports,
            "variables": parsed.variables,
            "classes": [asdict(entity) for entity in parsed.classes],
            "functions": [asdict(entity) for entity in parsed.functions],
            "raw_calls": parsed.raw_calls,
            "errors": parsed.errors,
        }

    def _resolve_symbol(self, name: str, symbol_index: dict[str, list[str]]) -> str | None:
        matches = symbol_index.get(name) or []
        return matches[0] if matches else None

    def _file_id(self, path: str) -> str:
        return f"file:{path}"
