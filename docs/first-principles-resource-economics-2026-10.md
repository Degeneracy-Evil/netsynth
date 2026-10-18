# 从第一性原理推导 NetSynth 的资源收益（2026-10-18）

> **状态：设计研究准则与可证伪的候选模型，不修改冻结的 NetSynth v0.1 语义，不冻结任何 wire-format。**
>
> **新目标：同等功能与安全条件下，保持吞吐/延迟在明确容忍范围内，至少严格减少一个具有实际价值的资源消耗；必须把新增状态、建立与维护开销一起计费。**
>
> 注意：这是比“发现前所未有的协议机制”更宽的系统研究目标。已有思想的合理整合可以产生工程价值，但不得以此宣称理论原创性。

## 1. 校准研究目标

以前审查得出的结论“Scope/STP/BSID 等已有大量先例”仍成立；它阻止我们凭概念相似度声称原创，却**没有证明实际 NetSynth 和现代协议栈在字节数、CPU、硬件约束、控制面更新代价上必然相同**。

项目不是为了创造抽象而创造抽象，而是从通信所需的最少信息与状态出发，设计一套不需要迁就历史 wire format 的体系。

设在相同物理链路、数据和安全可靠性下，一个网络方案的资源向量为：

~~~text
R = (
  transmitted-byte-hops per useful application byte,
  CPU cycles per useful application byte,
  persistent endpoint/router memory,
  control-update byte-hops and work,
  failure recovery loss/outage,
  application completion time
)
~~~

不提前将它们相加成单一分数。不同资源维度不能直接把“64 字节 RAM”和“64 字节网络流量”相减。

先用 **Pareto / 硬约束**：

- 正确性、可靠性、认证强度与交付语义不弱于公平基线；
- goodput 不低于基线乘以 (1-epsilon_T)；
- p99 延迟不高于基线乘以 (1+epsilon_L)；
- 明确 CPU、转发表内存、控制更新上限；
- 在满足约束下至少有一种资源有稳定显著的节约。

epsilon 是研究者事先写下的容忍度，不是看见结果以后调整。

## 2. 从最少必需信息开始

一个数据包送达并正确接收，需要：

1. 物理输出方向或可解释的路由选择；
2. 能确定它属于哪个接收通信上下文；
3. 可靠传输所需的包/消息/片段标识（具体是否都需要逐包出现取决于语义与共享上下文）；
4. 防止循环的有限转发预算，或等价的结构安全条件；
5. 认证与机密性所需的证明/标签；
6. 应用数据。

**不必要求每一个包重复携带完整 Endpoint ID、完整 Locator、完整内层物理路径和所有首次建立时的公共参数。** 它们只需在真正使用者正确解释当前包时可用。

这不代表这些信息消失：它们可能被提前绑定在端点的 Channel 状态、Scope 中的共享转发状态、初始控制消息或路由解析缓存中。

### 2.1 一个简单的信息论边界

一个接收者在已有本地上下文 Y 后，仍必须从 K 种同等可能、不可混淆的动作 X 中选择一个。

- 固定长度索引最少需要 ceil(log2 K) 位。
- 对非均匀分布且允许适当编码的情形，平均新信息量受 H(X|Y) 限制。

这是一般的信息论事实，不是 NetSynth 特有定理。

例如一个局部转发表同时可能解释 2^20 个不同活动上下文，其固定 token 至少需要 20 bit，向上取整为 3 字节；对更多上下文不得宣称同样的短 token 永远足够。

重要限制：

- token 的版本、有效期、作用域和拒绝旧引用需要额外处理；
- token 只是索引，**不是授权证明**；端到端认证不能由短 token 代替；
- 映射表本身占内存，其一致性/撤销/安装都需要资源；
- 如果路径/上下文变化很快，状态可能不值得缓存。

### 2.2 分清谁必须知道什么

- 中间转发节点只需决定合法的下一跳及对应局部操作，通常不必知道远端 EID 或 Channel 全状态。
- 接收端需要正确的 Channel 及其已认证 EID 关联，不一定需要报文每次携带全长 EID。
- 入口需要足够的路径/Locator 信息建立或查到下一段转发程序，不意味着每个后续包都携带完整 Route Program。
- 同一批 Channel 如果共享一个 STP/转发程序，应复用该局部转发状态，而不是在每台路由器装 per-Channel 条目。

这是 v0.1 生命周期与信息归属思想的自然实现方向，不是新加网络层。

## 3. 无兼容性条件下的两种包型：推导候选，不是最终格式

建议**先研究两个表述极端**，不能为了短包头而对所有流强制安装状态。

### Cold / Explicit

新通信、首个包、token 失效或缓存未命中时，包含足够的 Locator/程序/建立信息，按原架构路径执行。其头部可能较大，但没有前置的大规模逐流配置要求。

### Warm / Bound

