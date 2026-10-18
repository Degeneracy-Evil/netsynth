"""Actual byte codecs and two independent, node-local forwarding engines."""

import json
import struct
from dataclasses import replace

import pytest

from netsynth.scale4 import ScopedTransitPathlet
from netsynth.wire_forwarding import NetControl, build_net, run_net
from netsynth.wire_labels import LabelControl, LabelRow, build_labels, run_labels
from netsynth.wire_packet import EMPTY, Attachment, LabelPacket, NetPacket, WireKey, seal
from netsynth.wire_probe import DESTINATION, LABEL_KEY, NET_KEY, run_probe


def net_case(mode: str = "warm", capacity: int = 2, payload: bytes = b"test") -> tuple[NetControl, NetPacket, bytes]:
    control = build_net(mode, capacity)
    control.nodes[9].attachment = Attachment(DESTINATION, NET_KEY)
    packet = NetPacket(DESTINATION, control.code, [EMPTY] * control.program.context_words, (7, 1, 1, 0), b"")
    return control, packet, seal(packet, payload, NET_KEY)


def label_case(payload: bytes = b"test") -> tuple[LabelControl, LabelPacket, bytes]:
    control = build_labels()
    control.nodes[9].attachment = Attachment(DESTINATION, LABEL_KEY)
    packet = LabelPacket(DESTINATION, control.entry.label, (7, 1, 1, 0), b"")
    return control, packet, seal(packet, payload, LABEL_KEY)


@pytest.mark.parametrize("mode,capacity,header", [("warm", 0, 71), ("explicit", 2, 111), ("explicit", 0, 91)])
def test_codec_round_trip_actual_lengths_and_same_physical_path(mode: str, capacity: int, header: int) -> None:
    control, packet, wire = net_case(mode, capacity, b"x" * 128)
    assert NetPacket.decode(wire).encode() == wire
    assert len(wire) - 128 == header
    assert packet.code == control.code
    result = run_net(control.nodes[0], wire)
    assert result["status"] == "delivered"
    assert result["path"] == (0, 1, 2, 3, 5, 1, 2, 3, 6, 7, 9)
    sizes = result["wire_sizes"]
    assert isinstance(sizes, tuple) and set(sizes) == {len(wire)}
    assert control.nodes[9].attachment is not None
    assert control.nodes[9].attachment.received == [b"x" * 128]


def test_independent_label_codec_and_interpreter() -> None:
    control, _, wire = label_case()
    assert LabelPacket.decode(wire).encode() == wire
    assert len(wire) - len(b"test") == 49
    result = run_labels(control.nodes[0], wire)
    assert result["status"] == "delivered"
    assert result["path"] == (0, 1, 2, 3, 5, 1, 2, 3, 6, 7, 9)
    sizes = result["wire_sizes"]
    assert isinstance(sizes, tuple) and set(sizes) == {len(wire)}
    assert all(not hasattr(node, "registry") and not hasattr(node, "owners") for node in control.nodes.values())


def test_no_control_plane_or_global_mapping_is_reachable_or_needed_by_data_plane() -> None:
    net, _, wire = net_case()
    source = net.nodes[0]
    net.model.registries.clear()
    net.model.owners.clear()
    net.services.clear()
    net.nodes.clear()  # Only physical neighbor links now retain the routers.
    assert run_net(source, wire)["status"] == "delivered"
    labels, _, wire = label_case()
    label_source = labels.nodes[0]
    labels.model.registries.clear()
    labels.model.owners.clear()
    labels.policies.clear()
    labels.nodes.clear()
    assert run_labels(label_source, wire)["status"] == "delivered"


def test_scope_and_node_context_disambiguate_equal_numeric_tokens() -> None:
    control, packet, _ = net_case()
    colliding = [key for key in control.nodes[1].table if key.token == 0 and key.generation == 0]
    assert len({key.scope for key in colliding}) >= 3
    assert len({control.nodes[1].table[key] for key in colliding}) >= 3
    forged = replace(packet, code=(WireKey(65534, packet.code[0].token, 0),))
    wire = seal(forged, b"test", NET_KEY)
    assert run_net(control.nodes[0], wire)["status"] == "unknown_token"
    # A valid entry at node 0 cannot cause a remote lookup when presented at node 2.
    control, _, wire = net_case()
    assert run_net(control.nodes[2], wire)["status"] == "unknown_token"


