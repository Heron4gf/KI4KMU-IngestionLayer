from typing import List, Tuple

import simplemma

# Supported languages for multilingual lemmatization
SUPPORTED_LANGS: Tuple[str, ...] = ("de", "it", "fr", "en")

# Pre-computed stopwords set for all supported languages
_STOPWORDS: set[str] | None = None


def _get_stopwords() -> set[str]:
    """Lazy-load stopwords from NLTK for all supported languages."""
    global _STOPWORDS
    if _STOPWORDS is None:
        try:
            import nltk
            nltk.download("stopwords", quiet=True)
            from nltk.corpus import stopwords

            _STOPWORDS = set()
            lang_map = {
                "de": "german",
                "it": "italian",
                "fr": "french",
                "en": "english",
            }
            for lang_code, lang_name in lang_map.items():
                try:
                    _STOPWORDS.update(stopwords.words(lang_name))
                except Exception:
                    pass  # Skip if language not available
        except Exception:
            # Fallback: return empty set if NLTK is not available
            _STOPWORDS = set()
    return _STOPWORDS


def normalize_text(text: str, lang: Tuple[str, ...] = SUPPORTED_LANGS) -> str:
    """
    Normalize text using simplemma lemmatization with multi-language support.
    
    This extracts keyphrases by lemmatizing words and lowercasing them,
    which is useful for tag matching without heavy NLP overhead.
    
    Args:
        text: The input text to normalize
        lang: Tuple of language codes for lemmatization (tries all, returns best match)
    
    Returns:
        Normalized text with lemmatized, lowercased words joined by spaces
    """
    # Tokenize: split on whitespace and punctuation, keep word-like tokens
    tokens = text.split()
    
    lemmatized = []
    for token in tokens:
        # Lemmatize using simplemma with multi-language inference
        lemma = simplemma.lemmatize(token, lang=lang)
        # Lowercase for consistent matching
        lemmatized.append(lemma.lower())
    
    return " ".join(lemmatized)


def extract_keyphrases(text: str, lang: Tuple[str, ...] = SUPPORTED_LANGS) -> List[str]:
    """
    Extract normalized keyphrases from text, filtering out stopwords.
    
    Returns a list of lemmatized, lowercased words that can be used
    for tag matching and ontology insertion.
    
    Args:
        text: The input text to extract keyphrases from
        lang: Tuple of language codes for lemmatization
    
    Returns:
        List of normalized keyphrase strings (stopwords and short tokens removed)
    """
    normalized = normalize_text(text, lang)
    tokens = normalized.split()
    
    stopwords = _get_stopwords()
    
    # Filter out stopwords and tokens that are too short
    return [
        t for t in tokens
        if t not in stopwords and len(t) > 2
    ]