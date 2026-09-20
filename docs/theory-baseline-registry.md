# Compact-Routing Theory Baseline Registry

> Status: theory registry. The entries below define comparison targets; they are not an implementation checklist and do not authorize development.

## 1. Flat exact shortest-path routing

Model:
- arbitrary weighted graph;
- fixed or designer ports;
- any destination naming if a full name->next-port entry is stored.

Guarantees:
- stretch 1;
- conceptually Theta(n) destination entries per forwarding node;
- with explicit fixed-port identifiers this is typically Theta(n log n) routing bits per node.

Role in NetSynth:
- exact non-compact reference;
- not a candidate scalable universal scheme.

## 2. Exact labeled routing on trees

Classical results of Fraigniaud-Gavoille and Thorup-Zwick give exact shortest-path routing on weighted trees.

Fixed-port form used by later compact-routing work:
- stretch 1;
- O(log^2 n / log log n) bits for local routing information, destination label, and header;
- constant-time routing decision.

Designer-port variants can use asymptotically smaller labels; the port model must therefore be part of the scheme metadata.

Role:
- sanity baseline for graph-family specialization;
- proof that a universal API must support label-based routing without Scope summaries.

## 3. Thorup-Zwick stretch-3 labeled routing

General weighted undirected graph.

Classic k=2 result:
- name-dependent/labeled;
- about O~(sqrt(n)) bits of routing memory per node;
- stretch 3;
- very short destination/header representation, with the strongest compact form using designer-controlled ports;
- constant routing decision time.

Known lower bounds show stretch below 3 cannot be achieved universally with sublinear local memory.

Role:
- canonical general-graph labeled compact-routing baseline.

## 4. Thorup-Zwick parameterized handshake family

For integer k>1 on weighted undirected graphs, the 2001 scheme gives approximately:
- O~(n^(1/k)) routing space per node;
- small topology-dependent labels and packet headers;
- direct/no-handshake stretch 4k-5;
- after one round of handshaking, steady-session stretch 2k-1.

The original paper explicitly treats destination-label acquisition as outside its routing problem and notes that a header can be cached for a stream of packets.

Role:
- canonical baseline for NetSynth Resolution + Session Routing Context;
- shows that handshake/session state is part of established compact-routing design space.

Modern work must also note the 2025 Kadria-Roditty improvements rather than treating the 2001 direct bound as current state of the art.

## 5. 2025 Kadria-Roditty general-graph reference

Weighted undirected graphs:
- direct compact routing with O~(n^(1/k)) average local storage and about 2.64k stretch;
- optimal 2k-1 roundtrip/handshake stretch construction.

Role:
- current theory reference when claiming a new universal state/stretch point;
- not necessarily the first implementation target because the purpose of NetSynth is architecture composition, not reproducing the newest proof machinery immediately.

## 6. Name-independent minimum-stretch routing

Abraham-Gavoille-Malkhi-Nisan-Thorup, weighted undirected graph, arbitrary O(log n)-bit node names, fixed-port model.

Guarantees:
- stretch 3;
- O~(sqrt(n)) local routing state;
- concrete construction uses O(log^2 n / log log n)-bit writable headers and constant-time routing decisions.

Important lower-bound context:
- sublinear local memory cannot universally achieve stretch below 3;
- stretch below 5 requires Omega(sqrt(n))-scale local storage;
- their paper also proves that loop-free name-independent routing without header rewriting cannot use o(n) bits at every node on all graphs; writable header state is therefore a fundamental resource axis, not an implementation flourish.

Role:
- baseline against explicit Endpoint-ID resolution to labeled routing.

## 7. Earlier name-independent distributed-dictionary routing

Arias-Cowen-Laing-Rajaraman-Taka and related work:
- uses distributed dictionary/search machinery to translate arbitrary names into topology-dependent routing information during routing;
- demonstrates explicitly that name-independent routing can internalize what an architecture might otherwise expose as a separate resolution function.

Role:
- baseline for "in-path resolution" placement.

## 8. Low-doubling-dimension routing

Known compact-routing schemes for weighted low-doubling networks include:
- labeled (1+epsilon)-stretch schemes with O(log n)-scale routing labels and polylogarithmic local routing information for bounded/slowly growing doubling dimension;
- name-independent schemes with larger constant stretch under comparable structural assumptions;
- dynamic variants have also been studied.

Exact polynomial/polylog factors depend on the selected paper/model and must be recorded when an implementation is chosen.

Role:
- evidence that graph-family-specific routing should be a profile capability, not forced through one universal general-graph Scope construction.

## 9. LISP / HIP / ILNP / UIA architecture references

These are not compact-routing theorems, but they constrain novelty claims around naming.

LISP:
- EID/RLOC separation;
- Mapping System;
- core/edge separation;
- multihoming and mobility use cases.

HIP:
- separate Host Identity namespace;
- protocol layer between internetworking and transport;
- mobility/multihoming support.

ILNP:
- explicit Identifier and Locator namespaces with different semantics.

UIA:
- stable endpoint identities;
- location/routing discovery;
- thesis explores name-dependent compact routing with topology-sensitive locators, directory lookup, and conversation reuse.

Role:
- prior-art baseline for any NetSynth claim about stable identity, locator/descriptor resolution, or cached conversations.

## 10. Experimental interpretation rules

When a baseline is eventually implemented, output must separate:

~~~text
theorem:
    worst-case model and guarantee

implementation:
    which construction/version was implemented
    any simplifications/deviations

measurement:
    state bits on this graph
    header/label bits
    stretch distribution
    construction/update cost
    resolution/session overhead
~~~

Measured performance must never be described as re-establishing the theorem.

## 11. Initial implementation priority after framework refactor

Likely order, subject to final architecture approval:

1. Flat exact routing wrapper.
2. Historical Scope scheme wrapper.
3. Exact labeled tree routing baseline.
4. One faithful general-graph labeled compact-routing baseline.
5. One name-independent baseline or distributed-dictionary composition.
6. Specialized graph-family scheme only when a profile experiment needs it.

Do not implement all theory baselines before the generic interface itself has regression tests.
