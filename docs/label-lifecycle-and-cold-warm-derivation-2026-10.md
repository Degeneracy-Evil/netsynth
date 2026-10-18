# NetSynth 冷/热转发与短标签生命周期推导（2026-10-18）

> **状态：理论研究与下一轮最小验证设计；不修改 v0.1 冻结语义，不确定 wire-format，不要求 XDP 或完整协议栈。**
>
> **要回答的问题：** 在保证同样的物理转发、失效安全、Channel 交付语义、有限包长的情况下，显式 Route Code 与短标签何时各自更省资源？短标签能否长期安全地重复利用？现有逐节点样例是否已经证明显式方案值得保留？

## 1. 从现有实验证据开始，而不是理想账本

截至提交 64e2ae1 的逐节点真实序列化样例：

| 方案 | 每包头部 | 节点表记录 | 节点状态镜像 | 表 / generation 读 |
| --- | ---: | ---: | ---: | ---: |
| NetSynth warm macro | 71B | 19 | 931B | 19 / 19 |
| NetSynth explicit，2 槽 | 111B | 14 | 726B | 17 / 17 |
| NetSynth explicit，0 槽 | 91B | 17 | 837B | 17 / 17 |
| 独立局部标签交换 | 49B | 16 | 564B | 16 / 16 |

这些是一个十跳样例、固定长度记录的确定性账本，不是 RAM/ASIC 实测、吞吐、时延，也不是最优压缩下界。

**重要负例：在这个已安装的单条可复用路线中，49B 标签方案不仅短，而且表状态更小、查表次数更少。** 不能宣称 NetSynth 显式路径在该样例中的总体状态必然更省。111B 显式模式表记录数较少（14 vs 16），但实际表镜像仍更大。

71B warm 相比 49B 多 22B，来自：
- NetSynth prefix 12B vs label prefix 6B：+6；
- Scope/Token/generation 当前键 10B vs MPLS 4B shim：+6；
- 包内重复 Route Code 10B vs 已安装标签无此字段：+10。

两边都包括相同的 7B Locator、16B transport 元数据与 16B AEAD tag。本样例不存在“NetSynth 已经比标签交换省”的结果。

本研究要判断的是：能否让 NetSynth 的数据面 profile 采用短标签，同时在不适合预安装的请求上使用显式转发。由于原架构已允许 packet/state 之间的不同信息分配，这不要求增加新的核心网络层。

## 2. 先定义“真正需要的资源”

比较相同成功交付数据、相同物理路径和相同安全/可靠性要求时的资源向量：

    R=(network byte-hops, persistent forwarding bytes, peak forwarding bytes,
       control byte-hops, table operations, CPU cycles, stall/retry/loss)

先分别比较，不给 RAM、带宽、时延混合赋任意权重。

某条编译路线在一个有效生命周期内送 N 包，经过 d 跳，显式头 H_E，短标签头 H_L，额外安装/撤销控制流量 U（byte-hops），忽略丢包且路径不变时：

    r = d*(H_E-H_L)                 每包短标签节省的 byte-hops
    DeltaB = (N-N_cold)*r-U         净网络字节·跳节省

N_cold 是因为必须先显式发送或探测而不能使用已安装标签的数据包数，通常可为 0 或 1，也可能更多。

短标签胜出的条件为：

    (N-N_cold)*d*(H_E-H_L)>U

这不是多资源总胜利：内存、查表、更新时延仍必须单独满足硬预算。

对 64e2ae1 的相同十跳路径，**仅作为每包差额**：
- explicit 0-slot 91B 对 49B 标签，r=420 byte-hops/packet；
- explicit 2-slot 111B 对 49B 标签，r=620 byte-hops/packet；
- 71B warm 对 49B 标签，r=220 byte-hops/packet。

不能沿用 e3f1356 原本 “34B / hop；U=1710 byte-hops” 的第 7 包结论；当对照变成独立、实际序列化的标签实现后，安装、控制和删除成本必须重新实测/建模，且可以不同。

