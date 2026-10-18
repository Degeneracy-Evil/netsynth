"""Accounting identities and adverse cases, not performance tests."""

import json

import pytest

from netsynth.forwarding_program_probe import encoding, fixture
from netsynth.resource_economics import (
    Policy,
    Profile,
    Workload,
    dominates,
    evaluate,
    metric,
    quic_header,
    run_study,
    strict_break_even,
)


def test_exact_static_break_even_comes_from_actual_control_and_compiled_lengths() -> None:
    explicit_one = evaluate(Workload("one", (1,)), "explicit")
    token_one = evaluate(Workload("one", (1,)), "token")
    control_increment = metric(token_one, "control_byte_hops") - metric(explicit_one, "control_byte_hops")
    model = fixture()
    cold, warm = encoding(model, "hybrid"), encoding(model, "state-heavy")
    saving = cold.code_bytes + cold.context_bytes - warm.code_bytes - warm.context_bytes
    threshold = strict_break_even(control_increment, saving, 10)
    assert threshold is not None and threshold > 1
    for count in (1, threshold - 1, threshold, 1024):
        explicit = evaluate(Workload("static", (count,)), "explicit")
        token = evaluate(Workload("static", (count,)), "token")
        net = metric(explicit, "total_network_byte_hops") - metric(token, "total_network_byte_hops")
        assert net == (count - 1) * 10 * saving - control_increment
        assert (net > 0) == (count >= threshold)


def test_strict_inequality_and_absent_header_saving() -> None:
    assert strict_break_even(4096, 16, 4, 0) == 65
    assert strict_break_even(340, 34, 10) == 3  # 2 packets only tie after first cold packet.
    assert strict_break_even(0, 34, 10) == 2
    assert strict_break_even(100, 0, 10) is None
    assert strict_break_even(100, -1, 10) is None


def test_short_flow_is_a_real_control_state_counterexample() -> None:
    explicit = evaluate(Workload("short", (1,)), "explicit")
    token = evaluate(Workload("short", (1,)), "token")
    assert metric(token, "warm_packets") == 0
    assert token["observed_headers"] == explicit["observed_headers"]
    for key in (
        "total_network_byte_hops",
        "control_byte_hops",
        "peak_binding_entries",
        "peak_binding_compiler_bytes",
        "table_write_delete_work",
    ):
        assert metric(token, key) > metric(explicit, key)


@pytest.mark.parametrize("policy", ["explicit", "token"])
def test_channel_count_does_not_create_transit_entries(policy: Policy) -> None:
    # Same packet count/program: sharing across Channels is not replicated state.
    one = evaluate(Workload("one", (128,), channels=1), policy)
    many = evaluate(Workload("many", (128,), channels=32), policy)
    assert one == many


def test_control_hop_assumption_is_visible_and_changes_threshold_not_data() -> None:
    cheap, expensive = Profile(control_hops=1), Profile(control_hops=4)
    workload = Workload("static", (32,))
    for policy in ("explicit", "token"):
        left = evaluate(workload, policy, cheap)
        right = evaluate(workload, policy, expensive)
        assert metric(right, "control_byte_hops") == 4 * metric(left, "control_byte_hops")
        assert right["data_byte_hops"] == left["data_byte_hops"]
        assert right["peak_binding_compiler_bytes"] == left["peak_binding_compiler_bytes"]


def test_cache_expiry_requeries_but_does_not_reinstall_live_bindings() -> None:
    for policy in ("explicit", "token"):
        retained = evaluate(Workload("retained", (8,) * 4), policy)
        expired = evaluate(Workload("expired", (8,) * 4, event="expire"), policy)
        assert expired["peak_binding_entries"] == retained["peak_binding_entries"]
        assert expired["table_write_delete_work"] == retained["table_write_delete_work"]
        assert metric(expired, "cache_misses") > metric(retained, "cache_misses")
        assert metric(expired, "control_byte_hops") > metric(retained, "control_byte_hops")


def test_stale_cache_fails_closed_and_retry_delivers_same_useful_data() -> None:
    workload = Workload("stale", (4,) * 4, event="stale")
    explicit, token = evaluate(workload, "explicit"), evaluate(workload, "token")
    assert token["failed_attempts"] == 3
    assert explicit["failed_attempts"] == 0
    assert token["packets"] == explicit["packets"] == 16
    assert token["useful_application_bytes"] == explicit["useful_application_bytes"]
    assert token["physical_paths"] == explicit["physical_paths"]
    assert metric(token, "generation_lookups") > metric(explicit, "generation_lookups")


def test_hidden_repair_is_not_free_and_path_length_is_charged() -> None:
    for policy in ("explicit", "token"):
        stable = evaluate(Workload("stable", (16,) * 4), policy)
        repaired = evaluate(Workload("repair", (16,) * 4, event="repair"), policy)
        assert metric(repaired, "control_records") > metric(stable, "control_records")
        assert metric(repaired, "data_byte_hops") > metric(stable, "data_byte_hops")
        assert metric(repaired, "table_write_delete_work") > metric(stable, "table_write_delete_work")
        assert repaired["cache_misses"] == stable["cache_misses"]


def test_unshared_hard_generations_do_not_get_free_per_channel_state() -> None:
    explicit = evaluate(Workload("unshared", (1,) * 8, event="replace"), "explicit")
    token = evaluate(Workload("unshared", (1,) * 8, event="replace"), "token")
    assert token["warm_packets"] == 0
    assert metric(token, "peak_binding_entries") > metric(explicit, "peak_binding_entries")
    assert metric(token, "total_network_byte_hops") > metric(explicit, "total_network_byte_hops")


def test_standard_header_references_are_not_full_transport_or_sr_packets() -> None:
    assert quic_header(8, 2) == 75
    assert quic_header(0, 2) == 67
    assert quic_header(8, 4) == 77
    with pytest.raises(ValueError):
        quic_header(21, 2)
    with pytest.raises(ValueError):
        quic_header(8, 0)


def test_no_weighted_winner_and_equal_action_baseline_ties() -> None:
    assert not dominates((1, 1), (1, 1))
    assert not dominates((1, 2), (2, 1))
    assert dominates((1, 1), (2, 1))
    study = run_study()
    workloads = study["workloads"]
    assert isinstance(workloads, dict)
    for row in workloads.values():
        assert row["netsynth_explicit"] == row["sr_bsid_explicit"]
        assert row["netsynth_shared_token"] == row["sr_bsid_shared_token"]
        assert not row["comparison"]["token_dominates_explicit"]


def test_reproducible_json_and_invalid_budgets() -> None:
    assert json.dumps(run_study(), sort_keys=True) == json.dumps(run_study(), sort_keys=True)
    with pytest.raises(ValueError):
        Profile(control_hops=0)
    with pytest.raises(ValueError):
        Workload("empty", ())
    with pytest.raises(ValueError):
        evaluate(Workload("too_small", (1,)), "token", Profile(usable_packet_size=80))
