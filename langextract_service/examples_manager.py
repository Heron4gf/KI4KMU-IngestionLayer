"""Examples management for the LangExtract service.

This module handles the default examples used for extraction training and testing.
It separates the example data from the main server logic to improve maintainability
and testability.
"""

from typing import List, Dict, Any

import langextract as lx


class ExamplesManager:
    """Manager for handling extraction examples.
    
    This class encapsulates the logic for providing default examples
    used in the LangExtract service, separating this concern from
    the main server implementation.
    """
    
    @staticmethod
    def get_default_examples() -> List[Dict[str, Any]]:
        """Get the default examples for extraction.
        
        Returns:
            List of example data dictionaries for training/testing extraction.
        """
        from langextract.core.data import ExampleData

        return [
            ExampleData(
                text=(
                    "Die KI-4-KMU-Methode umfasst drei Phasen: Design-Phase, Build-Phase und Run-Phase. "
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
                        extraction_text="Die KI-4-KMU-Methode umfasst drei Phasen: Design-Phase, Build-Phase und Run-Phase.",
                        attributes={"typ": "besteht_aus", "subjekt_id": "ki_4_kmu_methode", "objekt_id": "design_phase"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="In der Design-Phase wird auf der Unternehmensebene mit einer Portfolioanalyse gestartet",
                        attributes={"typ": "besteht_aus", "subjekt_id": "design_phase", "objekt_id": "unternehmensebene"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Die KI-4-KMU-Methode umfasst drei Phasen: Design-Phase, Build-Phase und Run-Phase.",
                        attributes={"typ": "ist_vorlaeufer_von", "subjekt_id": "design_phase", "objekt_id": "build_phase"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="In der Design-Phase wird auf der Unternehmensebene mit einer Portfolioanalyse gestartet",
                        attributes={"typ": "beinhaltet_schritt", "subjekt_id": "unternehmensebene", "objekt_id": "portfolioanalyse"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="wobei die Portfolio-Matrix zur Priorisierung von KI-Anwendungsoptionen eingesetzt wird.",
                        attributes={"typ": "verwendet_werkzeug", "subjekt_id": "portfolioanalyse", "objekt_id": "portfolio_matrix"}
                    ),
                ]
            ),
            ExampleData(
                text=(
                    "Die FHNW nimmt am Workshop in Olten teil und hat einen KI-Anwendungsfall im Kundenservice identifiziert. "
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
                        extraction_text="Workshop",
                        attributes={"id": "workshop", "workshop_typ": "KI-4-KMU"}
                    ),
                    lx.data.Extraction(
                        extraction_class="city",
                        extraction_text="Olten",
                        attributes={"id": "olten"}
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
                        extraction_text="Die FHNW nimmt am Workshop in Olten teil",
                        attributes={"typ": "teilnimmt_an", "subjekt_id": "fhnw", "objekt_id": "workshop"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Workshop in Olten",
                        attributes={"typ": "findet_statt_in", "subjekt_id": "workshop", "objekt_id": "olten"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Die FHNW nimmt am Workshop in Olten teil und hat einen KI-Anwendungsfall im Kundenservice identifiziert.",
                        attributes={"typ": "hat_use_case", "subjekt_id": "fhnw", "objekt_id": "ki_kundenservice"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Die wissensintensive Aufgabe der Anfragenklassifikation soll durch einen LLM-basierten Chatbot optimiert werden.",
                        attributes={"typ": "optimiert", "subjekt_id": "ki_kundenservice", "objekt_id": "anfragenklassifikation"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Die wissensintensive Aufgabe der Anfragenklassifikation soll durch einen LLM-basierten Chatbot optimiert werden.",
                        attributes={"typ": "nutzt", "subjekt_id": "ki_kundenservice", "objekt_id": "llm_chatbot"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Der EU AI Act reguliert den Einsatz solcher Systeme.",
                        attributes={"typ": "reguliert", "subjekt_id": "eu_ai_act", "objekt_id": "llm_chatbot"}
                    ),
                    lx.data.Extraction(
                        extraction_class="beziehung",
                        extraction_text="Ziel Z1 ist die Reduktion der Antwortzeit um 30%.",
                        attributes={"typ": "hat_ziel", "subjekt_id": "ki_kundenservice", "objekt_id": "ziel_z1"}
                    ),
                ]
            ),
        ]


# Backward compatibility function
def _default_examples():
    """Legacy function for backward compatibility.
    
    Returns:
        List of default examples for extraction.
    """
    return ExamplesManager.get_default_examples()