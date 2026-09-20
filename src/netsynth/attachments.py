"""Bottom-up hierarchical attachment lookahead for prefix-monotone forwarding."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from types import MappingProxyType
from typing import Literal

from netsynth.decomposition import Scope, ScopeTree
from netsynth.forwarding import ForwardingKnowledge, ForwardingNetwork, Locator, LocatorCatalog
from netsynth.graph import Graph, Node
from netsynth.routing import PersistentObject, RoutingSnapshot

Lookahead = Literal[1, 2, 3, "full"]
DestinationKey = tuple[int, ...] | Locator


@dataclass(frozen=True)
class AttachmentCompilation:
    """Converged forwarding state and auditable fixed-point metadata."""

    network: ForwardingNetwork
    rounds: dict[str, int]


def compile_attachment_forwarding(
    graph: Graph,
    reference_graph: Graph,
    tree: ScopeTree,
    catalog: LocatorCatalog,
    lookahead: Lookahead,
) -> AttachmentCompilation:
    """Build recursively composable potentials without descendant-topology queries."""
    tables: dict[tuple[str, DestinationKey], dict[Node, float]] = {}
    rounds: dict[str, int] = {}
    attachments: dict[tuple[str, DestinationKey, Node], tuple[str, float | None]] = {}
    keys_by_scope: dict[str, set[DestinationKey]] = {scope.identifier: set() for scope in tree.scopes()}

    def build(scope: Scope, key: DestinationKey) -> dict[Node, float]:
        table_key = (scope.identifier, key)
        if table_key in tables:
            return tables[table_key]
        if scope.is_leaf:
            if not isinstance(key, Locator):
                raise ValueError("leaf attachment target must be a destination Locator")
            target = _node_for_locator(catalog, key)
            values, count = _fixed_point(graph, scope, {target: 0.0} if target in graph.nodes else {})
        else:
            child = _target_child(scope, key, catalog)
            child_prefix = _scope_prefix(child, catalog)
            if isinstance(key, tuple) and key == child_prefix:
                terminals = dict.fromkeys(child.members.intersection(graph.nodes), 0.0)
            else:
                child_values = build(child, key)
                terminals = {}
                for boundary in _scope_boundary(child, reference_graph):
                    value = child_values.get(boundary, inf)
                    terminals[boundary] = value
                    attachments[(scope.identifier, key, boundary)] = (
                        child.identifier,
                        None if value == inf else value,
                    )
            values, count = _fixed_point(graph, scope, terminals)
        tables[table_key] = values
        rounds[f"{scope.identifier}:{key}"] = count
        keys_by_scope[scope.identifier].add(key)
        return values

    for target in sorted(graph.nodes):
        destination = catalog.by_node[target]
        lineage = tree.lineage(target)
        build(lineage[-1], destination)
        for scope in lineage[:-1]:
            depth = len(_scope_prefix(scope, catalog))
            key: DestinationKey
            if lookahead == "full":
                key = destination
            else:
                checkpoint = min(((depth // lookahead) + 1) * lookahead, len(destination.components))
                key = destination.components[:checkpoint]
            build(scope, key)

    knowledge: dict[Locator, ForwardingKnowledge] = {}
    objects: dict[tuple[Node, str, str, str], PersistentObject] = {}
    node_by_locator = {locator: node for node, locator in catalog.by_node.items()}
    for owner in sorted(graph.nodes):
        locator = catalog.by_node[owner]
        neighbors = {catalog.by_node[node]: edge.cost for node, edge in graph.neighbors(owner)}
        eligible: dict[DestinationKey, tuple[Locator, ...]] = {}
        selected: dict[DestinationKey, Locator] = {}
        for scope in tree.lineage(owner):
            for key in sorted(keys_by_scope[scope.identifier], key=str):
                values = tables[(scope.identifier, key)]
                current = values.get(owner, inf)
                choices = tuple(
                    sorted(
                        catalog.by_node[neighbor]
                        for neighbor, _edge in graph.neighbors(owner)
                        if neighbor in scope.members and values.get(neighbor, inf) < current
                    )
                )
                eligible[key] = choices
                if choices:
                    selected[key] = min(
                        choices,
                        key=lambda hop: (neighbors[hop] + values[node_by_locator[hop]], hop),
                    )
                key_size = _key_size(key)
                objects[(owner, "potential_record", scope.identifier, str(key))] = PersistentObject(
                    (key, None if current == inf else current), key_size + 1
                )
                for hop in choices:
                    objects[(owner, "eligible_next_hop", scope.identifier, f"{key}:{hop}")] = PersistentObject(
                        (key, hop), key_size + hop.component_count
                    )
        objects[(owner, "own_locator", "local", "self")] = PersistentObject((locator,), locator.component_count)
        for neighbor, cost in neighbors.items():
            objects[(owner, "neighbor_link", "local", str(neighbor))] = PersistentObject(
                (neighbor, cost), neighbor.component_count + 1
            )
        knowledge[locator] = ForwardingKnowledge(
            locator,
            MappingProxyType(neighbors),
            MappingProxyType(selected),
            frozenset(catalog.by_node[node] for node in tree.leaf_for(owner).members),
            MappingProxyType(eligible),
            lookahead,
        )
    for (scope_id, key, boundary), (child_id, value) in attachments.items():
        locator = catalog.by_node[boundary]
        objects[(boundary, "attachment_advertisement", scope_id, f"{key}:{locator}")] = PersistentObject(
            (child_id, key, locator, value), _key_size(key) + locator.component_count + 1
        )
    network = ForwardingNetwork(MappingProxyType(knowledge), RoutingSnapshot(objects), catalog)
    return AttachmentCompilation(network, rounds)


def _fixed_point(graph: Graph, scope: Scope, terminals: dict[Node, float]) -> tuple[dict[Node, float], int]:
    """Converge from neighbor values plus explicit terminal attachment advertisements."""
    present = graph.nodes.intersection(scope.members)
    fixed = present.intersection(terminals)
    values = {node: terminals.get(node, inf) for node in present}
    rounds = 0
    while True:
        updated = dict(values)
        for node in sorted(present.difference(fixed)):
            updated[node] = min(
                (edge.cost + values[neighbor] for neighbor, edge in graph.neighbors(node) if neighbor in present),
                default=inf,
            )
        if updated == values:
            return values, rounds
        values = updated
        rounds += 1


def _target_child(scope: Scope, key: DestinationKey, catalog: LocatorCatalog) -> Scope:
    components = key.components if isinstance(key, Locator) else key
    return next(
        child
        for child in scope.children
        if components[: len(_scope_prefix(child, catalog))] == _scope_prefix(child, catalog)
    )


def _scope_prefix(scope: Scope, catalog: LocatorCatalog) -> tuple[int, ...]:
    components = [catalog.by_node[node].components for node in scope.members]
    index = 0
    while index < min(map(len, components)) and len({value[index] for value in components}) == 1:
        index += 1
    return components[0][:index]


def _scope_boundary(child: Scope, reference: Graph) -> tuple[Node, ...]:
    return tuple(
        sorted(
            {
                node
                for edge in reference.edges
                for node, other in ((edge.left, edge.right), (edge.right, edge.left))
                if node in child.members and other not in child.members
            }
        )
    )


def _node_for_locator(catalog: LocatorCatalog, target: Locator) -> Node:
    return next(node for node, locator in catalog.by_node.items() if locator == target)


def _key_size(key: DestinationKey) -> int:
    return key.component_count if isinstance(key, Locator) else len(key)
