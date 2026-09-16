# NetSynth agent guide

本仓库基于 Python 项目模板，当前用于 clean-slate 计算机网络架构研究与模拟验证。

## 工程约定

- 使用 Python 3.14 和 uv。
- Ruff 负责格式化与 lint，行宽 120。
- mypy 使用 strict 模式。
- pytest 是测试框架。
- runtime dependency 默认保持为空，确有实验需求时再增加。
- 完整检查必须保持 non-mutating。
- pre-commit 只检查 staged snapshot，不修改文件，也不自动 stage。
- 不无理由增加重复的 formatter、linter、type checker、package manager 或 framework。

修改后执行：

```bash
uv run --locked python scripts/check.py
uv run --locked python src/main.py
```

## 项目目的

NetSynth 不是现有互联网协议的重新实现。项目从两个计算机之间的最小通信问题开始，逐渐扩大网络规模，在旧模型真正失效时才引入新的架构概念。

当前架构背景见 `docs/architecture.md`，第一阶段模拟目标见 `docs/simulator.md`。

代码的职责是验证或反驳架构假设，而不是为了实现方便替架构做决定。

## 当前硬边界

1. **不考虑兼容性。** Ethernet、IPv4/IPv6、TCP/UDP/QUIC、DNS、BGP、VLAN、MAC 地址、port 等都不是默认前提。除非作为比较基线或架构文档明确重新引入，否则不要照搬。
2. **暂不考虑安全。** Authentication、encryption、authorization、privacy、spoofing、adversarial routing 等不属于当前阶段。
3. **暂不考虑无线和弱网。** 当前参考环境是稳定有线网络，不设计共享无线介质、高随机丢包、极端 jitter 等问题。
4. **不要把实现细节升级成协议要求。** Python 类型、整数宽度、第三方图库的数据结构、某个方便的算法都不自动成为 NetSynth 架构的一部分。
5. **不要只针对单一场景优化 common core。** 后续至少要能检查 general-purpose wired、datacenter/HPC、constrained/IoT 三类 profile。某个场景专有能力优先留在 profile，而不是塞入公共核心。
6. **优先暴露反例，不要堆 feature 掩盖失败。** 如果 Scope/Locator 假设在某类拓扑上表现很差，应保留并报告结果，而不是未经架构讨论就加入特殊规则让实验“变好看”。

## 第一阶段实现范围

只实现 `docs/simulator.md` 定义的 routing architecture simulator，重点包括：

- 物理 graph 的生成或导入；
- flat full-knowledge routing baseline；
- recursive scope decomposition 的表示；
- quotient / multi-resolution graph；
- compressed routing 实验；
- link/node failure 注入；
- State、Stretch、Churn、Failure Locality 四类核心指标；
- 可复现实验输出。

第一阶段不要实现 Endpoint ID、Rendezvous、Channel/Transport、wire format、congestion control 或 application protocol。

## 架构纪律

新增抽象前，必须说明哪个具体问题迫使它出现。如果删除一个抽象后系统仍能完整回答原问题，优先删除或合并它。

始终保持以下区别：

```text
physical connectivity = arbitrary graph
scope hierarchy        = compression structure（当前待验证假设）
routing                 = graph routing，不是 tree routing
```

Scope 默认不得绑定国家、地区、运营商、厂商、数据中心、机架或行政组织语义。

## 实验纪律

- 所有实验必须可复现，机器可读输出中保存 topology 参数、seed、decomposition/routing 参数和 metric schema/version。
- compressed routing 必须与**同一张物理图**上的 flat baseline 比较。
- sampled result 必须明确标记为 sampled，不能当成 exhaustive。
- 不从少量实验点直接宣称渐近复杂度。
- 必须包含对当前假设不友好的拓扑，尤其是难以分区/压缩的 graph。目标是寻找架构边界，而不是证明当前方案一定正确。

## 代码结构原则

初期保持小而清晰，优先把以下职责分开：

- topology generation；
- decomposition strategy；
- routing strategy；
- failure/event injection；
- metric collection；
- experiment runner/output。

不要提前引入重量级 framework。测试优先保证 graph transform、route validity、metric definition 和 deterministic reproducibility 的正确性，再考虑性能。

如果实现过程中暴露出架构歧义，不要默默选择传统网络的答案；先记录歧义并回到架构讨论。
