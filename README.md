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
