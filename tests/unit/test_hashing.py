from cortex.core.hashing import compute_content_hash


def test_compute_content_hash_consistency():
    text1 = "Error: Cannot find module 'react'"
    text2 = "Error: Cannot find module 'react'"
    text3 = "Error: Cannot find module 'lodash'"

    hash1 = compute_content_hash(text1)
    hash2 = compute_content_hash(text2)
    hash3 = compute_content_hash(text3)

    assert len(hash1) == 64
    assert hash1 == hash2
    assert hash1 != hash3


def test_compute_content_hash_normalization():
    # Leading/trailing whitespace should be stripped for stable error deduplication
    text_raw = "  SyntaxError: Unexpected token   \n"
    text_clean = "SyntaxError: Unexpected token"
    assert compute_content_hash(text_raw) == compute_content_hash(text_clean)