如果需要每个硬 generation 重装，令 j 遍历各生命周期：

    DeltaB_total = sum_j [ (N_j-Ncold_j)*d_j*DeltaH_j - U_j ]
                   - bytes_wasted_by_failures

不可把长时间内所有包当作同一个稳定生命周期。

## 3. 证明一个不得逃避的限制：有限短标签不可能在任意旧引用下无限安全复用

假设旧转发动作 A 使用一个可见标签 x，随后同一个节点将标签 x 重新赋予不等价动作 B。

若：
1. 新旧数据包在该节点用于选择转发表的所有可观察字段完全相同；
2. 节点没有其他能区别旧/新上下文的可信信息；
3. 旧引用/旧包可能在任意未来时刻再次出现；

那么接收到旧 x 的节点必然按新动作 B 解释它。这和“旧引用必须 fail closed、不得 alias 新含义”矛盾。

这是最简单的**不可区分性反例**，不是新定理。

因此长期有限标签池必须选择至少一种保证：
- 在相关生命周期内不重用 token（直到命名空间耗尽）；
- 增加可在转发点检查的 epoch/generation/版本信息；
- 使用撤销确认 + 所有合法旧引用停止注入 + 有界在途生命周期 + 回收隔离期；
- 使用另一个明确受约束的、不混淆旧包的上下文区分机制（如每接口/租约域）；其成本仍须计入。

仅凭 IP/MPLS 的 Hop Budget/TTL（限制跳数，而非无限排队的真实时间）**不能证明有界在途墙上时间**。端点 AEAD 可以避免最终交付给错误 Channel，却不能使中途错误转发变成“fail closed”。

现有 RFC 5036 LDP 明确规定 Withdraw/Release，并在部分标签撤销场景警告不能在收到释放之前重用。这是成熟的先例，不应自称发明回收算法。

## 4. 标签回收的最小生命周期

~~~text
unallocated
   ↓ allocate+install; wait for acknowledgement
installed (not yet issued to ingress)
   ↓ publish / enable at ingress
active
   ├── same-hard-generation local repair -> active
   └── retire / replace / cache migration
             ↓
        stop issuance
             ↓
        revoke + upstream acknowledgements
             ↓
        drain / quarantine (or fail closed)
             ↓
        free for reuse
~~~

**关键区别：**
- 删除一条路由器表项可以立即使尚在途旧包失败，不要求零丢失。
- **重新使用旧标签值** 却必须防止仍有旧包按新含义被接纳。

设 t_stop 为所有有权发行旧标签的可信入口最后可能发出旧标签的时刻，D_max 为从合法最后一次发行到旧包离开相关转发点的最大停留时间。

若存在已证明的 D_max，并且控制面保证 t_stop（发布/撤销已确认、旧 ingress 缓存不能再次注入），则安全重用的充分条件为：

    t_reuse >= t_stop + D_max

此外必须保证无其它未被纳入的旧标签注入者；这是对可信边界的假设，不是任意拜占庭发送者的保证。

没有 D_max 或发行截止保证，**固定等待若干秒**不构成严格安全证明。对于要求无限时间、无限更新仍能长期运行的系统：
- 要么增加能区分历史的版本/租约条件并限制它们的重用；
- 要么为资源耗尽定义合法拒绝行为；
- 不能同时承诺“有限不带版本标签、立即无限循环重用、任意延迟旧引用都不会 alias”。

有强 per-packet/flow 一致性要求时，还需要额外的网络更新机制；本项目已冻结的本地修复只承诺 fail closed，不承诺修复时零丢包。Reitblatt et al. SIGCOMM 2012 已系统研究了更强更新一致性。

## 5. 标签空间的容量界

假设一个节点的可用标签总数 B，当前活动标签数 A(t)，标签退休率 lambda(t)，回收隔离期 Q。

