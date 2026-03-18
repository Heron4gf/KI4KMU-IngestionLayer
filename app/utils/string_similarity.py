import re
from thefuzz import fuzz


_UMLAUT_MAP = {
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
}

_SIMILARITY_THRESHOLD = 90 # will merge entities that are more similar than this threeshold


def normalize_string(text: str) -> str:
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss'}
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def are_strings_similar(str1: str, str2: str, threshold: int = _SIMILARITY_THRESHOLD) -> bool:
    norm1 = normalize_string(str1)
    norm2 = normalize_string(str2)
    
    if norm1 == norm2:
        return True
        
    return fuzz.token_set_ratio(norm1, norm2) >= threshold

