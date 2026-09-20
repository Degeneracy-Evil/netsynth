"""Phase-3 experiment matrix tests."""

from netsynth.phase3 import Phase3Config, run_phase3


def test_phase3_exhaustive_matrix_and_reproducibility() -> None:
    config = Phase3Config("mesh2d", {"rows": 3, "columns": 3}, seed=4, leaf_size=3, failure_sample_count=1)
    first = run_phase3(config)
    assert first == run_phase3(config)
    assert first["schema"]["version"] == "5.0"
    assert first["sampling"]["pairs_sampled"] is False
    assert first["sampling"]["pair_count"] == 72
    assert first["decomposition_control"]["strategy_id"] == "d0"
    assert first["decomposition_control"]["quality"]["aggregate_distortion"]["count"] > 0
    assert set(first["strategies"]) == {
        "flat",
        "r0",
        "s0",
        "s1",
        "s2_k1",
        "s2_k2",
        "s2_k4",
        "s3",
        "scoped_potential",
        "attachment_h1",
        "attachment_h2",
        "attachment_h3",
        "attachment_hfull",
        "attachment_comparison",
    }
    assert first["strategies"]["s3"]["recursive_oracle"]["weighted_cost_stretch"]["mean"] == 1.0
    assert sum(first["strategies"]["s3"]["distributed"]["statuses"].values()) == 72
    assert first["strategies"]["scoped_potential"]["distributed"]["statuses"] == {
        "delivered": 72,
        "no_route": 0,
        "invalid_next_hop": 0,
        "loop": 0,
        "hop_budget_exhausted": 0,
    }
    assert first["strategies"]["attachment_h1"]["distributed"]["statuses"] == {
        "delivered": 72,
        "no_route": 0,
        "invalid_next_hop": 0,
        "loop": 0,
        "hop_budget_exhausted": 0,
    }
    comparison = first["strategies"]["attachment_comparison"]
    assert comparison["full_below_flat_violations"] == 0
    assert all(value["ordering_violations_below_full"] == 0 for value in comparison["limited"].values())


def test_weight_and_label_inputs_are_recorded() -> None:
    config = Phase3Config(
        "tree",
        {"node_count": 8},
        seed=1,
        leaf_size=2,
        failure_sample_count=0,
        cost_profile="skewed",
        label_permutation_seed=9,
    )
    result = run_phase3(config)
    assert result["topology"]["cost_profile"] == "skewed"
    assert result["topology"]["label_permutation_seed"] == 9
