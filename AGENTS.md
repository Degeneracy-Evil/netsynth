# NetSynth agent guide

NetSynth 是 clean-slate 计算机网络架构研究项目。当前权威架构入口是 `docs/architecture-v0.1.md`。

代码的职责是**验证或反驳架构语义**，不能为了实现方便替架构做决定。

## 1. 研究顺序

任何新的机制、Phase 或较大实验，都必须遵循：

```text
architecture question
    -> theory / prior-art reconciliation
    -> explicit architecture choice
    -> minimal semantic validation
```

Clean-slate 只表示不受现有协议兼容性约束，**不表示重新发明成熟理论**。

提出新机制之前必须先检查：对应的数学/系统问题、已知上下界与 impossibility/hardness、现代系统已有的类似信息布局，以及哪些复杂性只是兼容 IPv4/IPv6/MPLS/SRv6/TCP 的历史包袱。

## 2. 当前架构状态

以下语义已经冻结，除非后续需求暴露具体矛盾，否则不要擅自重做：

- Scale 0-3 的最小 forwarding / routing-control 原则；
- Scale 4 的 Routing Scope / BTG / STP / scoped route resolution；
- Scope 生命周期：形成、局部修复、split/merge、layout generation、renumbering；
- Scale 5 的 Endpoint ID / Binding / mobility / multihoming；
- Scale 6 的可靠 unordered Message Channel；
- Security Floor；
- service naming 边界；
- group communication 边界。

对应 freeze review：
- `docs/scale4-freeze-review.md`
- `docs/scale5-freeze-review.md`
- `docs/scale6-freeze-review.md`
- `docs/security-floor-freeze-review.md`
- `docs/scope-lifecycle-freeze-review.md`

当前 forwarding-program 架构已经选择 **hybrid compiled forwarding**，详见 `docs/forwarding-program-architecture.md`。

当前任务是做最小语义验证，而不是重新选择架构。必须同时阅读：
- `docs/packet-carried-routing-theory-reconciliation.md`
- `docs/forwarding-program-architecture.md`
- `docs/path-packet-size.md`

旧的固定 Transit Stack / `max_additional_transit_slots` 表述已经被更一般的资源模型取代。

## 3. 核心架构纪律

```text
physical connectivity = arbitrary graph

Scope hierarchy =
    knowledge / control / ownership / change-containment structure

physical route != Scope tree
```

禁止默认重新引入 prefix-monotone forwarding、固定 fanout/depth、global pathlet flooding、global routing epoch、global EID FIB、home-agent 式永久 forwarding pointer、默认 Stream/Lane/Subchannel，以及为不可压缩图制造假 hierarchy。

如果一个 region 没有实际压缩/containment 收益，允许保持 flat。

## 4. 信息生命周期

实现必须尊重不同状态的生命周期与 ownership：

```text
Endpoint ID
Binding / LocatorSet
Locator
Route Program
STP generation
STP internal realization
physical link/queue state
```

transport 必须保持：

```text
Channel identity / reliability state
        !=
Path State (Locator / Route / RTT / congestion / packet size)
```

更快变化的信息不应无理由导致更慢层级状态失效。

## 5. 数据面与 routing state

Scale 4 已确定：parent 只能消费 immediate-child contracts；不能查看 descendant physical topology；STP 是 opaque reusable transit service；destination-specific route state 按需 pull；stale generation fail closed；内部变化优先 local repair。

但 **packet-carried forwarding 的具体编码尚未冻结**。不要把 literal label stack 当成最终架构。

当前资源模型至少要显式收费：persistent forwarding state、packet route-code bits、writable forwarding context、forwarding processing、path quality/stretch、update/churn cost。

## 6. 兼容性与现代系统

不需要兼容 Ethernet、IPv4/IPv6、TCP/UDP/QUIC wire format、BGP、DNS、MPLS/SRv6、port namespace。

但必须主动学习现代系统和理论，并区分成熟思想与兼容旧体系带来的复杂性。

## 7. Security boundary

Security Floor 已冻结最低语义：self-certifying EID、delegated operational roles、signed Binding、authenticated Channel establishment、AEAD Channel。

不要默认继续扩展 Web PKI、human/service identity、revocation transparency、anonymity、Byzantine routing、hardware attestation。

## 8. 实验纪律

实验必须验证 NetSynth-specific semantic delta，而不是已知 theorem。

- 可复现；
- 参数/seed/schema 机器可读；
- 明确 sampled / exhaustive；
- 不从少量点宣称渐近复杂度；
- 必须保留不利拓扑/反例；
- 不为了结果好看临时加 feature；
- semantic prototype 优先 tiny deterministic adversarial fixture。

## 9. 工程约定

- Python 3.14 + uv；
- Ruff；
- strict mypy；
- pytest；
- 完整检查 non-mutating；
- 不无理由引入重量级 framework 或重复工具。

修改后至少运行：

```bash
uv run --locked python scripts/check.py
```

## 10. 历史代码

Phase 1-5 路由/分解实验保留为 derivation history、regression、negative control 和 research infrastructure。它们不是当前架构权威。

不要因为历史代码里已有某个 abstraction，就自动把它继续带入新架构。