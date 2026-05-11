"""SPARQL query loader with placeholder support."""

import re
from pathlib import Path
from typing import Any

# Cache for loaded queries
_query_cache: dict[str, str] = {}


def load_query(filename: str) -> str:
    """Load a SPARQL query from a file, with caching."""
    if filename in _query_cache:
        return _query_cache[filename]
    
    query_path = Path(__file__).parent / filename
    if not query_path.exists():
        raise FileNotFoundError(f"Query file not found: {query_path}")
    
    query = query_path.read_text(encoding="utf-8")
    _query_cache[filename] = query
    return query


def parse_query(query: str, **kwargs: Any) -> str:
    """
    Replace placeholders in a SPARQL query.
    
    Placeholders use the format {{placeholder_name}}.
    Values are automatically formatted based on their type:
    - str: wrapped in quotes (with escaping)
    - int/float: raw numeric value
    - bool: xsd:boolean literal
    
    For URIs, use the _uri placeholder type or pass pre-formatted URI strings.
    """
    def replace_placeholder(match: re.Match) -> str:
        key = match.group(1)
        if key not in kwargs:
            raise ValueError(f"Missing placeholder: {{{{{key}}}}}")
        
        value = kwargs[key]
        
        # Handle special placeholder types
        if key.endswith("_uri"):
            # URIs should be passed as <uri> format
            return str(value)
        
        if isinstance(value, bool):
            return f'"{str(value).lower()}"^^xsd:boolean'
        if isinstance(value, int):
            return f'"{value}"^^xsd:integer'
        if isinstance(value, float):
            return f'"{value}"^^xsd:decimal'
        
        # String values - escape and wrap in triple quotes
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
    """Load a query file and replace placeholders with provided values."""
    query = load_query(filename)
    return parse_query(query, **kwargs)