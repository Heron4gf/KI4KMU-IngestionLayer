#!/usr/bin/env python3
"""Generate prompts/extract.md from the LinkML schema.

Usage:
    python ontology/generate_prompt.py

Outputs prompts/extract.md — the extraction prompt consumed by the
langextract-service. Re-run whenever the schema changes.
"""
from pathlib import Path
import yaml

SCHEMA_PATH = Path(__file__).parent / "ki_kmu_schema.yaml"
OUTPUT_PATH = Path(__file__).parent.parent / "prompts" / "extract.md"


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_prompt(schema: dict) -> str:
    classes = schema.get("classes", {})
    enums   = schema.get("enums", {})

    # Collect concrete (non-abstract) entity classes
    entity_classes = {
        name: cls for name, cls in classes.items()
        if not cls.get("abstract", False) and name != "Beziehung"
    }

    # Collect relationship types from enum
    rel_types = list(
        enums.get("BeziehungsTyp", {}).get("permissible_values", {}).keys()
    )

    lines = [
        "# KI-4-KMU Entity & Relationship Extraction",
        "",
        "Extrahiere Entitäten und typisierte Beziehungen aus dem deutschen Text.",
        "Verwende **ausschließlich** den exakten Wortlaut des Textes für `extraction_text`.",
        "Überschneide keine Entitäten. Gib alle relevanten Attribute an.",
        "",
        "---",
        "",
        "## Entitätsklassen",
        "",
    ]

    for class_name, cls_def in entity_classes.items():
        desc = cls_def.get("description", "")
        attrs = cls_def.get("attributes", {})
        # Inherit attributes from Entitaet (id, extraction_text already documented globally)
        attr_list = ", ".join(
            f"`{a}`" for a in attrs
            if a not in ("id", "extraction_text", "quelle_chunk_id")
        ) or "–"
        lines.append(f"### `{class_name.lower()}`")
        lines.append(f"{desc}")
        lines.append(f"**Attribute:** {attr_list}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Beziehungen",
        "",
        "Extrahiere auch gerichtete Beziehungen zwischen Entitäten.",
        "Verwende `extraction_class = \"beziehung\"` mit folgenden Attributen:",
        "",
        "- `typ`: einer der folgenden Werte:",
    ]
    for rt in rel_types:
        desc = (
            enums["BeziehungsTyp"]["permissible_values"]
            .get(rt, {})
            .get("description", "")
        )
        lines.append(f"  - `{rt}`" + (f" — {desc}" if desc else ""))

    lines += [
        "",
        "- `subjekt_id`: `id` der Quell-Entität",
        "- `objekt_id`: `id` der Ziel-Entität",
        "- `kontext`: optionaler Original-Satz aus dem Text",
        "",
        "---",
        "",
        "## Allgemeine Regeln",
        "",
        "- Jede Entität bekommt ein `id`-Attribut: snake_case-Kurzform des `extraction_text`.",
        "- Extrahiere keine doppelten Entitäten; wiederholte Nennungen → gleiche `id`.",
        "- Lass Attribute weg, wenn sie im Text nicht erkennbar sind (kein Raten).",
        "- Beziehungen nur extrahieren, wenn Subjekt UND Objekt ebenfalls extrahiert wurden.",
    ]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    schema = load_schema()
    prompt = render_prompt(schema)
    OUTPUT_PATH.write_text(prompt, encoding="utf-8")
    print(f"Written {len(prompt)} chars → {OUTPUT_PATH}")
