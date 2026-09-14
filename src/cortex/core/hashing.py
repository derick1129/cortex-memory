import hashlib


def compute_content_hash(content: str) -> str:
    """Computes a canonical SHA-256 hash of normalized text."""
    normalized = content.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()
