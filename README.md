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

## Running phase-1 experiments

Run the built-in small suite (tree, mesh, irregular random, and expander-like hostile topology):

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
  "failure_sample_count": 20
}
```

Supported generated families are `tree`, `mesh2d`, `torus2d`, `random_geometric`, `small_world`,
`erdos_renyi`, `clos`, and `expander_like`. A `null` pair sample means exhaustive ordered pairs; a `null`
failure sample means all generated single-link, single-node, and random-link-set events. JSON output records all
generation, decomposition, routing, sampling, failure, and metric-schema inputs needed to reproduce a run.

To import a physical graph, use `"topology_family": "json"` and `"topology_parameters": {"path": "graph.json"}`.
The graph file has `nodes` and `links` lists; each link has `left`, `right`, and optional positive `cost` and
`capacity` fields. Imported experiments record the source file's SHA-256 digest.
