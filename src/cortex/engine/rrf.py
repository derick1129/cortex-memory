from collections import defaultdict
from typing import Dict, List, Tuple


def fuse_reciprocal_ranks(
    rankings: Dict[str, List[str]],
    weights: Dict[str, float],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """Calculates Reciprocal Rank Fusion score across multiple modality rankings."""
    scores: Dict[str, float] = defaultdict(float)
    for modality, doc_list in rankings.items():
        w = weights.get(modality, 1.0)
        for rank, doc_id in enumerate(doc_list):
            scores[doc_id] += w / (k + (rank + 1))

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