@pytest.mark.parametrize("mode,capacity", [("warm", 0), ("explicit", 2), ("explicit", 0)])
def test_hidden_repair_keeps_outer_bytes_fixed_and_changes_only_leaf_nodes(mode: str, capacity: int) -> None:
    control, original, _ = net_case(mode, capacity)
    old = {n: node.state_image() for n, node in control.nodes.items()}
    control.repair()
    changed = {n for n, node in control.nodes.items() if node.state_image() != old[n]}
    assert changed <= {1, 2, 3, 4, 8}
    packet = replace(original, transport=(7, 2, 2, 0))
    wire = seal(packet, b"test", NET_KEY)
    assert b"".join(k.encode() for k in packet.code) == b"".join(k.encode() for k in original.code)
    result = run_net(control.nodes[0], wire)
    assert result["status"] == "delivered"
    assert result["path"] == (0, 1, 4, 8, 3, 5, 1, 4, 8, 3, 6, 7, 9)
    sizes = result["wire_sizes"]
    assert isinstance(sizes, tuple) and set(sizes) == {len(wire)}


def test_label_hidden_repair_is_independent_and_preserves_public_label() -> None:
    control, packet, _ = label_case()
    entry = control.entry
    old = {n: node.state_image() for n, node in control.nodes.items()}
    control.repair()
    assert entry == control.entry
    assert {n for n, node in control.nodes.items() if node.state_image() != old[n]} <= {1, 2, 4, 8}
    wire = seal(replace(packet, transport=(7, 2, 2, 0)), b"test", LABEL_KEY)
    result = run_labels(control.nodes[0], wire)
    assert result["status"] == "delivered"
    assert result["path"] == (0, 1, 4, 8, 3, 5, 1, 4, 8, 3, 6, 7, 9)


def test_retired_generation_and_new_generation_do_not_alias() -> None:
    control, _, wire = net_case()
    old_handle = control.model.handles["leaf"]
    old = control.model.registries["leaf"].lookup(old_handle)
    assert old is not None
    control.withdraw(old_handle)
    assert run_net(control.nodes[0], wire)["status"] == "stale_generation"
    new = replace(old_handle, generation=1)
    control.model.registries["leaf"].publish(
        ScopedTransitPathlet(replace(old.advertisement, handle=new), old.realization)
    )
    control.services["leaf"].install(new, None, 0)
    control.install_rows()
    assert run_net(control.nodes[0], wire)["status"] in {"unknown_token", "stale_generation"}
    assert control.nodes[9].attachment is not None
    assert not control.nodes[9].attachment.received


def test_label_lifetime_has_no_alias_and_finite_exhaustion_rejects() -> None:
    control, _, wire = label_case()
    policy = control.policies["leaf"]
    old_handle = control.model.handles["leaf"]
    old = policy.registry.lookup(old_handle)
    assert old is not None
    labels_before = set(control.nodes[1].table)
    policy.withdraw(old_handle)
    new = replace(old_handle, generation=1)
    policy.registry.publish(ScopedTransitPathlet(replace(old.advertisement, handle=new), old.realization))
    entry = policy.install(new, None)
    assert entry.label not in labels_before
    assert run_labels(control.nodes[0], wire)["status"] == "stale_generation"
    node = control.nodes[1]
    node.next_label = 2**20
    with pytest.raises(ValueError, match="exhausted"):
        node.allocate(LabelRow(1, 0, 1, 0))


def test_inflight_retired_continuation_fails_closed_after_repair() -> None:
    control, _, data = net_case()
    status, data, port = control.nodes[0].step(data)
    assert status == "forward" and port == 2
    status, data, port = control.nodes[1].step(data)
    assert status == "forward" and port == 3
    control.repair()
    assert control.nodes[2].step(data)[0] == "unknown_token"
    labels, _, data = label_case()
    _, data, _ = labels.nodes[0].step(data)
    _, data, _ = labels.nodes[1].step(data)
    labels.repair()
    assert labels.nodes[2].step(data)[0] == "unknown_label"


def test_both_engines_reject_malformed_hop_exhaustion_and_local_link_failure() -> None:
    control, packet, wire = net_case()
    labels, label_packet, label_wire = label_case()
    for broken in (b"", wire[:-1], wire + b"x", bytes([99]) + wire[1:]):
        assert control.nodes[0].step(broken)[0] == "malformed"
    for broken in (b"", label_wire[:-1], label_wire + b"x", bytes([99]) + label_wire[1:]):
        assert labels.nodes[0].step(broken)[0] == "malformed"
    assert (
        run_net(control.nodes[0], seal(replace(packet, hops=0), b"test", NET_KEY))["status"] == "hop_budget_exhausted"
    )
    assert (
        run_labels(labels.nodes[0], seal(replace(label_packet, hops=0), b"test", LABEL_KEY))["status"]
        == "hop_budget_exhausted"
    )
    del control.nodes[0].links[2]
    del labels.nodes[0].links[2]
    assert run_net(control.nodes[0], wire)["status"] == "link_down"
    assert run_labels(labels.nodes[0], label_wire)["status"] == "link_down"


