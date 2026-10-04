"""Adversarial endpoint semantics on the frozen Scale-4/5 substrate."""

from copy import deepcopy
from dataclasses import replace

import pytest

from netsynth.scale6 import (
    ChannelEnvelope,
    ChannelPacket,
    EndpointChannels,
    Feedback,
    Fragment,
    ReceiveToken,
    establish_channel,
)
from netsynth.scale6_probe import TinyChannelFixture, require_packet, run_probe


def test_all_fourteen_criteria_reproducibly() -> None:
    probe = run_probe()
    criteria = probe["criteria"]
    assert isinstance(criteria, dict)
    assert len(criteria) == 14
    assert all(value is True for value in criteria.values())
    assert probe == run_probe()


def test_full_duplex_and_multiple_channels_are_independent() -> None:
    f = TinyChannelFixture()
    a2, b2 = establish_channel(f.left, f.right, maximum_message_size=16)
    a2.replace_path(f.initial, f.a.active_path.program, 68, 0)
    b2.replace_path(f.local_binding, f.b.active_path.program, 68, 0)
    assert f.a.queue_message(b"one") == a2.queue_message(b"two") == f.b.queue_message(b"back") == 0
    p1, p2, reverse = require_packet(f.a, 0), require_packet(a2, 0), require_packet(f.b, 0)
    assert p1.packet_number == p2.packet_number == reverse.packet_number == 0
    assert f.right.receive(ChannelEnvelope(p2), 1) == "accepted"
    assert f.right.receive(ChannelEnvelope(p1), 1) == "accepted"
    assert f.left.receive(ChannelEnvelope(reverse), 1) == "accepted"
    assert f.b.completed == {0: b"one"} and b2.completed == {0: b"two"}
    assert f.a.completed == {0: b"back"} and not a2.completed
    assert not b2.received_packets.keys() - {0}
    assert f.a.messages[0].acknowledged == set()
    f.a.receive(f.b.make_feedback(), 2)
    assert f.a.messages[0].acknowledged == {0, 1, 2}
    assert a2.messages[0].acknowledged == set()


def test_closed_and_unknown_tokens_cannot_alias_new_channel_even_with_repeated_entropy() -> None:
    f = TinyChannelFixture()
    packet = require_packet(f.a, 0) if f.a.queue_message(b"old") == 0 else pytest.fail("first ID")
    token = f.b.local_receive_token
    f.right.close(token)
    _, new = establish_channel(f.left, f.right, maximum_message_size=16)
    assert new.local_receive_token != token
    before = deepcopy(vars(new))
    assert f.right.receive(ChannelEnvelope(packet), 1) == "unknown_token"
    unknown = ChannelPacket.create(f.local.eid, f.remote.eid, ReceiveToken(b"unknown"), 10, packet.frame)
    assert f.right.receive(ChannelEnvelope(unknown), 1) == "unknown_token"
    assert vars(new) == before
    with pytest.raises(ValueError, match="closed"):
        f.b.queue_message(b"closed")
    with pytest.raises(ValueError, match="entropy"):
        establish_channel(EndpointChannels(f.local.eid, lambda: b"short"), f.right)


@pytest.mark.parametrize(
    "field_name", ["payload", "message_id", "total_size", "offset", "packet_number", "token", "source", "destination"]
)
def test_corrupted_data_and_demux_fields_do_not_mutate_channel(field_name: str) -> None:
    f = TinyChannelFixture()
    f.a.queue_message(b"data")
    packet = require_packet(f.a, 0)
    fragment = packet.frame
    assert isinstance(fragment, Fragment)
    match field_name:
        case "payload":
            bad = replace(packet, frame=replace(fragment, payload=b"evil"))
        case "message_id":
            bad = replace(packet, frame=replace(fragment, message_id=10))
        case "total_size":
            bad = replace(packet, frame=replace(fragment, total_size=10))
        case "offset":
            bad = replace(packet, frame=replace(fragment, offset=1))
        case "packet_number":
            bad = replace(packet, packet_number=100)
        case "token":
            bad = replace(packet, receive_token=ReceiveToken(b"bad"))
        case "source":
            bad = replace(packet, source_eid=f.remote.eid)
        case _:
            bad = replace(packet, destination_eid=f.local.eid)
    before = deepcopy(vars(f.b))
    assert f.right.receive(ChannelEnvelope(bad), 1) == "corrupt"
    assert vars(f.b) == before


