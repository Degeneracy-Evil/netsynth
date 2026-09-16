"""End-to-end matrix reproducibility and schema tests."""

from netsynth.experiment import ExperimentConfig, run_experiment


def test_phase2_matrix_is_deterministic_and_uses_one_control() -> None:
    config = ExperimentConfig(
        "mesh2d",
        {"rows": 3, "columns": 4},
        seed=17,
        leaf_size=3,
        pair_sample_count=20,
        failure_sample_count=2,
        s2_landmark_counts=(1, 2),
    )

    first = run_experiment(config)
    second = run_experiment(config)

    assert first == second
    assert first["schema"]["version"] == "2.0"
    assert set(first["strategies"]) == {"flat", "s0", "s1", "s2_k1", "s2_k2", "s3"}
    assert first["sampling"]["pairs_sampled"] is True
    assert first["decomposition_control"]["parameters"]["name"] == "balanced_connected"
    failure = first["failure_experiments"][0]["strategies"]["s3"]
    assert failure["recovery_churn"]["changed_objects"] == failure["churn"]["changed_objects"]
    assert failure["recovery_churn"]["changed_recipient_nodes"] >= failure["churn"]["changed_recipient_nodes"]
