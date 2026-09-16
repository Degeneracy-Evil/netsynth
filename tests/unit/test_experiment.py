"""End-to-end reproducibility and schema tests."""

from netsynth.experiment import ExperimentConfig, run_experiment


def test_experiment_is_deterministic_and_records_reproduction_inputs() -> None:
    config = ExperimentConfig(
        "mesh2d",
        {"rows": 3, "columns": 4},
        seed=17,
        leaf_size=3,
        pair_sample_count=20,
        failure_sample_count=3,
    )

    first = run_experiment(config)
    second = run_experiment(config)

    assert first == second
    assert first["schema"]["version"] == "1.0"
    assert first["topology"]["seed"] == 17
    assert first["sampling"]["pairs_sampled"] is True
    assert first["metrics"]["routing_state"]["flat"]["total"] == 12 * 11
    failure = first["metrics"]["failure_experiments"][0]
    assert failure["recovery"]["flat_churn"] == failure["flat_churn"]