@pytest.mark.parametrize("field_name", ["ack", "credit", "mark"])
def test_corrupted_feedback_cannot_change_reliability_credit_or_path(field_name: str) -> None:
    f = TinyChannelFixture()
    f.a.queue_message(b"data")
    packet = require_packet(f.a, 0)
    assert f.transmit(packet, 1) == "accepted"
    feedback = f.b.make_feedback()
    frame = feedback.frame
    assert isinstance(frame, Feedback)
    match field_name:
        case "ack":
            altered = replace(frame, receipts=((99, False),))
        case "credit":
            altered = replace(frame, credit_limit=999)
        case _:
            altered = replace(frame, receipts=((0, True),))
    bad = replace(feedback, frame=altered)
    before = deepcopy(vars(f.a))
    assert f.left.receive(ChannelEnvelope(bad), 2) == "corrupt"
    assert vars(f.a) == before


def test_integrity_valid_but_invalid_frames_are_rejected_atomically() -> None:
    f = TinyChannelFixture()
    malformed = [Fragment(-1, 4, 0, b"data"), Fragment(0, 17, 0, b"x"), Fragment(0, 4, 4, b"x"), Fragment(0, 4, 0, b"")]
    before = deepcopy(vars(f.b))
    for fragment in malformed:
        packet = ChannelPacket.create(f.local.eid, f.remote.eid, f.b.local_receive_token, 0, fragment)
        assert f.b.receive(packet, 0) == "invalid"
        assert vars(f.b) == before
    f.a.queue_message(b"data")
    require_packet(f.a, 0)
    before_a = deepcopy(vars(f.a))
    for frame in (Feedback(((0, False), (99, True)), 999), Feedback(((0, False),), -1)):
        packet = ChannelPacket.create(f.remote.eid, f.local.eid, f.a.local_receive_token, 0, frame)
        assert f.a.receive(packet, 0) == "invalid"
        assert vars(f.a) == before_a


def test_receiver_bounds_credit_consumption_and_reordered_credit_updates() -> None:
    f = TinyChannelFixture()
    with pytest.raises(ValueError, match="finite limit"):
        f.a.queue_message(b"x" * 17)
    m = f.a.queue_message(b"x" * 16)
    with pytest.raises(ValueError, match="flow credit"):
        f.a.queue_message(b"more")
    old_feedback = f.b.make_feedback()
    for tick in range(4):
        assert f.transmit(require_packet(f.a, tick * 3), tick * 3 + 1) == "accepted"
        assert f.transmit(f.b.make_feedback(), tick * 3 + 2) == "accepted"
    assert f.b.buffered_bytes == 16
    assert f.b.local_credit_limit == f.a.peer_credit_limit == 16
    with pytest.raises(ValueError, match="flow credit"):
        f.a.queue_message(b"more")
    assert f.b.consume_message(m) == b"x" * 16
    assert f.b.buffered_bytes == 0
    with pytest.raises(ValueError, match="already consumed"):
        f.b.consume_message(m)
    fresh = f.b.make_feedback()
    assert f.transmit(fresh, 15) == "accepted"
    assert f.a.peer_credit_limit == 32
    assert f.transmit(old_feedback, 16) == "accepted"
    assert f.a.peer_credit_limit == 32
    assert f.a.queue_message(b"more") == 1
    # Whole-message reservation rejects a second unseen message even if its first byte fits.
    malicious = ChannelPacket.create(f.local.eid, f.remote.eid, f.b.local_receive_token, 100, Fragment(99, 16, 0, b"x"))
    assert f.b.receive(malicious, 17) == "accepted"
    overflowing = ChannelPacket.create(
        f.local.eid, f.remote.eid, f.b.local_receive_token, 101, Fragment(100, 1, 0, b"x")
    )
    before = deepcopy(vars(f.b))
    assert f.b.receive(overflowing, 18) == "invalid"
    assert vars(f.b) == before


