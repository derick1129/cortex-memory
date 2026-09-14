from cortex.engine.rrf import fuse_reciprocal_ranks


def test_rrf_scoring_order():
    vector_results = ["doc_A", "doc_B", "doc_C"]
    graph_results = ["doc_B", "doc_A", "doc_D"]

    fused = fuse_reciprocal_ranks(
        rankings={"vector": vector_results, "graph": graph_results},
        weights={"vector": 1.0, "graph": 1.2},
        k=60,
    )

    # doc_B is rank 2 in vector, rank 1 in graph -> should score highest
    top_doc = fused[0][0]
    assert top_doc == "doc_B"


def test_rrf_empty_rankings():
    fused = fuse_reciprocal_ranks(rankings={}, weights={})
    assert fused == []


def test_rrf_default_weights_and_k():
    rankings = {
        "vector": ["doc_1", "doc_2"],
        "sparse": ["doc_2", "doc_3"],
    }
    # weights omitted, should default to 1.0, k defaults to 60
    fused = fuse_reciprocal_ranks(rankings=rankings, weights={})
    scores = dict(fused)

    # doc_2 appears at rank 2 (vector) and rank 1 (sparse)
    # rank 2: 1/(60+2) = 1/62; rank 1: 1/(60+1) = 1/61
    expected_doc_2 = (1.0 / 62) + (1.0 / 61)
    assert abs(scores["doc_2"] - expected_doc_2) < 1e-6
    assert fused[0][0] == "doc_2"


def test_rrf_disjoint_lists():
    rankings = {
        "vector": ["doc_A"],
        "graph": ["doc_B"],
    }
    weights = {"vector": 1.0, "graph": 2.0}
    fused = fuse_reciprocal_ranks(rankings=rankings, weights=weights, k=60)
    assert fused[0][0] == "doc_B"
    assert fused[1][0] == "doc_A"
