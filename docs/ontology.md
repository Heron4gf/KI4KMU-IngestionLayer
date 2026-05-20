# Ontology Reference

> The system uses a custom RDF/OWL ontology (`ontology/ontology.ttl`) to represent document knowledge in GraphDB (Ontotext).

---

## Table of Contents

- [Overview](#overview)
- [Classes](#classes)
- [Object Properties (Relationships)](#object-properties-relationships)
- [Datatype Properties](#datatype-properties)
- [Schema Diagram](#schema-diagram)
- [Example RDF Triples](#example-rdf-triples)

---

## Overview

The ontology defines a hierarchical structure for representing ingested PDF documents as a knowledge graph. Each PDF becomes a `Document` node, which contains `Chunk` nodes (raw text extracted from pages). Each chunk may contain multiple `Section` nodes (logical sections identified by the SLM). Sections are further specialized as `Text` or `Image` subclasses.

Concepts and keyphrases extracted from sections serve as retrieval labels, enabling both semantic and keyword-based search.

---

## Classes

| Class | Description | Subclasses |
|-------|-------------|------------|
| `Document` | An ingested PDF file | — |
| `Chunk` | A raw text chunk extracted from a document page | — |
| `Section` | A logical section identified by the SLM within a chunk | `Text`, `Image` |
| `Text` | A textual section (subclass of `Section`) | — |
| `Image` | An image section extracted from a document page (subclass of `Section`) | — |
| `Concept` | A retrieval label assigned to a section by the SLM (e.g. `"compression"`, `"GDPR"`) | — |
| `Keyphrase` | A lemmatized keyword algorithmically extracted from section text | — |

### Class Hierarchy

```
rdf:type
├── Document
├── Chunk
└── Section
    ├── Text
    └── Image
├── Concept
└── Keyphrase
```

---

## Object Properties (Relationships)

| Subject | Predicate | Object | Direction | Description |
|---------|-----------|--------|-----------|-------------|
| `Chunk` | `belongsTo` | `Document` | → | Links a chunk to its source document |
| `Chunk` / `Text` / `Image` | `isContained` | `Section` | → | Chunk/section is contained in a section *(direction: chunk is contained in section)* |
| `Section` | `hasConcept` | `Concept` | → | Associates a section with a retrieval concept |
| `Text` | `hasKeyphrase` | `Keyphrase` | → | Associates a text section with a keyphrase |
| `Concept` | `coOccursWith` | `Concept` | ↔ | Co-occurrence edge between concepts on the same section *(symmetric, built post-ingestion)* |

### Relationship Diagram

```
Document
  └── belongsTo ──→ Chunk
                      │
                      ├── isContained ──→ Section ──→ hasConcept ──→ Concept
                      │                            │
                      │                            └──→ coOccursWith ──→ Concept (symmetric)
                      │
                      └── isContained ──→ Text ──→ hasKeyphrase ──→ Keyphrase
                      │
                      └── isContained ──→ Image
```

---

## Datatype Properties

### Document

| Property | Type | Description |
|----------|------|-------------|
| `document_id` | string | Unique identifier for the document |
| `pdf_hash` | string | SHA-256 hash of the uploaded PDF file |

### Chunk

| Property | Type | Description |
|----------|------|-------------|
| `text` | string | Raw text content of the chunk |
| `chunk_index` | integer | Sequential index of the chunk within the document |
| `page_number` | integer | Page number from which the chunk was extracted |

### Section

| Property | Type | Description |
|----------|------|-------------|
| `section_id` | string | Unique identifier for the section |
| `section_uuid` | string | UUID for the section |

### Image

| Property | Type | Description |
|----------|------|-------------|
| `image_base64` | string | Base64-encoded image data |
| `page_number` | integer | Page number from which the image was extracted |

### Concept

| Property | Type | Description |
|----------|------|-------------|
| `concept_label` | string | The concept label text (e.g. `"compression"`, `"GDPR"`) |

---

## Example RDF Triples

### Document and Chunk

```turtle
<urn:uuid:aabbccdd-1234-5678-abcd-000000000000> a ki4kmu:Document ;
    ki4kmu:document_id "aabbccdd-1234-5678-abcd-000000000000" ;
    ki4kmu:pdf_hash "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" .

<urn:chunk:aabbccdd-1234-5678-abcd-000000000000_chunk_3> a ki4kmu:Chunk ;
    ki4kmu:text "The compression ratio of Chassis 3413GT is 2.1 bars..." ;
    ki4kmu:chunk_index 3 ;
    ki4kmu:page_number 3 ;
    ki4kmu:belongsTo <urn:uuid:aabbccdd-1234-5678-abcd-000000000000> .
```

### Section with Concept

```turtle
<urn:section:uuid-1> a ki4kmu:Section ;
    ki4kmu:section_id "section-uuid-1" ;
    ki4kmu:section_uuid "uuid-1" ;
    ki4kmu:isContained <urn:chunk:aabbccdd-1234-5678-abcd-000000000000_chunk_3> ;
    ki4kmu:hasConcept <urn:concept:compression> .

<urn:concept:compression> a ki4kmu:Concept ;
    ki4kmu:concept_label "compression" .
```

### Co-occurrence Edge

```turtle
<urn:concept:compression> ki4kmu:coOccursWith <urn:concept:chassis> .
<urn:concept:chassis>     ki4kmu:coOccursWith <urn:concept:compression> .
```

---

## Namespace Prefixes

| Prefix | URI |
|--------|-----|
| `ki4kmu` | `http://example.com/ki4kmu#` |
| `rdf` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` |
| `rdfs` | `http://www.w3.org/2000/01/rdf-schema#` |
| `owl` | `http://www.w3.org/2002/07/owl#` |
