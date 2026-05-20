# Graph Traversal

> Concept nodes are **global hubs**: every section across all documents that receives the same concept (e.g. `gdpr`) points to the same single Concept node in GraphDB. This enables retrieval strategies that go beyond what vector search alone can reach.

---

## Table of Contents

- [Overview](#overview)
- [2-hop: Cross-section Concept Traversal](#2-hop-cross-section-concept-traversal)
- [3-hop: Concept Co-occurrence Expansion](#3-hop-concept-co-occurrence-expansion)
- [Retrieval Pipeline](#retrieval-pipeline)
- [Configuration](#configuration)
- [SPARQL Queries](#sparql-queries)

---

## Overview

Graph traversal runs **on top of** vector search results. After the initial vector search identifies seed sections, the graph traversal strategies discover additional relevant chunks that may not be semantically similar but are structurally connected through the knowledge graph.

There are two traversal strategies:

| Strategy | Hops | What it finds |
|----------|------|---------------|
| 2-hop Concept Traversal | `seed_section → Concept → related_section → chunk` | Sections sharing concepts with vector results |
| 3-hop Co-occurrence Traversal | `seed_section → Concept_A → Concept_B → related_section → chunk` | Sections thematically adjacent to vector results |

---

## 2-hop: Cross-section Concept Traversal

Starting from a section found by vector search, the graph follows its concepts to discover *all other sections in the knowledge base that share at least one concept*.

### Path

```
seed_section --hasConcept--> Concept <--hasConcept-- related_section --isContained--> chunk
```

### How It Works

1. Vector search returns top-N seed sections
2. For each seed section, follow `hasConcept` edges to find associated Concept nodes
3. For each Concept node, find all other sections that share the same concept via `hasConcept`
4. For each related section, follow `isContained` to get the constituent chunks

### Example

If the vector search finds a section about "GDPR compliance requirements" labeled with concept `gdpr`, the 2-hop traversal will discover all other sections across all documents that also have the `gdpr` concept — even if they use completely different vocabulary (e.g., "data protection obligations" vs. "privacy regulations").

### Why It Matters

This retrieves chunks that may use **completely different vocabulary** but are structurally labeled with the same concept — something cosine similarity cannot find.

---

## 3-hop: Concept Co-occurrence Expansion

After each document is ingested, `build_concept_cooccurrence()` scans all sections and inserts a `ki4kmu:coOccursWith` edge between every pair of concepts that appear together on the same section. This builds a **concept-level co-occurrence graph** automatically.

At query time, the traversal extends one more hop beyond the 2-hop strategy.

### Path

```
seed_section --hasConcept--> Concept_A --coOccursWith--> Concept_B <--hasConcept-- related_section --isContained--> chunk
```

### How It Works

1. **Post-ingestion:** For each section, identify all pairs of concepts and insert symmetric `coOccursWith` edges
2. **At query time:**
   - Start from seed sections (from vector search)
   - Follow `hasConcept` to get Concept_A
   - Follow `coOccursWith` to get Concept_B (thematically related concepts)
   - Follow `hasConcept` from Concept_B to find related sections
   - Follow `isContained` to get chunks

### Example

If `gdpr` and `datenschutzbeauftragter` (data protection officer) co-occur frequently on the same sections, a query seeding on `gdpr` will also surface chunks labeled only with `datenschutzbeauftragter` — even though they share no direct concept.

### Why It Matters

This retrieves chunks about **topics that tend to go with** the seed section's concepts, even if they share no concept directly. It captures thematic adjacency that neither vector search nor direct concept sharing can reach.

---

## Retrieval Pipeline

Each retrieval arm operates independently and contributes candidates to a merged pool:

| Stage | Source | What it finds | Limit |
|-------|--------|---------------|-------|
| 1 | ChromaDB vector search | Embedding-similar sections | `VECTOR_TOP_K` (default: 50) |
| 2 | GraphDB keyword search | Sections whose concepts/keyphrases match query terms | `VECTOR_TOP_K` (default: 50) |
| 3 | GraphDB 2-hop concept traversal | Sections sharing concepts with vector results | Up to `TRAVERSAL_LIMIT` (default: 100) total |
| 4 | GraphDB 3-hop co-occurrence traversal | Sections thematically adjacent to vector results | Up to `TRAVERSAL_LIMIT` (default: 100) total |
| 5 | Qwen3-Reranker-0.6B | Final ranked top-k from merged pool | `top_k` |

### Pipeline Flow

```
Query
  │
  ├─→ [Vector Search] ──────────────────────────────┐
  │    ChromaDB                                       │
  │                                                   ▼
  ├─→ [Graph Keyword] ──────────────────────────┐    ┌──────────┐
  │    GraphDB concept/keyphrase match           │    │  Merge   │
  │                                               │───→│ & Dedup  │
  ├─→ [2-hop Concept] ────────────────────────┐  │    └────┬─────┘
  │    seed → concept → related sections       ││         │
  │                                             ▼▼         ▼
  ├─→ [3-hop Co-occurrence] ─────────────┐    ┌──────────┐
  │    seed → concept_A → concept_B →    │───→│  Rerank  │───→ Top-k Results
  │    related sections                   │    └──────────┘
  └──────────────────────────────────────┘
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `VECTOR_TOP_K` | 50 | Maximum candidates per retrieval arm (vector, keyword, traversal) |
| `TRAVERSAL_LIMIT` | 100 | Maximum unique chunks collected from traversal expansion |
| `top_k` | 5 | Final number of results after reranking (query-time parameter) |

---

## SPARQL Queries

The following SPARQL queries are used for graph-based retrieval:

| Query File | Purpose |
|------------|---------|
| [`app/infrastructure/sparql/search_concepts.sparql`](../app/infrastructure/sparql/search_concepts.sparql) | Find sections by matching query terms against concept labels |
| [`app/infrastructure/sparql/search_keyphrases.sparql`](../app/infrastructure/sparql/search_keyphrases.sparql) | Find sections by matching query terms against keyphrase labels |
| [`app/infrastructure/sparql/find_related_chunks_via_concept.sparql`](../app/infrastructure/sparql/find_related_chunks_via_concept.sparql) | 2-hop concept traversal |
| [`app/infrastructure/sparql/find_related_chunks_via_cooccurrence.sparql`](../app/infrastructure/sparql/find_related_chunks_via_cooccurrence.sparql) | 3-hop co-occurrence traversal |

### 2-hop Query Pattern

```sparql
# find_related_chunks_via_concept.sparql
PREFIX ki4kmu: <http://example.com/ki4kmu#>

SELECT DISTINCT ?chunk ?chunk_text ?page_number ?seed_section
WHERE {
  ?seed_section ki4kmu:hasConcept ?concept .
  ?concept ki4kmu:hasConcept ?related_section .
  ?related_section ki4kmu:isContained ?chunk .
  ?chunk ki4kmu:text ?chunk_text .
  ?chunk ki4kmu:page_number ?page_number .
  FILTER(?related_section != ?seed_section)
}
```

### 3-hop Query Pattern

```sparql
# find_related_chunks_via_cooccurrence.sparql
PREFIX ki4kmu: <http://example.com/ki4kmu#>

SELECT DISTINCT ?chunk ?chunk_text ?page_number ?seed_section
WHERE {
  ?seed_section ki4kmu:hasConcept ?concept_a .
  ?concept_a ki4kmu:coOccursWith ?concept_b .
  ?concept_b ki4kmu:hasConcept ?related_section .
  ?related_section ki4kmu:isContained ?chunk .
  ?chunk ki4kmu:text ?chunk_text .
  ?chunk ki4kmu:page_number ?page_number .
  FILTER(?related_section != ?seed_section)
}
```
