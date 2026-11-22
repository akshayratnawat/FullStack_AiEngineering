"""Tests for retrieval/fusion.py: Reciprocal Rank Fusion is pure maths, so no setup is needed."""

from app.retrieval.fusion import reciprocal_rank_fusion


def test_item_in_both_lists_beats_items_in_one():
    """A chunk both searches found outranks chunks only one search found."""
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]], k=60)
    assert fused[0][0] == "c"  # rank 3 + rank 1 beats a lone rank 1


def test_score_is_sum_of_reciprocal_ranks():
    """Score = 1/(k+rank) per list, summed: rank 1 in two lists with k=60 gives 2/61."""
    ((item, score),) = reciprocal_rank_fusion([["x"], ["x"]], k=60)
    assert item == "x"
    assert score == 2 / 61


def test_ties_keep_first_seen_order():
    """Equal scores keep the order the items were first seen in."""
    fused = reciprocal_rank_fusion([["a"], ["b"]], k=60)
    assert [item for item, _ in fused] == ["a", "b"]


def test_empty_input():
    """No lists, or only empty lists, give an empty result (no crash)."""
    assert reciprocal_rank_fusion([], k=60) == []
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_smaller_k_rewards_the_top_rank_more():
    """A smaller k makes rank 1 worth more: 1/2 at k=1 versus 1/61 at k=60."""
    (_, small), = reciprocal_rank_fusion([["x"]], k=1)
    (_, large), = reciprocal_rank_fusion([["x"]], k=60)
    assert small == 1 / 2 and large == 1 / 61
