# NetSynth

NetSynth is a clean-slate computer-network architecture research project.

The project starts from the smallest possible network—two computers connected by a point-to-point link—and increases scale step by step. New architectural concepts are introduced only when the previous model fails. The long-term goal is to derive a common network core that can scale from simple systems to world-scale networks without inheriting compatibility constraints from today's Internet stack.

Current work focuses on testing a multi-resolution routing hypothesis based on topology compression, Routing Scopes, and Structured Locators.

## Documents

- [`docs/architecture.md`](docs/architecture.md): current architecture derivation, boundaries, decisions, and open questions.
- [`docs/simulator.md`](docs/simulator.md): first routing-simulator experiment plan and metrics.
- [`AGENTS.md`](AGENTS.md): development and experiment constraints for coding agents.

## Current scope

The first implementation phase is a routing architecture simulator. It compares flat full-knowledge routing with recursive topology compression and measures:

- routing state;
- path stretch;
- control churn;
- failure locality.

Compatibility with existing network protocols, security, wireless/weak-network behavior, transport protocols, and application protocols are intentionally outside the current phase.

The codebase uses Python 3.14, uv, Ruff, mypy, and pytest.

## Running Phase-4 experiments

Run the built-in exhaustive small-graph suite. It compares Flat shortest paths, the Phase-2 recursive oracle,
R0/S0/S1/S2/S3 controls, scoped-potential forwarding, and attachment lookahead `h=1/2/3/full`. It includes two seeds per family, a label-only
permutation, a fixed-structure relabeling control, and a skewed-link-cost variant. Every strategy on one graph shares the same fixed decomposition,
ordered source/destination pairs, and failure events:

```bash
uv run --locked python src/main.py --output results.json
```

Or pass `--config experiment.json`. The file may contain one object or a list of objects:

```json
{
  "topology_family": "mesh2d",
  "topology_parameters": {"rows": 10, "columns": 10},
  "seed": 42,
  "leaf_size": 8,
  "pair_sample_count": null,
  "failure_sample_count": 20,
  "s1_bundle_representatives": 2,
  "s2_landmark_counts": [1, 2, 4],
  "cost_profile": "skewed",
  "label_permutation_seed": 17,
  "fixed_structure_label_seed": 19,
  "hop_budget": 100
}
```

Supported generated families are `tree`, `mesh2d`, `torus2d`, `random_geometric`, `small_world`,
`erdos_renyi`, `clos`, and `expander_like`. A `null` pair sample means exhaustive ordered pairs; a `null`
failure sample means all generated single-link, single-node, and random-link-set events. JSON output records all
generation, decomposition, summary-budget, routing, sampling, failure, state-accounting, and metric-schema inputs
needed to reproduce a run.

The summary budgets are:

- `R0`: exact boundary-interface connectivity components with deliberately uniform abstract cost (the reachability floor);
- `S0`: sibling adjacency and crossing-link metadata only;
- `S1`: boundary bundles with a bounded number of representative crossings;
- `S2(k)`: `k` stable boundary landmarks, landmark distances, and boundary attachments;
- `S3`: every stable boundary node and the complete boundary-distance matrix.

Summaries are constructed bottom-up. A non-leaf scope sees only immediate-child summaries and physical crossings
between those children. Results report forwarding, local/global detailed topology, quotient, crossing/bundle,
portal, attachment, distance, and reachability-component/interface state separately, both as object counts and normalized scalar sizes.
R0's persistent component representation is linear in boundary interfaces; pairwise abstract edges are transient
compiler input, not stored or legal next hops. S0/S1 remain negative controls, not candidate reachability floors.

Phase-3 data-plane forwarding receives only the destination's Structured Locator, a Hop Budget, and its own
immutable prefix-indexed FIB. The per-node control plane compiles this FIB from local-leaf detail and charged
ancestor crossings/remote sibling summaries. The physical graph is used by the separate executor only to validate
and price selected hops. Outputs distinguish delivered, no-route, invalid-next-hop, loop, and Hop-Budget-exhausted
routes, and report locator/reference component counts without claiming a wire encoding.
The Phase-3.2 candidate obtains one scalar potential per relevant Scope child prefix (and leaf-local destination)
through scoped neighbor-to-neighbor fixed-point updates. Its architectural forwarding object is the set of adjacent
physical neighbors with strictly lower potential. The experiment deterministically selects one member, while
reporting the complete eligible-set distribution. It consumes neither R0 summaries nor remote topology.

Phase 4 publishes recursively composed boundary attachment costs. A parent sees only its child's boundary values,
not descendant topology. Finite lookahead uses Locator-depth segment checkpoints so every node can recover the
active checkpoint from its own Locator and the unchanged destination Locator; full lookahead carries exact
destination attachment values through the hierarchy. Output separates information stretch (`h/full`) from
hierarchy stretch (`full/Flat`) and charges attachment, potential, and eligible-next-hop records independently.
Failure output separately classifies physical partitions, changed boundary reachability, unchanged boundary relation,
and cases where a fixed scope loses internal connectivity while the physical graph stays connected. Such cases can
remain unreachable under the prefix-monotone forwarding domain. Scoped potentials eliminate stable loops when
every fixed Scope remains connected; scope-breaking repair and destination/component attachment remain out of scope.

Run the modest lookahead scaling study (16, 32, 64, and 128 nodes by default) with:

```bash
uv run --locked python src/scaling_main.py --output scaling.json
```

It samples ordered pairs and reports state, stretch, reachability outcomes, and one failure's churn/locality per
topology. These empirical sizes are not an asymptotic complexity claim.

To import a physical graph, use `"topology_family": "json"` and `"topology_parameters": {"path": "graph.json"}`.
The graph file has `nodes` and `links` lists; each link has `left`, `right`, and optional positive `cost` and
`capacity` fields. Imported experiments record the source file's SHA-256 digest.
