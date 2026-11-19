"""Reciprocal Rank Fusion: merge several ranked lists into one."""

from collections.abc import Hashable, Sequence

RRF_K = 60  # the constant from the original RRF paper; damps the lead of rank 1 over rank 2


def reciprocal_rank_fusion[T: Hashable](
    rankings: Sequence[Sequence[T]], k: int = RRF_K
) -> list[tuple[T, float]]:
    """Return (item, score) best first. An item scores 1 / (k + rank) in every list it appears in.

    Only ranks matter, never the raw scores, so vector distances and text-search ranks
    (which live on different scales) combine without any normalising. Ties keep the order
    in which the item was first seen.
    """
    scores: dict[T, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
