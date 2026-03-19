import dataclasses
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import langextract as lx

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

API_KEY     = os.environ["LANGEXTRACT_API_KEY"]
MODEL_ID    = os.environ["LANGEXTRACT_MODEL_ID"]
PROMPT_PATH = os.environ["LANGEXTRACT_PROMPT_PATH"]
BASE_URL    = os.environ.get("LANGEXTRACT_BASE_URL")

MAX_CHAR_BUFFER = 10_000_000


def _load_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {PROMPT_PATH}")
    return path.read_text(encoding="utf-8").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_prompt()
    logger.info("LangExtract service ready — model=%s  base_url=%s", MODEL_ID, BASE_URL or "<openai default>")
    yield


app = FastAPI(title="LangExtract Service", lifespan=lifespan)


class ExtractRequest(BaseModel):
    text: str
    examples: list[dict] = []


class ExtractResponse(BaseModel):
    extractions: list[dict]


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    prompt = _load_prompt()
    model_params = {"base_url": BASE_URL} if BASE_URL else {}

    try:
        result = lx.extract(
            text_or_documents=req.text,
            prompt_description=prompt,
            examples=req.examples or _default_examples(),
            model_id=MODEL_ID,
            api_key=API_KEY,
            language_model_params=model_params,
            max_char_buffer=MAX_CHAR_BUFFER,
            show_progress=False,
            fence_output=True,
            use_schema_constraints=False,
        )
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    docs = result if isinstance(result, list) else [result]
    extractions = [
        dataclasses.asdict(ann)
        for doc in docs
        for ann in (doc.extractions or [])
        if ann is not None
    ]
    return ExtractResponse(extractions=extractions)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# KI-4-KMU Ontology
# Hierarchy: ki_methode → phase → ebene → schritt → analyse_werkzeug
# Parallel domain classes: organisation, ki_anwendung, aufgabe, ki_system,
#                          technologie, rahmenwerk, rolle, ziel,
#                          portfolio_kategorie, persona, workshop
# ---------------------------------------------------------------------------

ONTOLOGY_CLASSES = [
    {
        "name": "ki_methode",
        "beschreibung": "Die KI-4-KMU-Methode als Ganzes. Wurzel der Ontologie-Hierarchie.",
        "attribute": ["anzahl_phasen", "herausgeber", "version"],
    },
    {
        "name": "phase",
        "beschreibung": "Eine der drei Hauptphasen der KI-4-KMU-Methode (Design-Phase, Build-Phase, Run-Phase).",
        "uebergeordnet": "ki_methode",
        "attribute": ["sequenz_nummer", "ziel", "zugehoerige_methode"],
    },
    {
        "name": "ebene",
        "beschreibung": "Betrachtungsebene innerhalb einer Phase: Unternehmensebene, Prozessebene, Aufgabenebene.",
        "uebergeordnet": "phase",
        "attribute": ["sequenz_nummer", "zugehoerige_phase"],
    },
    {
        "name": "schritt",
        "beschreibung": "Nummerierter Teilschritt innerhalb einer Ebene, z.B. '1.1 Situation und Erwartungen'.",
        "uebergeordnet": "ebene",
        "attribute": ["nummer", "titel", "zugehoerige_ebene"],
    },
    {
        "name": "analyse_werkzeug",
        "beschreibung": "Strategisches Analyse-Werkzeug oder Canvas, eingesetzt in einem Schritt (z.B. Portfolio-Matrix, Capability Map, BSC, 2x2-Matrix, Brainstorming).",
        "uebergeordnet": "schritt",
        "attribute": ["typ", "einsatzbereich"],
    },
    {
        "name": "ki_anwendung",
        "beschreibung": "Konkreter KI-Anwendungsfall, der für eine Organisation identifiziert wurde.",
        "attribute": ["machbarkeit", "impact", "daten_vorhanden", "entwicklungstyp"],
    },
    {
        "name": "aufgabe",
        "beschreibung": "Wissensintensive (WIA) oder datenintensive (DIA) Aufgabe innerhalb eines Geschäftsprozesses.",
        "attribute": ["aufgabentyp", "prozess_id"],
    },
    {
        "name": "ki_system",
        "beschreibung": "Konkretes KI-System oder Produkt (z.B. LLM, spezialisierte Lösung, Dienst).",
        "attribute": ["kategorie", "anbieter"],
    },
    {
        "name": "technologie",
        "beschreibung": "KI- oder Digitaltechnologie-Kategorie (z.B. TensorFlow, Neo4j, Spracherkennung).",
        "attribute": ["unterkategorie", "reifegrad"],
    },
    {
        "name": "rahmenwerk",
        "beschreibung": "Regulatorischer oder normativer Rahmen (z.B. EU AI Act, DSGVO, DSG).",
        "attribute": ["herausgeber", "zweck", "geltungsbereich"],
    },
    {
        "name": "organisation",
        "beschreibung": "Unternehmen, Hochschule, Behörde oder Konsortium.",
        "attribute": ["branche", "groesse", "rolle_im_projekt"],
    },
    {
        "name": "rolle",
        "beschreibung": "Akteur, Berufsrolle oder Funktion innerhalb eines Prozesses oder Projekts.",
        "attribute": ["verantwortung", "organisation"],
    },
    {
        "name": "ziel",
        "beschreibung": "Strategisches oder operatives Ziel, formuliert gemäss Balanced Scorecard (BSC).",
        "attribute": ["bsc_kategorie", "kpi", "perspektive"],
    },
    {
        "name": "portfolio_kategorie",
        "beschreibung": "Segment der BCG-Portfolio-Matrix: Star, Cash Cow, Question Mark, Poor Dog.",
        "attribute": ["marktwachstum", "relativer_marktanteil"],
    },
    {
        "name": "persona",
        "beschreibung": "Fiktiver, repräsentativer Nutzertyp aus der Design-Thinking-Methode.",
        "attribute": ["ziele", "beduerfnisse"],
    },
    {
        "name": "workshop",
        "beschreibung": "Strukturiertes Workshop-Event zur Anwendung der KI-4-KMU-Methode.",
        "attribute": ["datum", "ort", "workshop_typ"],
    },
]


