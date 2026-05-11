"""SPARQL query loader with placeholder support."""

import re
from pathlib import Path
from typing import Any

_query_cache: dict[str, str] = {}

_RAW_SPARQL_SUFFIXES = ("_uri", "_triple", "_triples", "_sparql")
_RAW_SPARQL_KEYS = {"PREFIXES"}


def load_query(filename: str) -> str:
    if filename in _query_cache:
        return _query_cache[filename]

    query_path = Path(__file__).parent / filename
    if not query_path.exists():
        raise FileNotFoundError(f"Query file not found: {query_path}")

    query = query_path.read_text(encoding="utf-8")
    _query_cache[filename] = query
    return query


def parse_query(query: str, **kwargs: Any) -> str:
    def replace_placeholder(match: re.Match) -> str:
        key = match.group(1)
        if key not in kwargs:
            raise ValueError(f"Missing placeholder: {{{{{key}}}}}")

        value = kwargs[key]

        if key in _RAW_SPARQL_KEYS or any(key.endswith(s) for s in _RAW_SPARQL_SUFFIXES):
            return str(value)

        if isinstance(value, bool):
            return f'"{str(value).lower()}"^^xsd:boolean'
        if isinstance(value, int):
            return f'"{value}"^^xsd:integer'
        if isinstance(value, float):
            return f'"{value}"^^xsd:decimal'

        escaped = (
            str(value)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'

    return re.sub(r"\{\{(\w+)\}\}", replace_placeholder, query)


def load_and_parse(filename: str, **kwargs: Any) -> str:
    query = load_query(filename)
    return parse_query(query, **kwargs)
