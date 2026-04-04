from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Any


SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".go": "go",
    ".java": "java",
}


@dataclass
class ParsedEntity:
    name: str
    qualname: str
    entity_id: str
    kind: str
    line: int | None = None
    end_line: int | None = None
    bases: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    content: str = ""


@dataclass
class ParsedFile:
    path: str
    language: str
    imports: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    classes: list[ParsedEntity] = field(default_factory=list)
    functions: list[ParsedEntity] = field(default_factory=list)
    raw_calls: list[str] = field(default_factory=list)
    content: str = ""
    errors: list[str] = field(default_factory=list)

    def to_module_dict(self) -> dict[str, Any]:
        return {
            "name": os.path.basename(self.path),
            "path": self.path,
            "language": self.language,
            "classes": [cls.name for cls in self.classes],
            "functions": [fn.name for fn in self.functions],
            "dependencies": self.imports,
            "variables": self.variables,
            "db_api_interactions": [],
        }


class _PythonAnalyzer(ast.NodeVisitor):
    def __init__(self, path: str, source_lines: list[str]):
        self.path = path
        self.source_lines = source_lines
        self.imports: list[str] = []
        self.variables: set[str] = set()
        self.classes: list[ParsedEntity] = []
        self.functions: list[ParsedEntity] = []
        self.raw_calls: list[str] = []
        self._class_stack: list[ParsedEntity] = []
        self._function_stack: list[ParsedEntity] = []

    def visit_Import(self, node: ast.Import) -> Any:
        self.imports.extend(alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}" if module else alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        for target in node.targets:
            self._capture_assignment_target(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        self._capture_assignment_target(node.target)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        qualname = ".".join([*(c.name for c in self._class_stack), node.name])
        entity = ParsedEntity(
            name=node.name,
            qualname=qualname,
            entity_id=f"class:{self.path}::{qualname}",
            kind="class",
            line=getattr(node, "lineno", None),
            end_line=getattr(node, "end_lineno", None),
            bases=[self._expr_name(base) for base in node.bases],
            content=self._slice_source(node),
        )
        self.classes.append(entity)
        self._class_stack.append(entity)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> Any:
        callee = self._expr_name(node.func)
        if callee:
            self.raw_calls.append(callee)
            if self._function_stack:
                self._function_stack[-1].calls.append(callee)
            elif self._class_stack:
                self._class_stack[-1].calls.append(callee)
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        owner = [c.name for c in self._class_stack]
        qualname = ".".join([*owner, node.name])
        entity = ParsedEntity(
            name=node.name,
            qualname=qualname,
            entity_id=f"func:{self.path}::{qualname}",
            kind="function",
            line=getattr(node, "lineno", None),
            end_line=getattr(node, "end_lineno", None),
            variables=[arg.arg for arg in node.args.args],
            content=self._slice_source(node),
        )
        self.functions.append(entity)
        self._function_stack.append(entity)
        self.generic_visit(node)
        self._function_stack.pop()

    def _capture_assignment_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.variables.add(target.id)
            if self._function_stack:
                self._function_stack[-1].variables.append(target.id)
            elif self._class_stack:
                self._class_stack[-1].variables.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._capture_assignment_target(elt)

    def _expr_name(self, expr: ast.AST | None) -> str:
        if expr is None:
            return ""
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            base = self._expr_name(expr.value)
            return f"{base}.{expr.attr}" if base else expr.attr
        if isinstance(expr, ast.Call):
            return self._expr_name(expr.func)
        if isinstance(expr, ast.Subscript):
            return self._expr_name(expr.value)
        return ""

    def _slice_source(self, node: ast.AST) -> str:
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if not start or not end:
            return ""
        return "\n".join(self.source_lines[start - 1 : end])


class LanguageEngine:
    def __init__(self) -> None:
        self._function_patterns = {
            "javascript": [
                re.compile(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
                re.compile(r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
            ],
            "go": [re.compile(r"func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")],
            "java": [re.compile(r"(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")],
        }

    def detect_language(self, path: str, content: str = "") -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in SUPPORTED_EXTENSIONS:
            return SUPPORTED_EXTENSIONS[ext]
        stripped = content.lstrip()
        if stripped.startswith("package ") and "func " in content:
            return "go"
        if "class " in content and "public static void main" in content:
            return "java"
        return "text"

    def parse(self, path: str, content: str) -> ParsedFile:
        language = self.detect_language(path, content)
        parser = getattr(self, f"_parse_{language}", self._parse_generic)
        return parser(path, content)

    def parse_codebase(self, codebase: dict[str, str]) -> dict[str, ParsedFile]:
        return {path: self.parse(path, content) for path, content in codebase.items()}

    def extract_functions(self, parsed: ParsedFile) -> list[ParsedEntity]:
        return parsed.functions

    def extract_dependencies(self, parsed: ParsedFile) -> list[str]:
        return parsed.imports

    def _parse_python(self, path: str, content: str) -> ParsedFile:
        parsed = ParsedFile(path=path, language="python", content=content)
        try:
            tree = ast.parse(content)
            analyzer = _PythonAnalyzer(path, content.splitlines())
            analyzer.visit(tree)
            parsed.imports = analyzer.imports
            parsed.variables = sorted(analyzer.variables)
            parsed.classes = analyzer.classes
            parsed.functions = analyzer.functions
            parsed.raw_calls = analyzer.raw_calls
        except SyntaxError as exc:
            parsed.errors.append(f"Syntax error: {exc}")
        return parsed

    def _parse_javascript(self, path: str, content: str) -> ParsedFile:
        parsed = ParsedFile(path=path, language="javascript", content=content)
        parsed.imports = re.findall(r"(?:import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\))", content)
        parsed.imports = [match[0] or match[1] for match in parsed.imports]
        parsed.variables = re.findall(r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)", content)
        parsed.classes = self._extract_class_entities(path, content, "javascript", re.compile(r"class\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+([A-Za-z_][A-Za-z0-9_]*))?"))
        parsed.functions = self._extract_function_entities(path, content, "javascript")
        parsed.raw_calls = re.findall(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", content)
        return parsed

    def _parse_go(self, path: str, content: str) -> ParsedFile:
        parsed = ParsedFile(path=path, language="go", content=content)
        parsed.imports = re.findall(r'"([^"]+)"', self._extract_block(content, "import"))
        parsed.variables = re.findall(r"(?:var|const)\s+([A-Za-z_][A-Za-z0-9_]*)", content)
        parsed.functions = self._extract_function_entities(path, content, "go")
        parsed.raw_calls = re.findall(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", content)
        return parsed

    def _parse_java(self, path: str, content: str) -> ParsedFile:
        parsed = ParsedFile(path=path, language="java", content=content)
        parsed.imports = re.findall(r"import\s+([A-Za-z0-9_\.]+);", content)
        parsed.variables = re.findall(r"(?:private|protected|public)?\s+[A-Za-z0-9_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|;)", content)
        parsed.classes = self._extract_class_entities(path, content, "java", re.compile(r"class\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+([A-Za-z_][A-Za-z0-9_]*))?"))
        parsed.functions = self._extract_function_entities(path, content, "java")
        parsed.raw_calls = re.findall(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", content)
        return parsed

    def _parse_generic(self, path: str, content: str) -> ParsedFile:
        return ParsedFile(path=path, language=self.detect_language(path, content), content=content)

    def _extract_function_entities(self, path: str, content: str, language: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        patterns = self._function_patterns.get(language, [])
        seen: set[str] = set()
        lines = content.splitlines()
        for pattern in patterns:
            for match in pattern.finditer(content):
                name = match.group(1)
                if name in seen:
                    continue
                seen.add(name)
                line = content[: match.start()].count("\n") + 1
                entities.append(
                    ParsedEntity(
                        name=name,
                        qualname=name,
                        entity_id=f"func:{path}::{name}",
                        kind="function",
                        line=line,
                        end_line=min(len(lines), line + 20),
                        content=self._slice_lines(lines, line, min(len(lines), line + 20)),
                        calls=self._extract_calls_near_line(lines, line),
                    )
                )
        return entities

    def _extract_class_entities(self, path: str, content: str, language: str, pattern: re.Pattern[str]) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        lines = content.splitlines()
        for match in pattern.finditer(content):
            name = match.group(1)
            base = match.group(2) if len(match.groups()) > 1 else None
            line = content[: match.start()].count("\n") + 1
            entities.append(
                ParsedEntity(
                    name=name,
                    qualname=name,
                    entity_id=f"class:{path}::{name}",
                    kind="class",
                    line=line,
                    end_line=min(len(lines), line + 40),
                    bases=[base] if base else [],
                    content=self._slice_lines(lines, line, min(len(lines), line + 40)),
                )
            )
        return entities

    def _extract_block(self, content: str, keyword: str) -> str:
        match = re.search(rf"{keyword}\s*\((.*?)\)", content, re.DOTALL)
        return match.group(1) if match else content

    def _extract_calls_near_line(self, lines: list[str], line: int, window: int = 20) -> list[str]:
        snippet = "\n".join(lines[line - 1 : min(len(lines), line - 1 + window)])
        return re.findall(r"([A-Za-z_][A-Za-z0-9_\.]*)\s*\(", snippet)

    def _slice_lines(self, lines: list[str], start: int, end: int) -> str:
        return "\n".join(lines[max(0, start - 1) : max(0, end)])