def test_empty_messages_are_bounded_consumable_and_never_redeliver() -> None:
    f = TinyChannelFixture()
    for tick in range(16):
        message_id = f.a.queue_message(b"")
        packet = require_packet(f.a, tick * 3)
        assert f.transmit(packet, tick * 3 + 1) == "accepted"
        assert f.transmit(f.b.make_feedback(), tick * 3 + 2) == "accepted"
        assert f.b.completed[message_id] == b""
    assert f.b.buffered_bytes == 16
    with pytest.raises(ValueError, match="flow credit"):
        f.a.queue_message(b"")
    assert f.b.consume_message(0) == b""
    with pytest.raises(ValueError, match="already consumed"):
        f.b.consume_message(0)
    assert f.transmit(packet, 49) == "duplicate"
    assert f.b.delivery_order == list(range(16))


def test_overlapping_repacketized_ranges_and_either_transmission_ack_satisfy_obligation() -> None:
    f = TinyChannelFixture()
    m = f.a.queue_message(b"abcdefgh")
    original = require_packet(f.a, 0)
    assert f.transmit(original, 0, defer_transport=True) == "delivered"
    f.a.mark_lost(original.packet_number)
    f.move(1)
    retransmit = require_packet(f.a, 2)
    assert retransmit.packet_number != original.packet_number
    assert isinstance(retransmit.frame, Fragment) and retransmit.frame.payload == b"ab"
    assert f.transmit(retransmit, 3) == "accepted"
    assert f.right.receive(ChannelEnvelope(original), 4) == "accepted"
    assert f.transmit(f.b.make_feedback(), 5) == "accepted"
    assert f.a.messages[m].acknowledged == {0, 1, 2, 3}
    remaining = require_packet(f.a, 6)
    assert isinstance(remaining.frame, Fragment) and remaining.frame.offset == 4
    assert f.transmit(remaining, 7) == "accepted"
    assert f.transmit(f.b.make_feedback(), 8) == "accepted"
    last = require_packet(f.a, 9)
    assert f.transmit(last, 10) == "accepted"
    assert f.transmit(f.b.make_feedback(), 11) == "accepted"
    assert f.a.send_next(12) is None
    assert f.b.completed == {m: b"abcdefgh"}


def test_loss_congestion_window_pacing_and_independent_new_path() -> None:
    f = TinyChannelFixture()
    f.a.queue_message(b"abcdefghijkl")
    first = require_packet(f.a, 0)
    assert f.a.send_next(0) is None  # burst/pacing control
    second = require_packet(f.a, 1)
    assert f.a.send_next(2) is None  # congestion, not receiver credit
    old = f.a.active_path
    f.a.mark_lost(first.packet_number)
    assert old.losses == 1 and old.congestion_window == 68
    assert old.bytes_in_flight == second.size
    f.a.mark_lost(first.packet_number)
    assert old.losses == 1
    assert f.a.send_next(3) is None
    assert f.transmit(second, 3, marked=True, defer_transport=True) == "delivered"
    f.move(4)
    new = f.a.active_path
    assert new.rtt is new.rtt_variance is None and new.pmtu == 66 and new.congestion_window == 132
    assert not new.confirmed and new.bytes_in_flight == 0 and new.congestion_marks == new.losses == 0
    snapshot = deepcopy(new)
    assert f.right.receive(ChannelEnvelope(second).mark_congestion(), 5) == "accepted"
    assert f.transmit(f.b.make_feedback(), 6) == "accepted"
    assert new == snapshot
    assert old.congestion_marks == 1 and old.confirmed and old.rtt == 5
    packet = require_packet(f.a, 7)
    assert f.a.sent_packets[packet.packet_number].path_epoch == new.epoch
    assert f.transmit(packet, 8) == "accepted"
    assert f.transmit(f.b.make_feedback(), 9) == "accepted"
    assert (f.a.active_path.confirmed, f.a.active_path.rtt, f.a.active_path.rtt_variance) == (True, 2, 1)


