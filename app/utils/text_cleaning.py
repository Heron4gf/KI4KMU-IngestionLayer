import re

# Hyphenated line-break inside a word: "Umbrü-\nche" → "Umbrüche"
_HYPHEN_BREAK = re.compile(r'(\w)-\n(\w)')
# Soft single newline within a paragraph → space
_SOFT_NEWLINE = re.compile(r'(?<!\n)\n(?!\n)')
# Standalone page numbers (line that is just digits)
_PAGE_NUMBER_LINE = re.compile(r'^\s*\d{1,4}\s*$', re.MULTILINE)
# Repeated footer pattern
_FOOTER = re.compile(
    r'FHNW Hochschule für Wirtschaft \| ki-zentrum\.ch',
    re.IGNORECASE,
)
# Lines that are pure garbage: short lines with no real word characters (≥3 letters)
_GARBAGE_LINE = re.compile(r'^[^\w\säöüÄÖÜß]{0,2}\S{0,6}$')


def _filter_lines(text: str) -> str:
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append('')
            continue
        if _PAGE_NUMBER_LINE.match(stripped):
            continue
        if _FOOTER.search(stripped):
            continue
        word_chars = re.findall(r'[a-zA-ZäöüÄÖÜß]', stripped)
        if len(word_chars) < 3 and len(stripped) < 15:
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def fix_extraction_artifacts(text: str) -> str:
    text = _HYPHEN_BREAK.sub(r'\1\2', text)
    text = _filter_lines(text)
    text = _SOFT_NEWLINE.sub(' ', text)
    # Collapse 3+ consecutive newlines to double newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def is_garbage_chunk(text: str) -> bool:
    """Return True for chunks that are pure noise and should be dropped entirely."""
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) < 20:
        word_chars = re.findall(r'[a-zA-ZäöüÄÖÜß]', stripped)
        if len(word_chars) < 5:
            return True
    return False