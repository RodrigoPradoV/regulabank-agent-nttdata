"""`rrf_fuse`: `w / (60 + rango)` sobre listas de ids ya rankeadas."""

from __future__ import annotations

from regulabank.agents.fuse import rrf_fuse


def test_single_list_keeps_relative_order() -> None:
    scores = rrf_fuse([["a", "b", "c"]])
    assert scores["a"] > scores["b"] > scores["c"]


def test_item_in_both_lists_scores_higher_than_item_in_one() -> None:
    scores = rrf_fuse([["a", "b"], ["b", "c"]])
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]


def test_weights_change_contribution_per_channel() -> None:
    equal = rrf_fuse([["a"], ["b"]], weights=[1.0, 1.0])
    weighted = rrf_fuse([["a"], ["b"]], weights=[1.0, 0.3])
    assert equal["a"] == equal["b"]
    assert weighted["a"] > weighted["b"]


def test_empty_lists_produce_empty_scores() -> None:
    assert rrf_fuse([[], []]) == {}
