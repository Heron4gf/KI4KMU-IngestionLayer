import re
from typing import List, Tuple

import simplemma

SUPPORTED_LANGS: Tuple[str, ...] = ("de", "it", "fr", "en")

_STOPWORDS: set[str] | None = None
_PUNCT_RE = re.compile(r"[^\w\s]")


def _get_stopwords() -> set[str]:
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
                    pass
        except Exception:
            _STOPWORDS = set()
    return _STOPWORDS


def normalize_text(text: str, lang: Tuple[str, ...] = SUPPORTED_LANGS) -> str:
    tokens = text.split()
    lemmatized = []
    for token in tokens:
        clean = _PUNCT_RE.sub("", token)
        if not clean:
            continue
        lemma = simplemma.lemmatize(clean, lang=lang)
        lemmatized.append(lemma.lower())
    return " ".join(lemmatized)


def extract_keyphrases(text: str, lang: Tuple[str, ...] = SUPPORTED_LANGS) -> List[str]:
    stopwords = _get_stopwords()
    result = []
    for token in text.split():
        clean = _PUNCT_RE.sub("", token).lower()
        if not clean or len(clean) <= 2 or clean in stopwords:
            continue
        lemma = simplemma.lemmatize(clean, lang=lang).lower()
        result.append(lemma)
    return result