def _default_examples():
    from langextract.core.data import ExampleData

    return [
        # Example 1: Hierarchy — ki_methode → phase → ebene → schritt → analyse_werkzeug
        ExampleData(
            text=(
                "Die KI-4-KMU-Methode umfasst drei Phasen: Design, Build und Run. "
                "In der Design-Phase wird auf der Unternehmensebene mit einer Portfolioanalyse "
                "gestartet, wobei die Portfolio-Matrix zur Priorisierung von KI-Anwendungsoptionen eingesetzt wird."
            ),
            extractions=[
                lx.data.Extraction(
                    extraction_class="ki_methode",
                    extraction_text="KI-4-KMU-Methode",
                    attributes={"id": "ki_4_kmu_methode", "anzahl_phasen": "3", "herausgeber": "FHNW"}
                ),
                lx.data.Extraction(
                    extraction_class="phase",
                    extraction_text="Design-Phase",
                    attributes={"id": "design_phase", "sequenz_nummer": "1", "zugehoerige_methode": "ki_4_kmu_methode"}
                ),
                lx.data.Extraction(
                    extraction_class="phase",
                    extraction_text="Build-Phase",
                    attributes={"id": "build_phase", "sequenz_nummer": "2", "zugehoerige_methode": "ki_4_kmu_methode"}
                ),
                lx.data.Extraction(
                    extraction_class="phase",
                    extraction_text="Run-Phase",
                    attributes={"id": "run_phase", "sequenz_nummer": "3", "zugehoerige_methode": "ki_4_kmu_methode"}
                ),
                lx.data.Extraction(
                    extraction_class="ebene",
                    extraction_text="Unternehmensebene",
                    attributes={"id": "unternehmensebene", "sequenz_nummer": "1", "zugehoerige_phase": "design_phase"}
                ),
                lx.data.Extraction(
                    extraction_class="schritt",
                    extraction_text="Portfolioanalyse",
                    attributes={"id": "portfolioanalyse", "nummer": "1.2", "zugehoerige_ebene": "unternehmensebene"}
                ),
                lx.data.Extraction(
                    extraction_class="analyse_werkzeug",
                    extraction_text="Portfolio-Matrix",
                    attributes={"id": "portfolio_matrix", "typ": "Matrix", "einsatzbereich": "Strategische Priorisierung"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="KI-4-KMU-Methode besteht aus Design-Phase",
                    attributes={"typ": "besteht_aus", "subjekt_id": "ki_4_kmu_methode", "objekt_id": "design_phase"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="Design-Phase besteht aus Unternehmensebene",
                    attributes={"typ": "besteht_aus", "subjekt_id": "design_phase", "objekt_id": "unternehmensebene"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="Design-Phase ist Vorgänger von Build-Phase",
                    attributes={"typ": "ist_vorlaeufer_von", "subjekt_id": "design_phase", "objekt_id": "build_phase"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="Unternehmensebene beinhaltet Schritt Portfolioanalyse",
                    attributes={"typ": "beinhaltet_schritt", "subjekt_id": "unternehmensebene", "objekt_id": "portfolioanalyse"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="Portfolioanalyse verwendet Portfolio-Matrix",
                    attributes={"typ": "verwendet_werkzeug", "subjekt_id": "portfolioanalyse", "objekt_id": "portfolio_matrix"}
                ),
            ]
        ),
        # Example 2: Domain entities — organisation, ki_anwendung, aufgabe, ki_system, rahmenwerk, rolle, ziel
        ExampleData(
            text=(
                "Die FHNW hat im Workshop in Olten einen KI-Anwendungsfall im Kundenservice identifiziert. "
                "Die wissensintensive Aufgabe der Anfragenklassifikation soll durch einen LLM-basierten Chatbot optimiert werden. "
                "Der EU AI Act reguliert den Einsatz solcher Systeme. "
                "Ziel Z1 ist die Reduktion der Antwortzeit um 30%."
            ),
            extractions=[
                lx.data.Extraction(
                    extraction_class="organisation",
                    extraction_text="FHNW",
                    attributes={"id": "fhnw", "branche": "Hochschule", "rolle_im_projekt": "Forschungspartner"}
                ),
                lx.data.Extraction(
                    extraction_class="workshop",
                    extraction_text="Workshop in Olten",
                    attributes={"id": "workshop_olten", "ort": "Olten", "workshop_typ": "KI-4-KMU"}
                ),
                lx.data.Extraction(
                    extraction_class="ki_anwendung",
                    extraction_text="KI-Anwendungsfall im Kundenservice",
                    attributes={"id": "ki_kundenservice", "entwicklungstyp": "wissensbasiert"}
                ),
                lx.data.Extraction(
                    extraction_class="aufgabe",
                    extraction_text="Anfragenklassifikation",
                    attributes={"id": "anfragenklassifikation", "aufgabentyp": "wissensintensiv"}
                ),
                lx.data.Extraction(
                    extraction_class="ki_system",
                    extraction_text="LLM-basierten Chatbot",
                    attributes={"id": "llm_chatbot", "kategorie": "generisch"}
                ),
                lx.data.Extraction(
                    extraction_class="rahmenwerk",
                    extraction_text="EU AI Act",
                    attributes={"id": "eu_ai_act", "herausgeber": "EU", "zweck": "Regulierung von KI-Systemen"}
                ),
                lx.data.Extraction(
                    extraction_class="ziel",
                    extraction_text="Ziel Z1",
                    attributes={"id": "ziel_z1", "bsc_kategorie": "Prozesse", "kpi": "Antwortzeit -30%", "perspektive": "intern"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="FHNW teilnimmt an Workshop in Olten",
                    attributes={"typ": "teilnimmt_an", "subjekt_id": "fhnw", "objekt_id": "workshop_olten"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="FHNW hat KI-Anwendungsfall im Kundenservice",
                    attributes={"typ": "hat_use_case", "subjekt_id": "fhnw", "objekt_id": "ki_kundenservice"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="KI-Anwendungsfall optimiert Anfragenklassifikation",
                    attributes={"typ": "optimiert", "subjekt_id": "ki_kundenservice", "objekt_id": "anfragenklassifikation",
                                "kontext": "Die wissensintensive Aufgabe der Anfragenklassifikation soll durch einen LLM-basierten Chatbot optimiert werden."}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="KI-Anwendungsfall nutzt LLM-basierten Chatbot",
                    attributes={"typ": "nutzt", "subjekt_id": "ki_kundenservice", "objekt_id": "llm_chatbot"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="EU AI Act reguliert LLM-basierten Chatbot",
                    attributes={"typ": "reguliert", "subjekt_id": "eu_ai_act", "objekt_id": "llm_chatbot"}
                ),
                lx.data.Extraction(
                    extraction_class="beziehung",
                    extraction_text="KI-Anwendungsfall hat Ziel Z1",
                    attributes={"typ": "hat_ziel", "subjekt_id": "ki_kundenservice", "objekt_id": "ziel_z1"}
                ),
            ]
        ),
    ]
