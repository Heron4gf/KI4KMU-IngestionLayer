# KI-4-KMU Entity & Relationship Extraction

Extrahiere Entitäten und typisierte Beziehungen aus dem deutschen Text.
Verwende **ausschließlich** den exakten Wortlaut des Textes für `extraction_text`.
Überschneide keine Entitäten. Gib alle relevanten Attribute an.

---

## Entitätsklassen

### `organisation`
A company, university, public body or consortium (e.g. FHNW, KMU, Swisscom)
**Attribute:** `branche`, `groesse`, `rolle_im_projekt`

### `methode`
A structured methodology or framework (e.g. KI-4-KMU-Methode, Design Thinking)
**Attribute:** `zielgruppe`, `anzahl_phasen`

### `phase`
A named phase within a methodology (Design, Build, Run)
**Attribute:** `sequenz_nummer`, `ziel`, `zugehoerige_methode`

### `iteration`
A sub-level iteration within a phase (Unternehmensebene, Prozessebene, Aufgabenebene)
**Attribute:** `ebene`, `zugehoerige_phase`

### `tool`
A concrete workshop instrument or canvas (Business Model Canvas, Portfolio-Matrix)
**Attribute:** `anbieter`, `einsatzbereich`, `iteration`

### `use_case`
A concrete AI application scenario identified for an organisation
**Attribute:** `impact`, `machbarkeit`, `daten_vorhanden`, `entwicklungstyp`

### `technologie`
An AI or digital technology category (Machine Learning, NLP, Computer Vision)
**Attribute:** `unterkategorie`, `reifegrad`

### `konzept`
An abstract domain concept or term (Datenkompetenz, Wertschöpfungskette)
**Attribute:** `definition`, `bereich`

### `rolle`
A person, job function or actor (Data Scientist, Geschäftsführer)
**Attribute:** `verantwortung`, `organisation`

### `rahmenwerk`
A regulatory or normative framework (EU AI Act, ISO 42001)
**Attribute:** `herausgeber`, `zweck`, `geltungsbereich`

### `workshop`
A structured workshop event (Pilotworkshop, Validierungsworkshop)
**Attribute:** `datum`, `ort`, `workshop_typ`

---

## Beziehungen

Extrahiere auch gerichtete Beziehungen zwischen Entitäten.
Verwende `extraction_class = "beziehung"` mit folgenden Attributen:

- `typ`: einer der folgenden Werte:
  - `besteht_aus` — A method/phase consists of sub-elements
  - `verwendet` — An actor or phase uses a tool or technology
  - `hat_use_case` — An organisation has an identified AI use-case
  - `optimiert` — A use-case optimises a process
  - `nutzt` — A use-case leverages an AI technology
  - `teilnimmt_an` — An organisation or person participates in a workshop
  - `ist_vorlaeufer_von` — Temporal/sequential predecessor relationship (e.g. phase order)
  - `reguliert` — A framework regulates a technology or practice
  - `erfordert` — Something requires a prerequisite

- `subjekt_id`: `id` der Quell-Entität
- `objekt_id`: `id` der Ziel-Entität
- `kontext`: optionaler Original-Satz aus dem Text

---

## Allgemeine Regeln

- Jede Entität bekommt ein `id`-Attribut: snake_case-Kurzform des `extraction_text`.
- Extrahiere keine doppelten Entitäten; wiederholte Nennungen → gleiche `id`.
- Lass Attribute weg, wenn sie im Text nicht erkennbar sind (kein Raten).
- Beziehungen nur extrahieren, wenn Subjekt UND Objekt ebenfalls extrahiert wurden.
