from app.retrieval.fusion import reciprocal_rank_fusion


def test_item_in_both_lists_beats_items_in_one():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]])
    assert fused[0][0] == "c"  # rank 3 + rank 1 beats a lone rank 1


def test_score_is_sum_of_reciprocal_ranks():
    ((item, score),) = reciprocal_rank_fusion([["x"], ["x"]], k=60)
    assert item == "x"
    assert score == 2 / 61


def test_ties_keep_first_seen_order():
    fused = reciprocal_rank_fusion([["a"], ["b"]])
    assert [item for item, _ in fused] == ["a", "b"]


def test_empty_input():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