def test_context_overflow_cannot_expand_packet_and_ingress_limit_is_real() -> None:
    control, packet, _ = net_case("explicit", 2)
    packet.slots = []  # Malformed compiler output, but a valid serialized packet.
    wire = seal(packet, b"test", NET_KEY)
    result = run_net(control.nodes[0], wire)
    assert result["status"] == "context_exhausted"
    sizes = result["wire_sizes"]
    assert isinstance(sizes, tuple) and set(sizes) == {len(wire)}
    with pytest.raises(ValueError, match="ingress"):
        seal(packet, bytes(512), NET_KEY)
    for mode, capacity, size in (("warm", 0, 71), ("explicit", 2, 111), ("explicit", 0, 91)):
        candidate, _, wire = net_case(mode, capacity, bytes(512 - size))
        assert len(wire) == 512
        assert run_net(candidate.nodes[0], wire)["status"] == "delivered"
    label_control, _, wire = label_case(bytes(512 - 49))
    assert len(wire) == 512
    assert run_labels(label_control.nodes[0], wire)["status"] == "delivered"


def test_wire_widths_never_wrap() -> None:
    for key in (WireKey(2**16, 0, 0), WireKey(1, 2**32, 0), WireKey(1, 0, 0xFFFFFFFF)):
        with pytest.raises((ValueError, struct.error)):
            key.encode()


def test_corruption_rejected_before_endpoint_mutation_for_both_codecs() -> None:
    control, _, wire = net_case()
    corrupt = wire[:-1] + bytes([wire[-1] ^ 1])
    assert run_net(control.nodes[0], corrupt)["status"] == "invalid_integrity"
    assert control.nodes[9].attachment is not None and not control.nodes[9].attachment.received
    labels, _, wire = label_case()
    corrupt = wire[:-1] + bytes([wire[-1] ^ 1])
    assert run_labels(labels.nodes[0], corrupt)["status"] == "invalid_integrity"
    assert labels.nodes[9].attachment is not None and not labels.nodes[9].attachment.received


def test_identical_packets_do_not_install_per_packet_state() -> None:
    control, packet, _ = net_case()
    before = {n: node.state_image() for n, node in control.nodes.items()}
    for number in range(1, 4):
        wire = seal(replace(packet, transport=(7, number, number, 0)), b"test", NET_KEY)
        assert run_net(control.nodes[0], wire)["status"] == "delivered"
    assert {n: node.state_image() for n, node in control.nodes.items()} == before


def test_reproducible_byte_images_and_cost_report() -> None:
    assert json.dumps(run_probe(), sort_keys=True) == json.dumps(run_probe(), sort_keys=True)


def test_independent_baseline_does_not_use_netsynth_wire_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    control, _, wire = label_case()

    def forbidden(*_args: object) -> None:
        raise AssertionError("label baseline called NetSynth parser")

    monkeypatch.setattr(NetPacket, "decode", forbidden)
    assert run_labels(control.nodes[0], wire)["status"] == "delivered"


def test_serialized_state_parts_and_per_node_operations_are_exact() -> None:
    report = run_probe()
    rows = report["encodings"]
    assert isinstance(rows, dict)
    for row in rows.values():
        for node in row["initial_nodes"].values():
            assert node["state_image_bytes"] == sum(
                node[key]
                for key in ("table_image_bytes", "generation_image_bytes", "port_image_bytes", "allocator_image_bytes")
            )
            assert node["operations"]["table_lookups"] == node["operations"]["guard_lookups"]
        assert sum(node["operations"]["physical_hops"] for node in row["initial_nodes"].values()) == 10
        assert all(row["repair_record_delta"][str(node)]["written_records"] == 0 for node in (0, 5, 6, 7, 9))


def test_mutable_congestion_mark_preserves_endpoint_integrity_and_soft_metric_does_not_rekey() -> None:
    control, packet, wire = net_case()
    changed = NetPacket.decode(wire)
    changed.mark = 1
    images = {n: node.state_image() for n, node in control.nodes.items()}
    control.model.registries["leaf"].update_soft_metric(control.model.handles["leaf"], 100.0)
    assert {n: node.state_image() for n, node in control.nodes.items()} == images
    assert changed.code == packet.code
    assert run_net(control.nodes[0], changed.encode())["status"] == "delivered"
    labels, _, wire = label_case()
    changed_label = LabelPacket.decode(wire)
    changed_label.mark = 1
    labels.model.registries["leaf"].update_soft_metric(labels.model.handles["leaf"], 100.0)
    assert run_labels(labels.nodes[0], changed_label.encode())["status"] == "delivered"