在固定上界或稳定速率的近似下：

    B_required >= A_max + ceil(lambda_max*Q)

更准确地，退休待回收标签数应按窗口 [t-Q,t] 中的实际退休事件计算，并加上活动标签数量；这只是存储/名字空间必要条件，并非完整更新协议。

单个 20-bit 标签字段理论最多 1,048,576 个值，若预留前 16 值（MPLS 常见规则），最多约 1,048,560 个普通值，且本样例更多保留限制也要扣除。

例：A=100,000 个活动 token，lambda=20,000 次/秒，Q=60 秒：

    B_required >= 100000 + 20000*60 = 1,300,000

超过 20-bit 容量，至少需要 21 个有效 token 位，或者减少标签数、缩短真实安全隔离期、改变状态分配/命名空间策略。

如 Q 降到 30 秒，则必要数为 700,000，20-bit 容量在该简化模型下足够。

这不是预测现实世界每个节点发生 20k 次标签退休/秒；是刻意构造的边界条件。高 churn 场景必须保留显式/不额外安装路径状态的可能性。

每接口标签空间可从入端口等已有上下文得到更细作用域，降低各命名空间压力，但需要正确的邻接与发行者限制；这正是 RFC 3031 已有的标签空间设计。

## 6. 路径多样性才决定短标签是否继续赢

当前只有一条已安装整路径程序，因此标签方案能高度复用。

考虑 D 条互不共享的长短不一的目标路线：

- Label policy 的额外成本可能随 **需要保持活动的、无法合并的 forwarding policy 数量** 增长。
- 显式方案将每条路线的更多选择信息放在 ingress/cache/packet 中，可能复用相同的 STP 基础转发表。
- 如果多个路线能共享尾段/宏，标签方案同样允许复用和合并，不能人为禁止。

所以不能从当前 10 节点一条路线的样例推出：
- 显式模式在短流上一定更省状态（当前单路线模型反例）；
- 标签模式对大量不同路线仍总是更省状态；
- NetSynth 的两模式动态选择是其独有功能（SR 也可以有 token + segments）。

当前真正缺失的维度是：
**独立路线数、各路线复用次数、共享 STP 比例、更新/安全回收成本**。

下一轮若做最小验证，应优先加入一组“同一物理图、多个不同 Route Program”而不是继续扩大单条路径的包数。

## 7. 无未来信息的决定：安装还是继续显式发送？

将本次生命周期中每个显式包相对于短标签的额外成本看作 r，预安装成本 U，那么选择对应经典 online **ski-rental（租滑雪板/买滑雪板）**：

- 每包显式发送：交 r（租）；
- 安装一个有效整路径标签：交 U（买），之后省 r；
- 未来会出现多少包未知。

离线最佳增量成本为：

    OPT(N) = min(N*r, U)

这里为了展示标准模型，假设可在第一包前安装。现实 NetSynth 可能必须先发至少一个 cold 包，需相应扣除 N_cold。

经典确定性阈值策略“累计租用成本约达到 U 后买”在此理想单次生命周期模型中有至多约 2 倍离线最优成本的竞争比；**不是 NetSynth 独创算法**，也不是对多资源多缓存问题的 2 倍保证。

例如 U=2100 byte-hops、r=420 byte-hops/packet：
- 如果 N=2，离线应显式：额外成本 840，立刻安装要 2100；
- 如果 N=100，离线应尽早安装：2100，而始终显式成本 42,000；
- 延迟五包再安装可避免极短生命周期的多余安装，但会失去开始五包的潜在节省。

如果加入缓存容量 M、多个程序竞争资源、重装/更新、包头适应 PMTU、等待安装时延，这变成带资源约束的 online caching / switching-cost 问题，**不能无条件套用**单对象 2 倍界；CacheFlow、DevoFlow 等已有接近研究。

## 8. 从理论上给出 v0.1 的合理数据面 profile

