# similarity_utils.py
"""Client-side replacements for pg_trgm's similarity() and pgvector's <=> cosine
distance — Fabric has neither, so this math moves from SQL into Python. Fine at
our data sizes (a handful of categorical columns, a few dozen catalog rows)."""
import numpy as np
from rapidfuzz import fuzz

def fuzzy_ratio(a: str, b: str) -> float:
    """0-1 scale fuzzy similarity, comparable in spirit to pg_trgm's similarity()."""
    return fuzz.ratio(a, b) / 100.0

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a, b = np.array(vec_a), np.array(vec_b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)