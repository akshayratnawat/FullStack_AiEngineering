from app.retrieval.fusion import reciprocal_rank_fusion


def test_item_in_both_lists_beats_items_in_one():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]], k=60)
    assert fused[0][0] == "c"  # rank 3 + rank 1 beats a lone rank 1


def test_score_is_sum_of_reciprocal_ranks():
    ((item, score),) = reciprocal_rank_fusion([["x"], ["x"]], k=60)
    assert item == "x"
    assert score == 2 / 61


def test_ties_keep_first_seen_order():
    fused = reciprocal_rank_fusion([["a"], ["b"]], k=60)
    assert [item for item, _ in fused] == ["a", "b"]


def test_empty_input():
    assert reciprocal_rank_fusion([], k=60) == []
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_smaller_k_rewards_the_top_rank_more():
    (_, small), = reciprocal_rank_fusion([["x"]], k=1)
    (_, large), = reciprocal_rank_fusion([["x"]], k=60)
    assert small == 1 / 2 and large == 1 / 61