这是候选编译输出形态，**不修改已冻结 NetSynth 的混合转发架构**：

### Explicit path (无专用整路线宏)

- 入口携带较完整的 Route Code 与已经分配的固定 Context；
- 可复用基础 Scope/STP 状态仍然存在，**不等于完全无状态转发**；
- 用于一次性需求、高路径多样性、标签未安装、表容量吃紧或短暂失效恢复；
- 不能凭空假定 Scope STP 状态已存在且免费，其跨方案共同成本应单独报告。

### Bound path (整路径短标签)

- 完整的 route code 缓存在转发表，packet 只带当前节点/邻接可解释的短标签与端到端 Channel 数据；
- 更新 Scope 内部 realization 可保持合法外层 handle；
- 安装标签必须先确保所需下游表状态生效，再允许入口开始引用；
- 允许同代修复造成旧在途包丢失；不允许退役短标签立即复用引发错路由；
- 标签生命周期与重装/回收计入成本，不把无限 monontonic IDs 当作生产设计。

### 不应强制对所有流都启用任一模式

若“额外短标签收益”无法覆盖安装、保留、回收开销，选择 Explicit；
若短标签的 state/CPU/控制成本在预算内，且有足够共享与复用，选择 Bound。

注意：能做这个选择并不意味着相比强现代 SR/BSID 架构有独有优势。目标是更干净的等价功能与更少部署成本，需在公平强基线上测量。

## 9. 当前推导给出的决策

**通过：**
- 单程序路径上，标签压缩确实有显著的每包字节优势；NetSynth 不该因为名字不同而拒绝直接采用该思想。
- 安装与回收成本可以形成严格的 break-even 条件。
- 有限短标签、无限旧引用和无限安全重用不可兼得；这解释了为什么所谓 49B 不完全免费。
- 冷/热自适应是合理的工程策略，但其在线算法已属于成熟研究。

**未通过 / 尚未证明：**
- NetSynth 相对强 SR/BSID 的独特优势；
- “Cold path 总是比 Label path 减少转发状态”的宣称（现有单路径样例不成立）；
- 安全回收后仍保持 49B 的实测长期成本；
- 在多路线/高状态压力下任何特定编译策略的优越性；
- CPU、吞吐、尾延迟不退化。

**最小的下一项验证：**
给现有 node-local 标签/显式引擎加入多个独立但部分重叠的真实 Route Program 和一条明确的撤销/隔离时序；计量 label allocation/withdraw/release/quarantine 的控制流量、峰值活动+退役名字空间、安装前的可达性和运行时切换代价。无需大规模拓扑仿真，也不需要先做硬件数据面。必须允许 SR/BSID 对照采用同样的显式/标签双模式和回收策略，否则不是公平比较。

## 10. 文献与适用边界

- RFC 3031（per-interface / per-platform label space）：https://www.rfc-editor.org/rfc/rfc3031.html
- RFC 5036（Label Withdraw、Label Release、Conservative vs Liberal retention）：https://www.rfc-editor.org/rfc/rfc5036.html
- RFC 9256（stable BSID and SR Policy）：https://www.rfc-editor.org/rfc/rfc9256.html
- Reitblatt et al. (SIGCOMM 2012), Abstractions for Network Update：https://www.cs.princeton.edu/~dpw/papers/network-update-sigcomm12.pdf
- DevoFlow (SIGCOMM 2011), scaling fine-grained flows：https://conferences.sigcomm.org/sigcomm/2011/papers/sigcomm/p254.pdf
- CacheFlow (SOSR 2016), dependency-aware rule caching：https://collaborate.princeton.edu/en/publications/cacheflow-dependency-aware-rule-caching-for-software-defined-netw/
- 当前内部实验：commit e3f1356、commit 64e2ae1。

本文所得安全条件是精确定义假设下的结论，不自动适用于恶意任意注入的外部环境；涉及端点身份与可信传输的安全语义仍以 NetSynth Security Floor 为准。
