"""
Gherkin Lexer for Karate feature files.

Uses State Machine pattern to categorize lines into Gherkin structures.
"""

import re
from enum import Enum, auto
from typing import List, Optional, Tuple, Iterator


class GherkinTokenType(Enum):
    FEATURE = auto()
    BACKGROUND = auto()
    SCENARIO = auto()
    SCENARIO_OUTLINE = auto()
    STEP = auto()
    EXAMPLES = auto()
    TAG = auto()
    TABLE_ROW = auto()
    EMPTY = auto()
    COMMENT = auto()
    UNKNOWN = auto()


class Token:
    def __init__(self, type: GherkinTokenType, text: str, line_number: int, keyword: Optional[str] = None):
        self.type = type
        self.text = text
        self.line_number = line_number
        self.keyword = keyword

    def __repr__(self):
        return f"Token({self.type.name}, line={self.line_number}, text='{self.text[:20]}...')"


class GherkinLexer:
    """Lexer that tokenizes Karate feature file lines."""

    def __init__(self):
        # Patterns
        self._patterns = {
            GherkinTokenType.FEATURE: re.compile(r"^\s*Feature\s*:?\s*(.*)$", re.IGNORECASE),
            GherkinTokenType.BACKGROUND: re.compile(r"^\s*Background\s*:?\s*$", re.IGNORECASE),
            GherkinTokenType.SCENARIO_OUTLINE: re.compile(r"^\s*Scenario Outline\s*:?\s*(.*)$", re.IGNORECASE),
            GherkinTokenType.SCENARIO: re.compile(r"^\s*Scenario\s*:?\s*(.*)$", re.IGNORECASE),
            GherkinTokenType.EXAMPLES: re.compile(r"^\s*Examples:\s*$", re.IGNORECASE),
            GherkinTokenType.STEP: re.compile(r"^\s*(Given|When|Then|And|But|\*)\s+(.+)$", re.IGNORECASE),
            GherkinTokenType.TAG: re.compile(r"^\s*@"),
            GherkinTokenType.TABLE_ROW: re.compile(r"^\s*\|.*\|\s*$"),
            GherkinTokenType.COMMENT: re.compile(r"^\s*#"),
            GherkinTokenType.EMPTY: re.compile(r"^\s*$"),
        }

    def tokenize(self, lines: List[str]) -> Iterator[Token]:
        """Convert lines into a sequence of tokens."""
        for i, line in enumerate(lines):
            line_num = i + 1
            yield self._tokenize_line(line, line_num)

    def _tokenize_line(self, line: str, line_num: int) -> Token:
        # Check patterns in order of specificity
        for token_type, pattern in self._patterns.items():
            match = pattern.match(line)
            if match:
                if token_type == GherkinTokenType.STEP:
                    return Token(token_type, match.group(2).strip(), line_num, match.group(1))
                elif token_type in [GherkinTokenType.FEATURE, GherkinTokenType.SCENARIO, GherkinTokenType.SCENARIO_OUTLINE]:
                    return Token(token_type, match.group(1).strip(), line_num)
                else:
                    return Token(token_type, line.strip(), line_num)
        
        return Token(GherkinTokenType.UNKNOWN, line.strip(), line_num)
