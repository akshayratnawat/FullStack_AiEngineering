"""Reciprocal Rank Fusion: merge several ranked lists into one."""

from collections.abc import Hashable, Sequence


def reciprocal_rank_fusion[T: Hashable](
    rankings: Sequence[Sequence[T]], k: int
) -> list[tuple[T, float]]:
    """Return (item, score) best first. An item scores 1 / (k + rank) in every list it appears in.

    `k` smooths the gap between neighbouring ranks; 60 is the value from the original RRF
    paper and the default of `settings.retrieval_rrf_k`.

    Only ranks matter, never the raw scores, so vector distances and text-search ranks
    (which live on different scales) combine without any normalising. Ties keep the order
    in which the item was first seen.
    """
    scores: dict[T, float] = {}  # item -> running total across all lists
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):  # rank 1 = best
            # An item missing from a list simply adds nothing for that list.
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    # sorted() is stable, so equal scores keep the order they were first added in.
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
