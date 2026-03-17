# KI-4-KMU Ontology

This directory contains the **single source of truth** for all entity types,
relationship types and their attributes used across the ingestion pipeline.

## Files

| File | Purpose |
|------|---------|
| `ki_kmu_schema.yaml` | LinkML schema — defines all classes, enums and attributes |
| `generate_prompt.py` | Script that renders `prompts/extract.md` from the schema |

## Workflow

```
ki_kmu_schema.yaml
    │
    ├─▶ generate_prompt.py  →  prompts/extract.md        (LLM extraction prompt)
    ├─▶ gen-pydantic         →  app/models/generated.py  (optional: Pydantic models)
    └─▶ gen-owl              →  ontology/ki_kmu.owl.ttl  (OWL export for RDF reasoner)
```

## Regenerating the prompt

Run this whenever you edit `ki_kmu_schema.yaml`:

```bash
python ontology/generate_prompt.py
```

## Generating OWL for the RDF reasoner

```bash
pip install linkml
gen-owl ontology/ki_kmu_schema.yaml > ontology/ki_kmu.owl.ttl
```

## Adding a new entity class

1. Add the class to `ki_kmu_schema.yaml` under `classes:`
2. Run `python ontology/generate_prompt.py` to update `prompts/extract.md`
3. No changes needed in `graphdb_writer.py` — it reads valid types from the schema at startup