稳定长生命周期 Channel、复用率高的 STP，采用短局部 Route Token 与 Receive Token；EID 关联与路径实现来自已建立/已授权上下文。

示意：

~~~text
[flags/hop budget][local route token][receiver channel token]
[packet/message/fragment info][AEAD tag][data]
~~~

这只是信息类别示意。控制报文、ACK 与异常/迁移包可能需要不同字段。未来实际 profile 必须逐字段给出字节账单，并证明不会打破：
- stale token fail closed；
- 无意外 token 混淆；
- 同 Scope 修复和硬版本语义；
- 端到端 EID 验证；
- 安全/丢包/乱序/重放；
- ingress PMTU 和不增长包；
- 无 per-flow transit state。

## 4. 小模型 A：假设性的 warm packet 有多少字节机会？

这不是提议定稿，也不是测量结果；仅用于估算是否值得花精力验证。

选同样 **IPv6 + UDP + QUIC 1-RTT（加密、建立后）** 的常见比较口径：

- IPv6 固定 40B；
- UDP 8B；
- QUIC short header 固定标志 1B，PN 假定 2B，接收 CID 假定 8B；并计 16B AEAD tag；
- 合计 75B，**未计 QUIC stream frame 的额外编码**；
- QUIC 合法的零长度 CID 情形对应 67B，但在移动、NAT rebinding、同端点多路复用上具有额外约束；
- Ethernet 等共同外层成本统一不计。

构造一个**假设可行**的 NetSynth warm-profile 帐本：

| 字段 | 假设字节 |
| --- | ---: |
| flags + Hop Budget | 2 |
| Scope-local Route Token | 4 |
| receive Channel token | 4 |
| packet number | 4 |
| Message ID | 4 |
| fragment/packetization info | 4 |
| authentication tag | 16 |
| **合计** | **38** |

这里的 38B 是待验证预算，**不是证明能实现**：特别需要检查多个作用域的 token 使用方式、抗重放窗口、变长消息/ACK 编码、PMTU 与路径重解析是否需要更多字段。

固定 1500B 的共同可承载预算下（仅信息空间比较，不是实测吞吐）：

- QUIC 8B CID：可承载 1425B；假设 NetSynth 可承载 1462B，理论数据空间多约 2.60%。
- QUIC 0B CID：可承载 1433B；NetSynth 1462B，多约 2.02%。
- 共同预算只有 256B 时，对应 181B / 189B / 218B；多约 20.44% / 15.34%。

以上不是“NetSynth 比 QUIC 吞吐快 2.6%”。真实 CPU、发送打包效率、缓冲、链路前导码/FCS/IFG、丢包和控制包都可能改变结果。

如果 NetSynth 必须逐包携带昂贵的 Route Code，上述目标可能失败；因此必须分别记录显式路径、已缓存路径，以及短流比例。不能只挑 warm case 展示最好数字。

强基线包括 QUIC 短头/零 CID、MPLS/SR 本地转发以及 ROHC 一类通过已有上下文压缩报头的技术。ROHC 已经明确研究压缩率与丢包/状态失效之间的权衡，所以不能宣称状态化头部压缩是新思想。

## 5. 小模型 B：状态交换是否真的划算？

对一种具有可共享的固定路径程序，定义：

- N：被该程序服务的数据包总数；
- h：相对于等价显式包，每个 packet 每一跳节省的字节数；
- d：共用该数据包路径的转发链路数；
- U：为维持新方案，额外产生的控制流量，单位 byte-hops；
- M：新增持久转发状态，单位 bytes；
- X：新增处理工作，如查表/管理成本，单位 CPU cycles。

那么净节省的**网络流量（按 byte-hops 计）**：

    DeltaB = N * d * h - U

若只看网络承载字节，成立的充要条件是：

    N > U/(d*h)

但这只是一个维度的盈亏平衡；不能拿它掩盖 M 和 X。

透明的假设例子：

~~~text
d=4 hops; h=16 B/packet/hop;
incremental U=4096 byte-hops;
incremental state M=4*64=256 B.
~~~

阈值为 N>64。发送 1000 包时节省 64000 byte-hops，减掉控制 4096 后为 59904 byte-hops；发送 10 包时只节省 640 byte-hops，反而不够覆盖建立代价。

这不是 NetSynth 对实际 TCP/QUIC 的成本测量。h、U、M 必须在真实编译器和对照栈上测量；尤其强 IP/SR 基线本身也可能有控制开销，U 必须算相对于强基线的**增量**。

### 5.1 共享复用而非 per-flow 状态

若 Q 个 Channel 复用一个程序，转发器新增状态依赖的是**可复用程序数量**，而不是直接依赖 Channel 数。

反例也清晰：如果每个 Channel 都需要独特路径且无法共享，程序状态可能退化为 per-flow；与现有无状态 IP FIB 相比会很差。

此时应选择显式/更少本地绑定的编码，而不是强制 warm。

