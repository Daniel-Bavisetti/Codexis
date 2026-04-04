from __future__ import annotations

import json
import re
from collections import defaultdict, deque


class ImpactAnalyzer:
    def analyze(self, file_path: str, diff_text: str, graph: dict, protected_files: list[str] | None = None) -> dict:
        protected_files = protected_files or []
        changed_symbols = self._extract_changed_symbols(diff_text)
        node_ids = self._seed_nodes(file_path, changed_symbols, graph)
        adjacency = self._build_adjacency(graph.get("edges", []))
        visited: set[str] = set()
        dependency_chain: list[dict] = []
        impacted_files: set[str] = set()
        impacted_functions: set[str] = set()

        queue = deque((node_id, 0) for node_id in node_ids)
        while queue:
            current, depth = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            node = self._node_lookup(graph).get(current, {})
            node_path = node.get("path")
            if node_path:
                impacted_files.add(node_path)
            if node.get("type") == "function":
                impacted_functions.add(node.get("qualname", node.get("name", current)))

            for edge in adjacency.get(current, []):
                dependency_chain.append({"from": current, "to": edge["to"], "type": edge["type"], "depth": depth + 1})
                queue.append((edge["to"], depth + 1))

        risk_score = min(
            1.0,
            0.2
            + (0.1 * len(impacted_files))
            + (0.07 * len(impacted_functions))
            + (0.12 if any(item in file_path for item in protected_files) else 0.0),
        )

        return {
            "impacted_files": sorted(impacted_files),
            "impacted_functions": sorted(impacted_functions),
            "dependency_chain": dependency_chain[:20],
            "risk_score": round(risk_score, 2),
            "summary": self._summary(impacted_files, impacted_functions, risk_score),
            "changed_symbols": changed_symbols,
            "raw": json.dumps(
                {
                    "impacted_files": sorted(impacted_files),
                    "impacted_functions": sorted(impacted_functions),
                    "dependency_chain": dependency_chain[:20],
                    "risk_score": round(risk_score, 2),
                }
            ),
        }

    def _node_lookup(self, graph: dict) -> dict[str, dict]:
        return {node["id"]: node for node in graph.get("nodes", [])}

    def _build_adjacency(self, edges: list[dict]) -> dict[str, list[dict]]:
        adjacency: dict[str, list[dict]] = defaultdict(list)
        for edge in edges:
            adjacency[edge["from"]].append(edge)
        return adjacency

    def _extract_changed_symbols(self, diff_text: str) -> list[str]:
        added_lines = [line[1:].strip() for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]
        symbols: list[str] = []
        patterns = [
            re.compile(r"(?:def|class|func|function)\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ]
        for line in added_lines:
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    symbols.append(match.group(1))
        return symbols

    def _seed_nodes(self, file_path: str, symbols: list[str], graph: dict) -> list[str]:
        node_lookup = self._node_lookup(graph)
        seeded = [node_id for node_id, node in node_lookup.items() if node.get("path") == file_path and node.get("type") == "file"]
        for symbol in symbols:
            for node_id, node in node_lookup.items():
                if node.get("path") == file_path and node.get("name") == symbol:
                    seeded.append(node_id)
        return seeded or [f"file:{file_path}"]

    def _summary(self, impacted_files: set[str], impacted_functions: set[str], risk_score: float) -> str:
        return (
            f"Risk {round(risk_score, 2)} across {len(impacted_files)} file(s) "
            f"and {len(impacted_functions)} function(s)."
        )
