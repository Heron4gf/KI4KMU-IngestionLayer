import asyncio
import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(os.getenv("SCHEMA_PATH", "schema/predicate_schema.json"))
SCHEMA_MIN_FREQUENCY = int(os.getenv("SCHEMA_MIN_FREQUENCY", "3"))
SCHEMA_LLM_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
SCHEMA_LLM_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SCHEMA_LLM_MODEL = os.getenv("SCHEMA_LLM_MODEL", "google/gemini-2.0-flash-001")


class SchemaCurator:
    """
    Manages the versioned predicate schema.

    On each document enrichment run:
      1. Frequency-prune raw patterns (drop noise below SCHEMA_MIN_FREQUENCY).
      2. Check if any new (type_pair, predicate_surface) combos are not yet mapped.
      3. If new unknown patterns exist, call the LLM — passing the FULL existing schema
         plus the new patterns — to map/extend the schema.
      4. Persist the updated schema to disk.
    """

    def __init__(self) -> None:
        self._schema = self._load()
        self._client = AsyncOpenAI(
            base_url=SCHEMA_LLM_BASE_URL,
            api_key=SCHEMA_LLM_API_KEY,
        )

    def _load(self) -> dict[str, Any]:
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": 0, "entity_types": [], "predicate_map": {}, "merge_map": {}}

    def _save(self) -> None:
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEMA_PATH, "w", encoding="utf-8") as f:
            json.dump(self._schema, f, indent=2, ensure_ascii=False)
        logger.info("[SCHEMA] Saved schema v%d to %s", self._schema["version"], SCHEMA_PATH)

    def get_entity_types(self) -> list[str]:
        return list(self._schema.get("entity_types", []))

    def get_predicate_map(self) -> dict[str, str]:
        """surface_pattern -> canonical ki4kmu predicate name"""
        return dict(self._schema.get("predicate_map", {}))

    def get_merge_map(self) -> dict[str, str]:
        """surface_form -> canonical entity label"""
        return dict(self._schema.get("merge_map", {}))

    async def evolve(self, raw_patterns: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Given raw Stage-1 patterns, frequency-prune then call LLM only for unknown patterns.
        Returns the current (possibly updated) schema dict.
        """
        # Frequency pruning: count (type, surface_text) pairs
        counter: Counter = Counter()
        for p in raw_patterns:
            counter[(p["type"], p["text"].lower())] += 1

        frequent_types: set[str] = {
            type_ for (type_, _), count in counter.items() if count >= SCHEMA_MIN_FREQUENCY
        }

        known_types = set(self._schema.get("entity_types", []))
        new_types = frequent_types - known_types

        if not new_types:
            logger.info("[SCHEMA] No new entity types — schema unchanged (v%d)", self._schema["version"])
            return self._schema

        logger.info("[SCHEMA] %d new entity type patterns detected — invoking LLM", len(new_types))
        updated = await self._llm_evolve(raw_patterns, new_types)
        if updated:
            self._schema = updated
            self._save()

        return self._schema

    async def _llm_evolve(self, raw_patterns: list[dict], new_types: set[str]) -> dict | None:
        existing_schema_json = json.dumps(self._schema, indent=2)
        new_patterns_summary = json.dumps(
            [
                {"type": p["type"], "text": p["text"]}
                for p in raw_patterns
                if p["type"] in new_types
            ][:200],  # cap to avoid huge prompts
            indent=2,
        )

        prompt = f"""You are a knowledge graph schema engineer for an industrial machinery knowledge base (ki4kmu).

EXISTING SCHEMA (versioned — do NOT remove or rename existing entries):
{existing_schema_json}

NEW RAW ENTITY PATTERNS (from NER discovery on new documents):
{new_patterns_summary}

For each new pattern, do ONE of:
  a) Map it to an existing entity_type (add to merge_map: {{"surface": "canonical_type"}})
  b) Propose a new canonical entity_type if semantically distinct (snake_case, domain-specific)
  c) Discard if it is clearly noise

Return ONLY valid JSON with this exact structure (increment version by 1):
{{
  "version": <int>,
  "entity_types": [<all existing + any new>],
  "predicate_map": {{<unchanged existing + any new surface->canonical mappings>}},
  "merge_map": {{<unchanged existing + any new surface->canonical mappings>}}
}}"""

        try:
            response = await self._client.chat.completions.create(
                model=SCHEMA_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = response.choices[0].message.content
            updated = json.loads(content)
            # Structural validation
            assert "version" in updated and "entity_types" in updated
            assert isinstance(updated["entity_types"], list)
            assert updated["version"] > self._schema["version"]
            logger.info("[SCHEMA] LLM evolved schema to v%d", updated["version"])
            return updated
        except Exception as e:
            logger.error("[SCHEMA] LLM schema evolution failed: %s", e)
            return None
