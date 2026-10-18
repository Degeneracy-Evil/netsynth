"""Deterministic resource ledger over frozen forwarding, NOT a new dataplane.

SR/BSID is the equal-action abstract translation, not stock MPLS emulation.
All byte widths except RFC references are the existing symbolic model/profile.
No CPU/latency estimates, scalar utility weights or performance conclusions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from netsynth.forwarding_program import (
    HANDLE_BYTES,
    WORD_BYTES,
    BindingRef,
    CompiledProgram,
    Execution,
    Instruction,
    PacketBudget,
    execute,
)
from netsynth.forwarding_program_probe import Fixture, encoding, fixture
from netsynth.scale4 import PhysicalHop

type Policy = Literal["explicit", "token"]
type Event = Literal["none", "repair", "replace", "expire", "stale"]

# A hypothetical established-Channel envelope, identical for BOTH architectures.
# Not the economics note's unvalidated 38-byte complete warm-packet target.
ENVELOPE_FIELDS = {
    "flags_and_hop_budget": 2,
    "receive_token": 4,
    "packet_number": 4,
    "message_id": 4,
    "fragment_metadata": 4,
    "aead_tag": 16,
}


@dataclass(frozen=True)
class Profile:
    """Explicit assumptions, not hardware measurements or a frozen wire format."""

    control_hops: int = 2
    payload_bytes: int = 128
    usable_packet_size: int = 512

    def __post_init__(self) -> None:
        if min(self.control_hops, self.payload_bytes, self.usable_packet_size) <= 0:
            raise ValueError("profile parameters must be positive")

    @property
    def envelope_bytes(self) -> int:
        return sum(ENVELOPE_FIELDS.values())


DEFAULT_PROFILE = Profile()


@dataclass(frozen=True)
class Workload:
    """One program, reused by Channels; events happen between converged batches."""

    name: str
    batches: tuple[int, ...]
    channels: int = 1
    event: Event = "none"

    def __post_init__(self) -> None:
        if not self.batches or min(self.batches) <= 0 or self.channels <= 0:
            raise ValueError("nonempty positive workload required")


WORKLOADS = (
    Workload("long_flow", (1024,)),
    Workload("short_flow", (1,)),
    Workload("shared_by_32_channels", (128,), channels=32),
    Workload("unshared_short_lifetimes", (1,) * 16, event="replace"),
    Workload("hidden_repairs", (16,) * 8, event="repair"),
    Workload("path_replacements", (4,) * 8, event="replace"),
    Workload("ingress_cache_expiry", (8,) * 8, event="expire"),
    Workload("stale_cached_program", (4,) * 8, event="stale"),
)


@dataclass
class Totals:
    """Dimensions stay separate; bytes of RAM are never subtracted from traffic."""

    packets: int = 0
    cold_packets: int = 0
    warm_packets: int = 0
    failed_attempts: int = 0
    header_byte_hops: int = 0
    data_byte_hops: int = 0
    control_byte_hops: int = 0
    control_messages: int = 0
    control_records: int = 0
    table_write_delete_work: int = 0
    binding_lookups: int = 0
    generation_lookups: int = 0
    context_mutations: int = 0
    peak_binding_entries: int = 0
    peak_binding_compiler_bytes: int = 0
    peak_ingress_cache_bytes: int = 0
    peak_stp_records: int = 0
    cache_misses: int = 0
    cache_hits: int = 0
    observed_headers: set[int] = field(default_factory=set)
    physical_paths: list[tuple[int, ...]] = field(default_factory=list)


def snapshot(model: Fixture) -> dict[str, dict[BindingRef, Instruction]]:
    """Measurement harness only: compilers do not receive this global view."""
    return {name: dict(owner.table) for name, owner in model.owners.items()}


def charge_tables(
    model: Fixture, before: dict[str, dict[BindingRef, Instruction]], totals: Totals, profile: Profile
) -> None:
    """One install delta + acknowledgement per changed owner, with explicit framing."""
    for name, owner in model.owners.items():
        deleted = before[name].keys() - owner.table.keys()
        changed = {ref: item for ref, item in owner.table.items() if before[name].get(ref) != item}
        records = len(deleted) + len(changed)
        if not records:
            continue
        # delete: opcode+token; write: opcode+token+full existing-model instruction.
        record_bytes = len(deleted) * (1 + WORD_BYTES) + sum(
            1 + WORD_BYTES + item.size_bytes for item in changed.values()
        )
        totals.control_records += records
        totals.control_messages += 2
        totals.control_byte_hops += profile.control_hops * (record_bytes + WORD_BYTES + 2 * profile.envelope_bytes)


def charge_query(program: CompiledProgram, totals: Totals, profile: Profile) -> None:
    """Request=handle+capacity; response=finite code+resource bound; two envelopes."""
    totals.cache_misses += 1
    totals.control_messages += 2
    totals.control_byte_hops += profile.control_hops * (
        HANDLE_BYTES + WORD_BYTES + program.code_bytes + WORD_BYTES + 2 * profile.envelope_bytes
    )


def observe_state(model: Fixture, cold: CompiledProgram, warm: CompiledProgram | None, totals: Totals) -> None:
    totals.peak_binding_entries = max(totals.peak_binding_entries, sum(len(o.table) for o in model.owners.values()))
    totals.peak_binding_compiler_bytes = max(
        totals.peak_binding_compiler_bytes, sum(o.state_bytes for o in model.owners.values())
    )
    totals.peak_stp_records = max(totals.peak_stp_records, sum(r.persistent_records for r in model.registries.values()))
    # Ingress cache stores code and advertised bound; writable packet copies are not persistent state.
    cache_bytes = cold.code_bytes + WORD_BYTES + (0 if warm is None else warm.code_bytes + WORD_BYTES)
    totals.peak_ingress_cache_bytes = max(totals.peak_ingress_cache_bytes, cache_bytes)


def packet(model: Fixture, program: CompiledProgram, profile: Profile) -> Execution:
    return execute(
        model.graph,
        model.owners,
        model.registries,
        program,
        0,
        9,
        PacketBudget(profile.usable_packet_size, profile.envelope_bytes),
        profile.payload_bytes,
    )


def charge_packets(result: Execution, count: int, totals: Totals, profile: Profile, *, failed: bool = False) -> None:
    if count == 0:
        return
    if failed:
        if result.status != "stale_pathlet":
            raise AssertionError("stale cached reference did not fail closed")
        totals.failed_attempts += count
    elif result.status != "delivered":
        raise AssertionError(f"forwarding failed: {result.status}")
    if len(set(result.wire_sizes)) != 1:
        raise AssertionError("packet size changed after ingress")
    hops = len(result.path) - 1
    wire = result.wire_sizes[0]
    totals.header_byte_hops += count * hops * (wire - profile.payload_bytes)
    totals.data_byte_hops += count * hops * wire
    totals.binding_lookups += count * result.lookups
    totals.generation_lookups += count * result.generation_checks
    totals.context_mutations += count * result.context_mutations
    totals.observed_headers.add(wire - profile.payload_bytes)


def change(model: Fixture, event: Event, index: int, totals: Totals, profile: Profile) -> None:
    """Converged repair or root-program withdrawal, not an asynchronous update protocol."""
    if event not in {"repair", "replace", "stale"}:
        return
    actions = (
        (PhysicalHop(1, 4), PhysicalHop(4, 8), PhysicalHop(8, 3))
        if index % 2
        else (PhysicalHop(1, 2), PhysicalHop(2, 3))
    )
    model.owners["leaf"].repair(model.handles["leaf"], actions)
    # Underlying owner-local STP replacement, separate from compiled-binding deltas.
    totals.control_records += 1 + len(actions)
    totals.control_messages += 2
    totals.control_byte_hops += profile.control_hops * (
        HANDLE_BYTES + len(actions) * WORD_BYTES + WORD_BYTES + 2 * profile.envelope_bytes
    )
    if event in {"replace", "stale"}:
        registry = model.registries["root"]
        old = model.handles["root"]
        current = registry.lookup(old)
        assert current is not None
        registry.retire(old)
        new = replace(old, generation=old.generation + 1)
        registry.publish(replace(current, advertisement=replace(current.advertisement, handle=new)))
        model.handles["root"] = new
        totals.control_records += 2
        totals.control_messages += 2
        totals.control_byte_hops += profile.control_hops * (2 * HANDLE_BYTES + 2 * profile.envelope_bytes)


def evaluate(workload: Workload, policy: Policy, profile: Profile = DEFAULT_PROFILE) -> dict[str, object]:
    """Measure each batch once, multiply deterministic packet counts, never benchmark."""
    model = fixture()
    totals = Totals()
    cold: CompiledProgram | None = None
    warm: CompiledProgram | None = None
    for index, count in enumerate(workload.batches):
        before = snapshot(model)
        work_before = sum(owner.update_records for owner in model.owners.values())
        if index:
            change(model, workload.event, index, totals, profile)
            if workload.event == "stale" and warm is not None:
                charge_packets(packet(model, warm, profile), 1, totals, profile, failed=True)
            if workload.event in {"replace", "expire", "stale"}:
                warm = None
        cold_miss = cold is None or (index > 0 and workload.event in {"replace", "expire", "stale"})
        if cold_miss:
            cold = encoding(model, "hybrid", 2)
            charge_query(cold, totals, profile)
        assert cold is not None
        cold_result = packet(model, cold, profile)
        totals.physical_paths.append(cold_result.path)
        if policy == "explicit":
            charge_packets(cold_result, count, totals, profile)
            totals.cold_packets += count
            if not cold_miss:
                totals.cache_hits += 1
        else:
            warm_miss = warm is None
            if warm_miss:
                # Explicit first packet/fallback needs no prior whole-route macro.
                charge_packets(cold_result, 1, totals, profile)
                totals.cold_packets += 1
                warm = encoding(model, "state-heavy", 0)
                charge_query(warm, totals, profile)
            else:
                totals.cache_hits += 1
            assert warm is not None
            warm_result = packet(model, warm, profile)
            if warm_result.path != cold_result.path:
                raise AssertionError("explicit and token routes differ")
            warm_count = count - int(warm_miss)
            charge_packets(warm_result, warm_count, totals, profile)
            totals.warm_packets += warm_count
        charge_tables(model, before, totals, profile)
        totals.table_write_delete_work += sum(owner.update_records for owner in model.owners.values()) - work_before
        observe_state(model, cold, warm, totals)
        totals.packets += count
    result = asdict(totals)
    result["observed_headers"] = sorted(totals.observed_headers)
    result["useful_application_bytes"] = totals.packets * profile.payload_bytes
    result["total_network_byte_hops"] = totals.data_byte_hops + totals.control_byte_hops
    result["byte_hops_per_useful_byte"] = (totals.data_byte_hops + totals.control_byte_hops) / (
        totals.packets * profile.payload_bytes
    )
    result["forwarding_lookup_total"] = totals.binding_lookups + totals.generation_lookups
    return result


def strict_break_even(
    control_increment: int, saving_per_packet_hop: int, hops: int, cold_packets: int = 1
) -> int | None:
    """Smallest packet count with STRICT positive byte-hop savings; memory stays separate."""
    if saving_per_packet_hop <= 0 or hops <= 0 or cold_packets < 0:
        return None
    return max(cold_packets, control_increment // (saving_per_packet_hop * hops) + cold_packets + 1)


def quic_header(cid_bytes: int, pn_bytes: int, tag_bytes: int = 16) -> int:
    """RFC 8200/768/9000: IPv6+UDP+short QUIC+AEAD, no frames or extension headers."""
    if not 0 <= cid_bytes <= 20 or not 1 <= pn_bytes <= 4 or tag_bytes != 16:
        raise ValueError("outside the declared RFC reference profile")
    return 40 + 8 + 1 + cid_bytes + pn_bytes + tag_bytes


def dominates(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    """No weighted score: equal components alone never establish a strict win."""
    return all(a <= b for a, b in zip(left, right, strict=True)) and any(
        a < b for a, b in zip(left, right, strict=True)
    )


def metric(result: dict[str, object], key: str) -> int:
    value = result[key]
    assert isinstance(value, int)
    return value


def run_study(profile: Profile = DEFAULT_PROFILE) -> dict[str, object]:
    """Same-action SR/BSID baseline gets identical semantics and resource accounting."""
    rows: dict[str, object] = {}
    for workload in WORKLOADS:
        explicit = evaluate(workload, "explicit", profile)
        token = evaluate(workload, "token", profile)
        dimensions = (
            "total_network_byte_hops",
            "peak_binding_compiler_bytes",
            "peak_ingress_cache_bytes",
            "forwarding_lookup_total",
            "table_write_delete_work",
            "failed_attempts",
        )
        explicit_vector = tuple(metric(explicit, key) for key in dimensions)
        token_vector = tuple(metric(token, key) for key in dimensions)
        net_saved = explicit_vector[0] - token_vector[0]
        last_path = token["physical_paths"]
        assert isinstance(last_path, list)
        last_hops = len(last_path[-1]) - 1
        # This is only a conditional continuation of the observed finite schedule.
        probe = fixture()
        coarse, bound = encoding(probe, "hybrid"), encoding(probe, "state-heavy")
        header_saving = coarse.code_bytes + coarse.context_bytes - bound.code_bytes - bound.context_bytes
        extra_packets = 0 if net_saved > 0 else (-net_saved) // (last_hops * header_saving) + 1
        # A deliberate restricted translation, NOT independent stock-SR validation.
        # The equivalence gate grants both machines identical instructions/widths.
        rows[workload.name] = {
            "workload": asdict(workload),
            "netsynth_explicit": explicit,
            "netsynth_shared_token": token,
            "sr_bsid_explicit": explicit,
            "sr_bsid_shared_token": token,
            "comparison": {
                "net_saved_byte_hops_token_vs_explicit": net_saved,
                "extra_packets_to_profit_if_final_path_cache_stabilize": extra_packets,
                "pareto_dimensions": dimensions,
                "token_dominates_explicit": dominates(token_vector, explicit_vector),
                "explicit_dominates_token": dominates(explicit_vector, token_vector),
                "vs_equal_action_sr_bsid": "tie_by_restricted_translation",
                "performance_gate": "unmeasured; no comparable-throughput/latency claim",
            },
        }
    cold = evaluate(Workload("threshold", (1,)), "explicit", profile)
    warm = evaluate(Workload("threshold", (1,)), "token", profile)
    delta = metric(warm, "control_byte_hops") - metric(cold, "control_byte_hops")
    model = fixture()
    explicit_program, token_program = encoding(model, "hybrid"), encoding(model, "state-heavy")
    saving = (
        explicit_program.code_bytes
        + explicit_program.context_bytes
        - token_program.code_bytes
        - token_program.context_bytes
    )
    hops = len(packet(model, explicit_program, profile).path) - 1
    return {
        "schema": "netsynth.resource-economics.v1",
        "provenance": {
            "compiler_counts": "existing Forwarding Program compiler/state accounting, 8-byte words and 12-byte handles",
            "control_bytes": "assumed delta-record serialization; per-owner request+ack, no standard wire format",
            "sr_baseline": "restricted equal-action/cost translation; derived equality, not independently measured stock SR",
            "cpu_cycles_latency_throughput": "not measured; no success claim for economics H1/performance gate",
            "cache_hits_unit": "retained program selections per batch, not per-packet cache probes",
        },
        "profile": asdict(profile),
        "envelope_field_bytes": ENVELOPE_FIELDS,
        "fixture": {
            "source": "forwarding_program_probe.fixture",
            "seed": None,
            "nodes": 10,
            "sampled": False,
            "coverage": "exhaustive declared deterministic batches only",
        },
        "reference_header_bytes": {
            "ipv6_udp_quic_cid8_pn2_tag16": quic_header(8, 2),
            "ipv6_udp_quic_cid0_pn2_tag16": quic_header(0, 2),
            "mpls_single_label_only": 4,
        },
        "packet_layout_bytes": {
            "explicit": {
                "route_code": explicit_program.code_bytes,
                "context": explicit_program.context_bytes,
                "envelope": profile.envelope_bytes,
            },
            "shared_token": {
                "route_code": token_program.code_bytes,
                "context": token_program.context_bytes,
                "envelope": profile.envelope_bytes,
            },
        },
        "reference_sources": [
            "https://www.rfc-editor.org/rfc/rfc8200.html",
            "https://www.rfc-editor.org/rfc/rfc768.html",
            "https://www.rfc-editor.org/rfc/rfc9000.html",
            "https://www.rfc-editor.org/rfc/rfc8439.html",
            "https://www.rfc-editor.org/rfc/rfc3032.html",
            "https://www.rfc-editor.org/rfc/rfc9256.html",
        ],
        "limitations": [
            "symbolic encoding/state sizes, not serialization, CPU cycles, throughput or latency",
            "SR/BSID is equal-action abstract translation, not deployed SR-MPLS/SRv6",
            "QUIC is header reference only; no equal unordered-message transport claim",
            "common Channel establishment, ACK/flow-control traffic and physical discovery excluded for all",
            "assumed 34-byte established envelope; no authenticated transport implementation added",
            "control hop distance is an input assumption, not a topology measurement",
            "cold explicit retains local STP bindings; not the privileged packet-heavy oracle",
            "retired compiled entries remain charged; no production GC/admission policy",
            "unshared means distinct retired program generations, not Channels forced into per-flow state",
        ],
        "break_even": {
            "incremental_control_byte_hops": delta,
            "saved_bytes_per_warm_packet_hop": saving,
            "hops": hops,
            "first_cold_packets": 1,
            "strict_min_packets": strict_break_even(delta, saving, hops),
            "condition": "(N-1)*hops*saved_bytes > incremental_control_byte_hops; static cache lifetime only",
        },
        "workloads": rows,
    }
