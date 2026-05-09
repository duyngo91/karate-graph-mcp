"""
Lightweight JavaScript structure extractor for Karate helper files.

This is intentionally regex-based: Karate projects commonly use small JS helper
files, config files, and exported functions where a full JavaScript AST would be
heavier than the analyzer needs.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class JavaScriptFunction:
    name: str
    line_number: int
    kind: str


@dataclass(frozen=True)
class JavaScriptStructure:
    file_path: str
    functions: List[JavaScriptFunction]


class JavaScriptStructureExtractor:
    """Extract function/export symbols from a JavaScript file."""

    _FUNCTION_PATTERNS = [
        (re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\("), "function"),
        (re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*function\b"), "function_expression"),
        (re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"), "arrow_function"),
        (re.compile(r"\bexports\.([A-Za-z_$][\w$]*)\s*="), "exports"),
        (re.compile(r"\bmodule\.exports\.([A-Za-z_$][\w$]*)\s*="), "module_exports"),
    ]

    _MODULE_EXPORT_FUNCTION = re.compile(
        r"\bmodule\.exports\s*=\s*(?:async\s*)?function(?:\s+([A-Za-z_$][\w$]*))?\s*\("
    )
    _MODULE_EXPORT_OBJECT = re.compile(r"\bmodule\.exports\s*=\s*\{(?P<body>.*?)\}\s*;?", re.DOTALL)
    _OBJECT_EXPORT_ENTRY = re.compile(
        r"(?:^|,)\s*([A-Za-z_$][\w$]*)\s*(?::\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>|[A-Za-z_$][\w$]*))?"
    )

    def parse_file(self, file_path: str) -> JavaScriptStructure:
        path = Path(file_path)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")

        functions: List[JavaScriptFunction] = []
        seen = set()
        for line_number, line in enumerate(content.splitlines(), start=1):
            stripped = self._strip_line_comment(line)
            for pattern, kind in self._FUNCTION_PATTERNS:
                for match in pattern.finditer(stripped):
                    self._append_function(functions, seen, match.group(1), line_number, kind)

            export_match = self._MODULE_EXPORT_FUNCTION.search(stripped)
            if export_match:
                name = export_match.group(1) or self._default_export_name(path)
                self._append_function(functions, seen, name, line_number, "module_exports_function")

        for object_match in self._MODULE_EXPORT_OBJECT.finditer(content):
            base_line = content[: object_match.start("body")].count("\n") + 1
            body = object_match.group("body")
            for entry_match in self._OBJECT_EXPORT_ENTRY.finditer(body):
                name = entry_match.group(1)
                if any(function.name == name for function in functions):
                    continue
                line_number = base_line + body[: entry_match.start(1)].count("\n")
                self._append_function(functions, seen, name, line_number, "module_exports_object")

        return JavaScriptStructure(str(path), functions)

    def _append_function(
        self,
        functions: List[JavaScriptFunction],
        seen: set,
        name: str,
        line_number: int,
        kind: str,
    ) -> None:
        key = (name, line_number, kind)
        if name and key not in seen:
            seen.add(key)
            functions.append(JavaScriptFunction(name=name, line_number=line_number, kind=kind))

    def _strip_line_comment(self, line: str) -> str:
        return re.sub(r"//.*$", "", line)

    def _default_export_name(self, path: Path) -> str:
        return "default" if path.stem == "index" else path.stem
