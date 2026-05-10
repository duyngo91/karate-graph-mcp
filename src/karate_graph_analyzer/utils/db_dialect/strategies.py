"""Strategies for database dialect detection."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

from karate_graph_analyzer.utils.db_dialect.context import (
    UNKNOWN,
    DbDialectContext,
    normalize_optional,
    normalize_token,
    unique_tuple,
)


class DbDialectStrategy(Protocol):
    """Strategy contract for detecting one DB family or fallback."""

    def detect(self, text: str, details: Dict[str, Any]) -> Optional[DbDialectContext]:
        ...


OPERATION_RULES: List[Tuple[str, str]] = [
    (r"\bSELECT\b", "SELECT"),
    (r"\bINSERT\s+INTO\b", "INSERT"),
    (r"\bUPDATE\b", "UPDATE"),
    (r"\bDELETE\s+FROM\b", "DELETE"),
    (r"\bMERGE\b", "MERGE"),
    (r"\bUPSERT\b", "UPSERT"),
    (r"\bCREATE\b", "CREATE"),
    (r"\bDROP\b", "DROP"),
    (r"\bALTER\b", "ALTER"),
    (r"\bTRUNCATE\b", "TRUNCATE"),
    (r"\bUSE\b", "USE"),
    (r"\bfindOne\b", "FINDONE"),
    (r"\bfind\b", "FIND"),
    (r"\binsertOne\b", "INSERTONE"),
    (r"\bupdateOne\b", "UPDATEONE"),
    (r"\bdeleteOne\b", "DELETEONE"),
    (r"\baggregate\b", "AGGREGATE"),
    (r"\bHGET\b", "HGET"),
    (r"\bHSET\b", "HSET"),
    (r"\bGET\b", "GET"),
    (r"\bSET\b", "SET"),
    (r"\bDEL\b", "DEL"),
    (r"\bGetItem\b", "GETITEM"),
    (r"\bPutItem\b", "PUTITEM"),
    (r"\bUpdateItem\b", "UPDATEITEM"),
    (r"\bDeleteItem\b", "DELETEITEM"),
    (r"\bquery\s*\(", "QUERY"),
    (r"\bscan\s*\(", "SCAN"),
    (r"/_search\b|\b_search\b", "SEARCH"),
    (r"\bMATCH\s*\([^)]*\)\s*RETURN\b", "MATCH"),
]

SQL_OPERATION_PATTERN = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|UPSERT|USE)\b",
    re.IGNORECASE,
)
SQL_TABLE_PATTERN = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_.]*)[`\"\]]?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RegexDialectStrategy:
    """Detect a DB family by one or more regex patterns."""

    dialect: str
    db_type: str
    provider: str
    patterns: Tuple[str, ...]
    confidence: str

    def detect(self, text: str, details: Dict[str, Any]) -> Optional[DbDialectContext]:
        corpus = build_corpus(text, details)
        for pattern in self.patterns:
            if re.search(pattern, corpus, re.IGNORECASE):
                return build_context(
                    text=text,
                    details=details,
                    db_type=self.db_type,
                    dialect=self.dialect,
                    provider=self.provider,
                    confidence=self.confidence,
                    signals=[f"pattern:{self.dialect}"],
                )
        return None


class MetadataDialectStrategy:
    """Trust explicit dialect metadata collected upstream."""

    def detect(self, text: str, details: Dict[str, Any]) -> Optional[DbDialectContext]:
        dialect = normalize_token(details.get("dialect") or details.get("db_dialect"), "")
        if not dialect:
            return None
        db_type = normalize_token(details.get("db_type") or details.get("store_type"))
        provider = normalize_token(details.get("provider"), dialect)
        confidence = normalize_token(details.get("dialect_confidence"), "high")
        return build_context(
            text=text,
            details=details,
            db_type=db_type,
            dialect=dialect,
            provider=provider,
            confidence=confidence,
            signals=[f"metadata:{dialect}"],
        )


class GenericSqlStrategy:
    """Fallback strategy for SQL that has no vendor-specific signal."""

    def detect(self, text: str, details: Dict[str, Any]) -> Optional[DbDialectContext]:
        if not looks_like_sql(text, details):
            return None
        return build_context(
            text=text,
            details=details,
            db_type="relational",
            dialect="generic_sql",
            provider=UNKNOWN,
            confidence="low",
            signals=["sql_operation"],
        )


def build_context(
    text: str,
    details: Dict[str, Any],
    db_type: str,
    dialect: str,
    provider: str,
    confidence: str,
    signals: List[str],
) -> DbDialectContext:
    operation = str(details.get("operation") or "").upper() or detect_operation(text)
    entity_type, entity_name, entity_signals = detect_entity(text, details, db_type, dialect)
    return DbDialectContext(
        db_type=db_type or UNKNOWN,
        dialect=dialect or UNKNOWN,
        provider=provider or (dialect if dialect else UNKNOWN),
        dialect_confidence=confidence or "low",
        dialect_signals=unique_tuple(signals + entity_signals),
        operation=operation or details.get("operation"),
        entity_type=entity_type,
        entity_name=entity_name,
    )


def detect_operation(text: str) -> Optional[str]:
    for pattern, operation in OPERATION_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return operation
    return None


def detect_entity(
    text: str,
    details: Dict[str, Any],
    db_type: str,
    dialect: str,
) -> Tuple[Optional[str], Optional[str], List[str]]:
    for key, entity_type in [
        ("table", "table"),
        ("collection", "collection"),
        ("key", "key"),
        ("index", "index"),
        ("keyspace", "keyspace"),
    ]:
        value = normalize_optional(details.get(key))
        if value:
            return entity_type, value, [f"metadata:{entity_type}"]

    if db_type == "document" or dialect == "mongodb":
        return first_entity_match(
            text,
            [
                (r"\bdb\.([A-Za-z_][\w]*)\.(?:find|findOne|insertOne|updateOne|deleteOne|aggregate)\b", "collection"),
                (r"\bcollection\s*[:=]\s*['\"]([^'\"]+)['\"]", "collection"),
            ],
        )
    if dialect == "redis":
        return first_entity_match(
            text,
            [
                (r"\b(?:HGET|HSET|HDEL|GET|SET|DEL|EXPIRE|LPUSH|RPUSH|ZADD)\s*\(\s*['\"]([^'\"]+)['\"]", "key"),
                (r"\bkey\s*[:=]\s*['\"]([^'\"]+)['\"]", "key"),
            ],
        )
    if dialect == "dynamodb":
        return first_entity_match(
            text,
            [
                (r"\bTableName\s*[:=]\s*['\"]([^'\"]+)['\"]", "table"),
                (r"\btable\s*[:=]\s*['\"]([^'\"]+)['\"]", "table"),
            ],
        )
    if dialect in {"elasticsearch", "opensearch"}:
        return first_entity_match(
            text,
            [
                (r"/([A-Za-z0-9_.-]+)/_search\b", "index"),
                (r"\b(?:index|_index)\s*[:=]\s*['\"]([^'\"]+)['\"]", "index"),
            ],
        )
    if dialect == "cassandra":
        table = SQL_TABLE_PATTERN.search(text)
        if table:
            return "table", table.group(1), ["pattern:table"]
        return first_entity_match(text, [(r"\bKEYSPACE\s+([A-Za-z_][\w]*)", "keyspace")])

    table = SQL_TABLE_PATTERN.search(text)
    if table:
        return "table", table.group(1), ["pattern:table"]
    return None, None, []


def first_entity_match(
    text: str,
    patterns: List[Tuple[str, str]],
) -> Tuple[Optional[str], Optional[str], List[str]]:
    for pattern, entity_type in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return entity_type, match.group(1), [f"pattern:{entity_type}"]
    return None, None, []


def looks_like_sql(text: str, details: Dict[str, Any]) -> bool:
    if details.get("operation") and (details.get("table") or details.get("database")):
        return True
    return bool(SQL_OPERATION_PATTERN.search(text) and SQL_TABLE_PATTERN.search(text))


def build_corpus(text: str, details: Dict[str, Any]) -> str:
    values = [text]
    values.extend(str(value) for value in details.values() if value is not None)
    return " ".join(values)


def default_strategies() -> List[DbDialectStrategy]:
    return [
        MetadataDialectStrategy(),
        RegexDialectStrategy("postgresql", "relational", "postgresql", (
            r"\b(?:jdbc:postgresql:|postgresql://|postgres://)\b|\bpostgres(?:ql)?\b",
        ), "high"),
        RegexDialectStrategy("postgresql", "relational", "postgresql", (
            r"\bILIKE\b|\bRETURNING\b|::[A-Za-z_][\w]*|\bJSONB\b|\bSERIAL\b",
        ), "medium"),
        RegexDialectStrategy("mysql", "relational", "mysql", (
            r"\b(?:jdbc:mysql:|mysql://)\b|\bmysql\b",
        ), "high"),
        RegexDialectStrategy("mysql", "relational", "mysql", (
            r"\bAUTO_INCREMENT\b|\bON\s+DUPLICATE\s+KEY\b|`[A-Za-z_][\w]*`",
        ), "medium"),
        RegexDialectStrategy("mariadb", "relational", "mariadb", (
            r"\b(?:jdbc:mariadb:|mariadb://)\b|\bmariadb\b",
        ), "high"),
        RegexDialectStrategy("oracle", "relational", "oracle", (
            r"\bjdbc:oracle:|\boracle\b",
        ), "high"),
        RegexDialectStrategy("oracle", "relational", "oracle", (
            r"\bROWNUM\b|\bSYSDATE\b|\bNVL\s*\(|\bDUAL\b|\.NEXTVAL\b",
        ), "medium"),
        RegexDialectStrategy("sqlserver", "relational", "sqlserver", (
            r"\b(?:jdbc:sqlserver:|sqlserver://)\b|\bsql\s*server\b|\bmssql\b",
        ), "high"),
        RegexDialectStrategy("sqlserver", "relational", "sqlserver", (
            r"\bTOP\s+\d+\b|\bGETDATE\s*\(|\bNVARCHAR\b|\[[A-Za-z_][\w]*\]",
        ), "medium"),
        RegexDialectStrategy("sqlite", "relational", "sqlite", (
            r"\b(?:jdbc:sqlite:|sqlite://|sqlite:)\b|\bsqlite\b",
        ), "high"),
        RegexDialectStrategy("db2", "relational", "db2", (
            r"\b(?:jdbc:db2:|db2://)\b|\bdb2\b",
        ), "high"),
        RegexDialectStrategy("h2", "relational", "h2", (r"\bjdbc:h2:|\bh2\b",), "high"),
        RegexDialectStrategy("redshift", "relational", "redshift", (
            r"\b(?:jdbc:redshift:|redshift://)\b|\bredshift\b",
        ), "high"),
        RegexDialectStrategy("snowflake", "relational", "snowflake", (
            r"\b(?:jdbc:snowflake:|snowflake://)\b|\bsnowflake\b",
        ), "high"),
        RegexDialectStrategy("clickhouse", "relational", "clickhouse", (
            r"\b(?:jdbc:clickhouse:|clickhouse://)\b|\bclickhouse\b",
        ), "high"),
        RegexDialectStrategy("mongodb", "document", "mongodb", (
            r"\b(?:mongodb://|mongodb\+srv://)\b|\bmongodb\b",
        ), "high"),
        RegexDialectStrategy("mongodb", "document", "mongodb", (
            r"\bdb\.[A-Za-z_][\w]*\.(?:find|findOne|insertOne|updateOne|deleteOne|aggregate)\b|\bObjectId\s*\(",
        ), "medium"),
        RegexDialectStrategy("redis", "key-value", "redis", (
            r"\b(?:redis://|rediss://)\b|\bredis\b",
        ), "high"),
        RegexDialectStrategy("redis", "key-value", "redis", (
            r"\b(?:HGET|HSET|HDEL|EXPIRE|LPUSH|RPUSH|ZADD)\b|\bredis\.(?:get|set|del)\b",
        ), "medium"),
        RegexDialectStrategy("dynamodb", "key-value", "dynamodb", (
            r"\bdynamodb\b|\b(?:GetItem|PutItem|UpdateItem|DeleteItem|BatchWriteItem)\b|\bTableName\b",
        ), "high"),
        RegexDialectStrategy("dynamodb", "key-value", "dynamodb", (
            r"\bdynamodb\.(?:query|scan)\s*\(",
        ), "medium"),
        RegexDialectStrategy("cassandra", "wide-column", "cassandra", (
            r"\b(?:cassandra://|cqlsh|cql)\b|\bcassandra\b",
        ), "high"),
        RegexDialectStrategy("cassandra", "wide-column", "cassandra", (
            r"\bKEYSPACE\b|\bALLOW\s+FILTERING\b",
        ), "medium"),
        RegexDialectStrategy("elasticsearch", "search", "elasticsearch", (
            r"\belasticsearch\b|\bopensearch\b|/_search\b|\b_search\b",
        ), "high"),
        RegexDialectStrategy("neo4j", "graph", "neo4j", (
            r"\b(?:neo4j://|bolt://)\b|\bneo4j\b|\bcypher\b",
        ), "high"),
        RegexDialectStrategy("neo4j", "graph", "neo4j", (
            r"\bMATCH\s*\([^)]*\)\s*RETURN\b",
        ), "medium"),
        GenericSqlStrategy(),
    ]
