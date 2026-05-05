from thefuzz import fuzz

from app.utils.text_normalization import normalize_text

_SIMILARITY_THRESHOLD = 90  # will merge entities that are more similar than this threshold


def are_strings_similar(str1: str, str2: str, threshold: int = _SIMILARITY_THRESHOLD) -> bool:
    """Check if two strings are similar using lemmatized normalized forms."""
    norm1 = normalize_text(str1)
    norm2 = normalize_text(str2)
    
    if norm1 == norm2:
        return True
        
    return fuzz.token_set_ratio(norm1, norm2) >= threshold