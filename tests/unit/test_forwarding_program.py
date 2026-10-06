"""Adversarial semantic checks; no performance or graph-family sweeps."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from netsynth.forwarding_program import (
    BindingRef,
    PacketBudget,
    ResourceContract,
    compile_hybrid,
    execute,
)
from netsynth.forwarding_program_probe import encoding, fixture, run_probe
from netsynth.scale4 import AdvertisedPathlet, PathletHandle, PhysicalHop, ScopedTransitPathlet


@pytest.mark.parametrize(
    "mode,capacity", [("packet-heavy", 0), ("state-heavy", 0), ("hybrid", 0), ("hybrid", 1), ("hybrid", 2)]
)
def test_same_route_and_fixed_wire_size(mode: str, capacity: int) -> None:
    model = fixture()
    program = encoding(model, mode, capacity)
    budget = PacketBudget(512, 64)
    result = execute(
        model.graph, model.owners, model.registries, program, 0, 9, budget, budget.payload_capacity(program)
    )
    assert result.status == "delivered"
    assert result.path == (0, 1, 2, 3, 5, 1, 2, 3, 6, 7, 9)
    assert set(result.wire_sizes) == {512}
    assert result.maximum_context_words <= capacity
    assert program.code_bytes + program.context_bytes + 64 + budget.payload_capacity(program) == 512


@pytest.mark.parametrize("capacity", [0, 1, 2])
def test_hidden_longer_repair_preserves_code_and_resource_contract(capacity: int) -> None:
    model = fixture()
    program = encoding(model, "hybrid", capacity)
    contracts = {name: owner.contract(model.handles[name]) for name, owner in model.owners.items()}
    counts = {name: owner.update_records for name, owner in model.owners.items()}
    model.owners["leaf"].repair(model.handles["leaf"], (PhysicalHop(1, 4), PhysicalHop(4, 8), PhysicalHop(8, 3)))
    assert encoding(model, "hybrid", capacity) == program
    assert {name: owner.contract(model.handles[name]) for name, owner in model.owners.items()} == contracts
    assert all(owner.update_records == counts[name] for name, owner in model.owners.items() if name != "leaf")
    budget = PacketBudget(512, 64)
    result = execute(
        model.graph, model.owners, model.registries, program, 0, 9, budget, budget.payload_capacity(program)
    )
    assert result.status == "delivered"
    assert result.path == (0, 1, 4, 8, 3, 5, 1, 4, 8, 3, 6, 7, 9)
    assert set(result.wire_sizes) == {512}


def test_less_context_spills_into_more_reusable_state() -> None:
    rich, small = fixture(), fixture()
    rich_program = encoding(rich, "hybrid", 2)
    small_program = encoding(small, "hybrid", 0)
    assert small_program.code_bytes == rich_program.code_bytes
    assert small_program.context_bytes < rich_program.context_bytes
    assert sum(len(owner.table) for owner in small.owners.values()) > sum(
        len(owner.table) for owner in rich.owners.values()
    )
    assert sum(owner.state_bytes for owner in small.owners.values()) > sum(
        owner.state_bytes for owner in rich.owners.values()
    )
    snapshot = {
        name: (dict(owner.table), owner.state_bytes, owner.update_records) for name, owner in small.owners.items()
    }
    for _ in range(4):
        assert encoding(small, "hybrid", 0) == small_program
        assert (
            execute(small.graph, small.owners, small.registries, small_program, 0, 9, PacketBudget(256, 64), 100).status
            == "delivered"
        )
    assert snapshot == {
        name: (dict(owner.table), owner.state_bytes, owner.update_records) for name, owner in small.owners.items()
    }


class OpaqueChild:
    """Expose only advertised contracts and an opaque owner-local install RPC."""

    __slots__ = ("_contract", "_installer", "calls")

    def __init__(
        self, contract: ResourceContract, install: Callable[[PathletHandle, BindingRef | None, int], BindingRef]
    ) -> None:
        self._contract = contract
        self._installer = install
        self.calls: list[tuple[PathletHandle, int]] = []

    def contract(self, handle: PathletHandle) -> ResourceContract:
        assert handle == self._contract.advertisement.handle
        return self._contract

    def install(self, handle: PathletHandle, continuation: BindingRef | None, capacity: int) -> BindingRef:
        self.contract(handle)
        self.calls.append((handle, capacity))
        return self._installer(handle, continuation, capacity)


def test_parent_uses_only_immediate_contracts_and_no_descendant_topology() -> None:
    model = fixture()
    # Replace every child view by an interface with no physical/realization accessor.
    for parent, child in (("inner", "leaf"), ("middle", "inner"), ("root", "middle")):
        compiler = model.owners[child]
        model.owners[parent].children = {child: OpaqueChild(compiler.contract(model.handles[child]), compiler.install)}
    middle = model.owners["middle"]
    public = OpaqueChild(middle.contract(model.handles["middle"]), middle.install)
    program = compile_hybrid(model.actions, {"middle": public}, 2)
    assert public.calls == [(model.handles["middle"], 2)]
    assert program.code[0] == PhysicalHop(0, 1)
    assert isinstance(program.code[1], BindingRef)
    assert program.code[2] == PhysicalHop(7, 9)
    # Only root crossings are physical in the packet. All detailed hops are owner-local.
    assert [item for item in program.code if isinstance(item, PhysicalHop)] == [PhysicalHop(0, 1), PhysicalHop(7, 9)]
    assert not hasattr(public, "registry") and not hasattr(public, "graph")
    with pytest.raises(KeyError):
        compile_hybrid((model.handles["leaf"],), {"middle": public}, 2)
    assert model.owners["middle"].contract(model.handles["middle"]).context_words == 2
    assert (
        execute(model.graph, model.owners, model.registries, program, 0, 9, PacketBudget(512, 64), 100).status
        == "delivered"
    )


@pytest.mark.parametrize("mode", ["packet-heavy", "state-heavy", "hybrid"])
def test_old_generation_cannot_alias_replacement(mode: str) -> None:
    model = fixture()
    program = encoding(model, mode)
    old = model.handles["leaf"]
    model.registries["leaf"].retire(old)
    new = replace(old, generation=1)
    model.registries["leaf"].publish(
        ScopedTransitPathlet(AdvertisedPathlet(new, 1, 3, 2), (PhysicalHop(1, 2), PhysicalHop(2, 3)))
    )
    result = execute(model.graph, model.owners, model.registries, program, 0, 9, PacketBudget(512, 64), 1)
    assert result.status == "stale_pathlet"
    assert result.path == (0, 1)
    leaf = model.owners["leaf"]
    assert leaf.install(new, None, 0) != leaf.install(new, None, 1)
    with pytest.raises(ValueError, match="stale"):
        leaf.install(old, None, 0)


def test_hard_resource_growth_rejected_before_repair_mutation() -> None:
    model = fixture()
    owner = model.owners["inner"]
    owner.contract(model.handles["inner"])
    leaf = model.owners["leaf"]
    larger = replace(leaf.contract(model.handles["leaf"]), context_words=3)
    owner.children = {"leaf": OpaqueChild(larger, leaf.install)}
    before = model.registries["inner"].lookup(model.handles["inner"])
    assert before is not None
    with pytest.raises(ValueError, match="new generation"):
        owner.repair(model.handles["inner"], (model.handles["leaf"], PhysicalHop(3, 6)))
    assert model.registries["inner"].lookup(model.handles["inner"]) == before


def test_packet_size_and_context_rejections_are_explicit() -> None:
    model = fixture()
    program = encoding(model, "hybrid", 2)
    with pytest.raises(ValueError, match="fit"):
        PacketBudget(80, 64).payload_capacity(program)
    with pytest.raises(ValueError, match="payload"):
        execute(model.graph, model.owners, model.registries, program, 0, 9, PacketBudget(512, 64), 1000)
    with pytest.raises(ValueError, match="negative"):
        encoding(model, "hybrid", -1)
    undersized = replace(program, context_words=0)
    result = execute(model.graph, model.owners, model.registries, undersized, 0, 9, PacketBudget(512, 64), 10)
    assert result.status == "context_exhausted"
    assert set(result.wire_sizes) == {undersized.code_bytes + undersized.context_bytes + 74}


def test_invalid_physical_hop_and_hop_budget_fail_closed() -> None:
    model = fixture()
    program = encoding(model, "hybrid")
    result = execute(
        model.graph, model.owners, model.registries, program, 0, 9, PacketBudget(512, 64), 10, hop_budget=1
    )
    assert result.status == "hop_budget_exhausted"
    broken = model.graph.without(edges=frozenset({(1, 2)}))
    result = execute(broken, model.owners, model.registries, program, 0, 9, PacketBudget(512, 64), 10)
    assert result.status == "invalid_physical_hop"


def test_local_repair_cannot_encode_a_hidden_descendant_hop() -> None:
    model = fixture()
    program = encoding(model, "hybrid")
    owner = model.owners["middle"]
    before = dict(owner.table), owner.update_records
    with pytest.raises(ValueError, match="visible"):
        owner.repair(model.handles["middle"], (PhysicalHop(1, 2), PhysicalHop(2, 7)))
    assert (dict(owner.table), owner.update_records) == before
    assert encoding(model, "hybrid") == program


def test_reproducible_probe() -> None:
    assert run_probe() == run_probe()