### 5.2 故障和更新改变盈亏

令 F 为路径硬契约失效次数，S 为每次重装的增量 byte-hop 成本，则：

    DeltaB = N*d*h - (U_initial + F*S)

同代隐藏修复如果保持外层 token，可降低 F；但不能免费忽略内部表更新、质量变差和软指标更新。

这个潜在收益在 SR Policy / Binding SID 中也能实现，故不是唯一创新。需要比较实际可用实现资源开销和硬约束。

## 6. 为什么两段式执行比“全体都用最短包”更合理？

- 冷启动：安装短 token 的往返通信与状态维护可能比一个直接带完整路径的包贵。
- 热通道：大量数据包重复发送不变信息，短 token 有摊销空间。
- 网络剧烈变化：状态频繁过期，热模式可能退化甚至额外丢包。
- 转发表吃紧：若表满，编译器应该选择更显式的包状态，而非无限制安装 per-flow 表。

因此架构选择不是统一要求短头，而是由可实现的成本/资源约束选择编码。这也符合已冻结的 hybrid compiled forwarding。

## 7. 上一轮“应用提示”问题如何处置

前一份 application-progress-research-probe.md 已经得出静态不准确信号收益条件：

    p > (1 + 2*delta/tau)/n

但 QUIC/RFC 9218 已经提供应用调度与更新优先级的接口，2026 年不确定 coflow 优化仍有直接研究。因此单凭“应用更早继续”无法证明 NetSynth 核心的必要性。

当前策略：
- 保留有限提示作为将来的应用负载/接口优化；
- 同样提示必须给予 QUIC、Homa、SIRD 等对照方案；
- 优先做资源最小化的架构级推导，而不立刻让路由器理解计算任务依赖。

## 8. 本轮可证伪假设

**H1 — 热包成本：** 在长期复用、变更较少的通信中，NetSynth 的 warm profile 能满足相同语义/安全并减少每个成功传输的应用字节所对应的网络头部与线速字节，不使 CPU/尾延迟明显退化。

**H2 — 共享状态：** 在有真实路径复用的负载下，短 token 带来的状态开销主要和不同共享 forwarding program 数量而非 Channel 数量相关。

**H3 — 自适应冷/热：** 对短流、表内存紧张和高变更区域，合理编译器能避免固定 state-heavy 策略带来的建立/更新浪费，至少不会被简单的显式路径方案系统性击败。

这些是普通系统实验可测的假设，**不是经证明的新颖网络定理**。

## 9. 何时值得继续？

下一步先做一个极小的、纯资源级的理论/确定性验证，不改协议栈：

1. 从 v0.1 既有 Route Program / compiled forwarding 数据取出真实长度和共享率；
2. 显式统计 packet code/context、每跳 token lookup、installed state、重编译更新；
3. 对比一个同能力的 hierarchical SR/BSID-like 抽象基线，以及实际 IPv6/QUIC 短头预算；
4. 比较长会话、多消息短会话、完全无复用、隐藏修路频繁四种情况；
5. 输出 **每个指标独立的 Pareto 结果**，不要只给一个加权总分。

成功门槛：证明至少一个清楚划定的负载区域实现“同等语义/相近性能 + 某项资源净减少”，且非该负载区域有明确退化保护。失败则停下来查资源不可压缩下界与强基线等价性。

本阶段绝对不需要新的 10000 节点模拟器、XDP 数据面或完整 transport stack。

## 10. 参考资料及适用范围

- RFC 8200 IPv6 固定报头：https://www.rfc-editor.org/rfc/rfc8200.html
- RFC 9000 QUIC 短报头、变长 CID、PN 与应用优先级：https://www.rfc-editor.org/rfc/rfc9000.html
- RFC 9308 QUIC 0 长度 CID 的适用边界：https://www.rfc-editor.org/rfc/rfc9308.html
- RFC 9218 HTTP 优先级更新：https://www.rfc-editor.org/rfc/rfc9218.html
- RFC 5795 ROHC 状态化压缩与鲁棒性：https://www.rfc-editor.org/rfc/rfc5795.html
- RFC 3032 MPLS 4 字节标签：https://www.rfc-editor.org/rfc/rfc3032.html
- Chiesa et al., area/pathlet 层次实现：https://www.sciencedirect.com/science/article/abs/pii/S0140366414000978
- RFC 9256 SR Policy：https://www.rfc-editor.org/rfc/rfc9256.html
- SIRD NSDI 2025：https://www.usenix.org/conference/nsdi25/presentation/prasopoulos
- AdaCoflow 2026（不确定调度也有新研究）：https://www.sciencedirect.com/science/article/pii/S1389128626005384

**最终判断：** NetSynth 的价值可以是“相近服务水平下严格节约资源”的工程/架构整合，而不要求发现此前数学上不可能实现的功能。是否真的节约还未建立；当前获得的是条件、账本、下界与适用/失败边界。
