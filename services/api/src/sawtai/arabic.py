import re
import unicodedata

ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
WHITESPACE = re.compile(r"\s+")
URL = re.compile(r"https?://\S+", re.IGNORECASE)


def normalize_for_search(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("ـ", "")
    normalized = normalized.translate(ARABIC_INDIC_DIGITS)
    normalized = DIACRITICS.sub("", normalized)
    normalized = URL.sub(" ⟨URL⟩ ", normalized)
    normalized = normalized.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    normalized = normalized.replace("ى", "ي").replace("ة", "ه")
    return WHITESPACE.sub(" ", normalized).strip()
