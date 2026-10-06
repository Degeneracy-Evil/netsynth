# NetSynth

NetSynth is a clean-slate computer-network architecture research project.

The project derives a network architecture from first principles, introducing new abstractions only when the previous model fails. Compatibility with Ethernet/IP/TCP/BGP/DNS is not a design requirement, but established mathematics and modern systems work are mandatory constraints and sources of reusable ideas.

## Current architecture

The primary architecture entry point is [`docs/architecture-v0.1.md`](docs/architecture-v0.1.md).

Related project guidance:
- [`docs/architecture-recentering.md`](docs/architecture-recentering.md): research direction and methodology;
- [`AGENTS.md`](AGENTS.md): implementation/research rules for coding agents.

The current architecture includes Routing Scopes, Boundary Transit Graphs and opaque Scoped Transit Pathlets, Structured Locators, pull-based route resolution, stable Endpoint IDs with versioned bindings, reliable unordered Message Channels, a minimal Security Floor, and versioned Scope layouts for structural evolution.

Service naming and group communication remain above the common core.

NetSynth Architecture v0.1 is now semantically frozen. Its forwarding plane uses a hybrid compiled model: packets carry finite coarse Route Code, while Scopes retain reusable local forwarding bindings and packets reserve bounded writable forwarding context. See `docs/architecture-v0.1-freeze-review.md`.

## Semantic prototypes

Tiny deterministic probes validate frozen architecture choices:

```bash
uv run --locked python src/scale4_main.py
uv run --locked python src/scale5_main.py
uv run --locked python src/scale6_main.py
uv run --locked python src/security_floor_main.py
uv run --locked python src/scope_evolution_main.py
uv run --locked python src/forwarding_program_main.py
uv run --locked python scripts/check.py
```

These probes validate semantics and ownership boundaries. They are not performance benchmarks or production protocol implementations.

The [forwarding-program validation](docs/forwarding-program-validation.md) compares packet-heavy, state-heavy and hybrid encodings on one tiny topology, including bounded-context spilling and a longer hidden STP repair.

## Historical experiments

The repository still contains Phase 1-5 routing/decomposition experiments and scaling studies. They remain useful as derivation history, negative controls, regression infrastructure, and evidence about state/stretch/churn and hierarchy failure modes.

Their prefix-monotone forwarding and metric-aware hierarchy designs are **not** the current NetSynth architecture.

Historical documents such as [`docs/architecture.md`](docs/architecture.md) and [`docs/simulator.md`](docs/simulator.md) are derivation records, not current architecture authority.

## Research method

```text
architecture question
    -> theory / prior-art reconciliation
    -> explicit NetSynth choice
    -> minimal semantic validation
```

Do not use large simulator sweeps to rediscover established theory, and do not turn every theoretical alternative into a first-class NetSynth abstraction.

## Development

The codebase uses Python 3.14, uv, Ruff, strict mypy, and pytest.

```bash
uv run --locked python scripts/check.py
```
