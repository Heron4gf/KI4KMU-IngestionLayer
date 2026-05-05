from typing import List

import simplemma


def normalize_text(text: str, lang: str = "de") -> str:
    """
    Normalize text using simplemma lemmatization for German/English.
    
    This extracts keyphrases by lemmatizing words and lowercasing them,
    which is useful for tag matching without heavy NLP overhead.
    
    Args:
        text: The input text to normalize
        lang: Language code for lemmatization ('de' for German, 'en' for English)
    
    Returns:
        Normalized text with lemmatized, lowercased words joined by spaces
    """
    # Tokenize: split on whitespace and punctuation, keep word-like tokens
    tokens = text.split()
    
    lemmatized = []
    for token in tokens:
        # Lemmatize using simplemma (zero model downloads, fast)
        lemma = simplemma.lemmatize(token, lang=lang)
        # Lowercase for consistent matching
        lemmatized.append(lemma.lower())
    
    return ' '.join(lemmatized)


def extract_keyphrases(text: str, lang: str = "de") -> List[str]:
    """
    Extract normalized keyphrases from text.
    
    Returns a list of lemmatized, lowercased words that can be used
    for tag matching and ontology insertion.
    
    Args:
        text: The input text to extract keyphrases from
        lang: Language code for lemmatization
    
    Returns:
        List of normalized keyphrase strings
    """
    normalized = normalize_text(text, lang)
    # Split back into individual keyphrases
    return normalized.split()