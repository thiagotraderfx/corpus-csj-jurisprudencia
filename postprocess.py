"""Normaliza citas del LLM: 【N】 → [N], comillas, espacios."""
import re

def normalize_answer(text):
    if not text:
        return text
    # CJK brackets → ASCII
    text = text.replace("【", "[").replace("】", "]")
    # Comillas typográficas → ASCII
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    # Colapsar espacios múltiples
    text = re.sub(r"[ \t]+", " ", text)
    # Colapsar líneas vacías múltiples
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
