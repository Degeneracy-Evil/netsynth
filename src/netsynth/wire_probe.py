"""Tiny byte-accurate, node-local forwarding feasibility probe."""

from __future__ import annotations

from netsynth.forwarding import Locator
from netsynth.wire_forwarding import NetNode, Operations, build_net, net_metrics, run_net
from netsynth.wire_labels import LabelNode, build_labels, label_metrics, run_labels
from netsynth.wire_packet import EMPTY, Attachment, LabelPacket, NetPacket, seal

DESTINATION = Locator((2,), 9)
NET_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
LABEL_KEY = bytes.fromhex("101112131415161718191a1b1c1d1e1f")


def node_records(node: NetNode | LabelNode) -> dict[bytes, bytes]:
    """Measurement-only canonical records; no forwarding code calls this."""
    if isinstance(node, NetNode):
        records = {b"T" + key.encode(): row.encode(key) for key, row in node.table.items()}
    else:
        records = {b"T" + label.to_bytes(4): row.encode(label) for label, row in node.table.items()}
        records[b"A"] = node.next_label.to_bytes(4)
    for (scope, slot), gen in node.generations.items():
        key = scope.to_bytes(2) + slot.to_bytes(4)
        records[b"G" + key] = key + gen.to_bytes(4)
    return records


def record_delta(before: dict[bytes, bytes], after: dict[bytes, bytes]) -> dict[str, int]:
    deleted = before.keys() - after.keys()
    changed = [key for key, value in after.items() if before.get(key) != value]
    return {
        "deleted_records": len(deleted),
        "written_records": len(changed),
        "delete_key_bytes": sum(len(key) - 1 for key in deleted),
        "write_image_bytes": sum(len(after[key]) for key in changed),
    }


def run_probe() -> dict[str, object]:
    rows: dict[str, object] = {}
    for case, (mode, capacity) in enumerate((("warm", 0), ("explicit", 2), ("explicit", 0)), start=1):
        traffic_key = bytes([case]) * 16
        control = build_net(mode, capacity)
        control.nodes[9].attachment = Attachment(DESTINATION, traffic_key)
        packet = NetPacket(DESTINATION, control.code, [EMPTY] * control.program.context_words, (7, 1, 1, 0), b"")
        wire = seal(packet, b"x" * 128, traffic_key)
        before = run_net(control.nodes[0], wire)
        initial_nodes = net_metrics(control.nodes)
        initial_state = {n: node.state_image() for n, node in control.nodes.items()}
        before_records = {n: node_records(node) for n, node in control.nodes.items()}
        for node in control.nodes.values():
            node.operations = Operations()
        control.repair()
        changed_nodes = [n for n, node in control.nodes.items() if node.state_image() != initial_state[n]]
        delta = {str(n): record_delta(before_records[n], node_records(node)) for n, node in control.nodes.items()}
        repaired_packet = NetPacket(DESTINATION, control.code, list(packet.slots), (7, 2, 2, 0), b"")
        repaired_wire = seal(repaired_packet, b"x" * 128, traffic_key)
        repaired = run_net(control.nodes[0], repaired_wire)
        after_repair = net_metrics(control.nodes)
        for node in control.nodes.values():
            node.operations = Operations()
        control.withdraw(control.model.handles["leaf"])
        stale = run_net(control.nodes[0], repaired_wire)
        rows[f"netsynth_{mode}_context{capacity}"] = {
            "header_bytes": len(wire) - 128,
            "wire_hex": wire.hex(),
            "before": before,
            "initial_nodes": initial_nodes,
            "after_repair_nodes": after_repair,
            "stale_nodes": net_metrics(control.nodes),
            "repair_changed_physical_nodes": changed_nodes,
            "repair_record_delta": delta,
            "repair": repaired,
            "stale": stale,
            "outer_code_unchanged": packet.code == repaired_packet.code,
            "exceeds_previous_67_byte_estimate_by": len(wire) - 128 - 67,
        }
    label = build_labels()
    label.nodes[9].attachment = Attachment(DESTINATION, LABEL_KEY)
    label_packet = LabelPacket(DESTINATION, label.entry.label, (7, 1, 1, 0), b"")
    label_wire = seal(label_packet, b"x" * 128, LABEL_KEY)
    baseline = run_labels(label.nodes[0], label_wire)
    label_initial = label_metrics(label.nodes)
    old = {n: node.state_image() for n, node in label.nodes.items()}
    label_before_records = {n: node_records(node) for n, node in label.nodes.items()}
    for label_node in label.nodes.values():
        label_node.operations = Operations()
    label.repair()
    label_changed = [n for n, node in label.nodes.items() if node.state_image() != old[n]]
    label_delta = {str(n): record_delta(label_before_records[n], node_records(node)) for n, node in label.nodes.items()}
    label_repair_wire = seal(LabelPacket(DESTINATION, label.entry.label, (7, 2, 2, 0), b""), b"x" * 128, LABEL_KEY)
    label_repaired = run_labels(label.nodes[0], label_repair_wire)
    label_after_repair = label_metrics(label.nodes)
    for label_node in label.nodes.values():
        label_node.operations = Operations()
    label.policies["leaf"].withdraw(label.model.handles["leaf"])
    label_stale = run_labels(label.nodes[0], label_repair_wire)
    rows["independent_label_swap"] = {
        "header_bytes": len(label_wire) - 128,
        "wire_hex": label_wire.hex(),
        "before": baseline,
        "initial_nodes": label_initial,
        "after_repair_nodes": label_after_repair,
        "stale_nodes": label_metrics(label.nodes),
        "repair_changed_physical_nodes": label_changed,
        "repair_record_delta": label_delta,
        "repair": label_repaired,
        "stale": label_stale,
        "outer_label_unchanged": label.entry.label == label_packet.label,
    }
    return {
        "schema": "netsynth.local-wire-feasibility.v1",
        "base_revision": "e3f1356",
        "fixture": {
            "generator": "forwarding_program_probe.fixture",
            "seed": None,
            "nodes": 10,
            "coverage": "exhaustive declared tiny fixture, not general topology coverage",
        },
        "field_bytes": {
            "netsynth_prefix": 12,
            "netsynth_current_key": 10,
            "structured_locator": 7,
            "each_code_or_context_key": 10,
            "receive_token_pn_message_fragment": 16,
            "aead_tag": 16,
            "label_prefix_with_lengths": 6,
            "label_shim": 4,
        },
        "limitations": [
            "experimental encoding, not frozen wire format or optimal compression",
            "serialized canonical forwarding state images, not CPython heap or ASIC allocation",
            "control-plane compiler caches and endpoint state excluded from node forwarding image",
            "AES-GCM with deterministic fixture keys; no handshake/reliable Channel stack",
            "single-label baseline uses local guards and never-reused 20-bit labels; exhaustion rejects",
            "equivalence covers finite tested lifetime only, not indefinite label recycling",
            "local operations and header byte changes counted, not CPU cycles/throughput/latency",
            "lengths exclude common link-layer framing; no path-MTU protocol or structural layout transition",
        ],
        "encodings": rows,
    }