def test_monotonic_marks_duplicate_feedback_and_retired_path_never_reappear() -> None:
    f = TinyChannelFixture()
    f.a.queue_message(b"data")
    packet = require_packet(f.a, 0)
    envelope = ChannelEnvelope(packet)
    assert envelope.mark_congestion().mark_congestion() == envelope.mark_congestion()
    assert f.right.receive(envelope, 1) == "accepted"
    unmarked = f.b.make_feedback()
    assert f.transmit(unmarked, 2) == "accepted"
    assert f.right.receive(envelope.mark_congestion(), 3) == "duplicate"
    marked = f.b.make_feedback()
    old = f.a.active_path
    assert f.transmit(marked, 4) == "accepted"
    assert old.congestion_marks == 1
    window = old.congestion_window
    assert f.transmit(f.b.make_feedback(), 5) == "accepted"
    assert old.congestion_window == window and old.congestion_marks == 1
    f.move(6)
    new = deepcopy(f.a.active_path)
    with pytest.raises(ValueError, match="retention"):
        f.a.retire_path(old.epoch, 7)
    f.a.retire_path(old.epoch, 16)
    assert f.transmit(marked, 17) == "duplicate"
    assert f.a.active_path == new and old.epoch not in f.a.paths


def test_conflicting_fragments_or_packet_reuse_reject_before_mutation() -> None:
    f = TinyChannelFixture()
    f.a.queue_message(b"abcdefgh")
    packet = require_packet(f.a, 0)
    assert f.transmit(packet, 1) == "accepted"
    before = deepcopy(vars(f.b))
    for number, frame in (
        (0, Fragment(0, 8, 0, b"evil")),
        (1, Fragment(0, 8, 2, b"evil")),
        (1, Fragment(0, 9, 4, b"x")),
    ):
        bad = ChannelPacket.create(f.local.eid, f.remote.eid, f.b.local_receive_token, number, frame)
        assert f.b.receive(bad, 2) == "invalid"
        assert vars(f.b) == before


def test_ack_after_old_path_reclamation_satisfies_data_without_resurrecting_path() -> None:
    f = TinyChannelFixture()
    message = f.a.queue_message(b"data")
    packet = require_packet(f.a, 0)
    assert f.transmit(packet, 1, defer_transport=True) == "delivered"
    old_epoch = f.a.active_path.epoch
    f.move(2)
    with pytest.raises(ValueError, match="outstanding"):
        f.a.retire_path(old_epoch, 12)
    f.a.mark_lost(packet.packet_number)
    f.a.retire_path(old_epoch, 12)
    current = deepcopy(f.a.active_path)
    assert f.right.receive(ChannelEnvelope(packet).mark_congestion(), 13) == "accepted"
    assert f.transmit(f.b.make_feedback(), 14) == "accepted"
    assert old_epoch not in f.a.paths and f.a.active_path == current
    assert f.a.messages[message].acknowledged == {0, 1, 2, 3}
    assert f.a.send_next(15) is None


def test_path_binding_and_route_identity_are_checked_without_changing_channel() -> None:
    f = TinyChannelFixture()
    old = f.a.active_path
    with pytest.raises(ValueError, match="remote EID"):
        f.a.replace_path(f.local_binding, old.program, 68, 0)
    f.move(1)
    before = deepcopy(vars(f.a))
    with pytest.raises(ValueError, match="regress"):
        f.a.replace_path(f.initial, old.program, 68, 2)
    assert vars(f.a) == before
    with pytest.raises(ValueError, match="payload"):
        f.a.replace_path(f.a.active_path.binding, f.a.active_path.program, 64, 2)
