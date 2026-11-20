import re
import unicodedata


def normalize_text(value: object) -> str:
    """Normalize text for accent-insensitive factual matching."""
    text = str(value or "")
    text = text.replace("’", "'").replace("\u00a0", " ").replace("**", "")
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", text).strip()
