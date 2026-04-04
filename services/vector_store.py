from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from services.language_engine import LanguageEngine, ParsedFile


@dataclass
class VectorChunk:
    chunk_id: str
    path: str
    symbol: str
    kind: str
    language: str
    content: str
    embedding: list[float]


class SemanticVectorStore:
    def __init__(self, embedding_dim: int = 192) -> None:
        self.embedding_dim = embedding_dim
        self.language_engine = LanguageEngine()
        self.chunks: list[VectorChunk] = []

    def index_codebase(self, codebase: dict[str, str], parsed_files: dict[str, ParsedFile] | None = None) -> None:
        self.chunks = []
        parsed_files = parsed_files or self.language_engine.parse_codebase(codebase)
        for path, content in codebase.items():
            parsed = parsed_files[path]
            self._add_chunk(path, "__file__", "file", parsed.language, content)
            for entity in [*parsed.classes, *parsed.functions]:
                if entity.content.strip():
                    self._add_chunk(path, entity.qualname, entity.kind, parsed.language, entity.content)

    def retrieve(self, query: str, top_k: int = 3, file_hint: str | None = None) -> list[dict]:
        if not self.chunks:
            return []

        query_embedding = self._embed(query)
        scored: list[tuple[float, VectorChunk]] = []
        for chunk in self.chunks:
            score = self._cosine_similarity(query_embedding, chunk.embedding)
            if file_hint and file_hint in chunk.path:
                score += 0.18
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, chunk in scored[:top_k]:
            results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "path": chunk.path,
                    "symbol": chunk.symbol,
                    "kind": chunk.kind,
                    "language": chunk.language,
                    "score": round(score, 4),
                    "content": chunk.content,
                }
            )
        return results

    def _add_chunk(self, path: str, symbol: str, kind: str, language: str, content: str) -> None:
        self.chunks.append(
            VectorChunk(
                chunk_id=f"{path}::{symbol}",
                path=path,
                symbol=symbol,
                kind=kind,
                language=language,
                content=content,
                embedding=self._embed(f"{path}\n{symbol}\n{content}"),
            )
        )

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.embedding_dim
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]*", text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.embedding_dim
            sign = -1.0 if digest[2] % 2 else 1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))
