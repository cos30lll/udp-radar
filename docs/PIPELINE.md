# 实现流程速览与证据等级

完整从零教程现在位于 [FROM_ZERO.md](FROM_ZERO.md)，具体token/汇编检索位于 [EVIDENCE_WALKTHROUGH.md](EVIDENCE_WALKTHROUGH.md)。本篇保留架构速览，不代替主教程。

本文件回答“这套雷达是怎么一步步做出来的”，并明确哪些步骤有静态/流量证据，哪些只是工程选择。

## 0. 输入边界

需要你自己合法持有的三类输入：

1. **游戏安装/热更新文件**：用于静态确认协议、实体与字段语义。
2. **自己设备、自己账号的运行流量**：用于验证解析，不随仓库分发。
3. **目标 Android 环境**：Root 抓包/端口探测，以及可运行 Python 的 proot Ubuntu。

仓库不包含 APK、`libil2cpp.so`、`global-metadata.dat`、`UpdateScript`、原始 Dump、PCAP、CSV 或会话日志。

## 1. 静态取证：确认“谁在发包、字段是什么”

固定样本：`UpdateScript_500.dll`（`UpdateScript` 热更新托管程序集），以及原生 `libjelib.so`。工具见 `research/`。

流程：

1. 从 UnityFS TextAsset 提取托管 DLL：`research/extract_hotupdate.py`。
2. 用 Mono.Cecil 建类型/方法索引和网络关键词候选：`research/managed/StaticAssemblyInspect`（`index` 模式）。
3. 用自定义 attributes（传输路由属性）确定 module/command → handler 方法：`ProtocolEvidenceInspect routes`，再对候选 token 导出 IL。
4. 对原生库反汇编：`research/disassemble_native.py`，重点看 `JeUdpClient::udpParse`、`AsyncSend`、`msgParse`、`RecvLoop`、`JeMsgQueue::PushMsg`。

已得到的**代码级**结论：

- 上行/下行应用消息外壳：`module(u16 BE) + command(u16 BE) + protobuf-like payload`。
- 3/852 是场景更新；实体字段 1/2/3 为运行时编号/次编号/类别，字段 4 是动作列表。
- Position 动作 = 1，值字段是三分量整数，按消息 scale（1000）还原为世界单位。
- HP 动作 = 31，第一值按既有固定 IL 取证经 `conv.i4` 写入生命值字段。其他值用途需回到对应 IL 复核；本轮未重新独立确认，尤其不能当作最大血量。
- 姓名/UID 消息模型读取字段 1 实体号、字段 2 UInt64 UID、字段 3 UTF-8 姓名；登录 3/1 还写本地 UID 与本地实体号。
- 3/6 是玩家增删；字段 2 可为 packed/unpacked UInt32 移除编号；场景 3/852 字段 7 也可删除实体。
- 独立 RPC 通道存在，但**没有证据证明本局身份初始化一定走 TCP 或独立 RPC**；不能把“存在 RPC”当作总根因。
- 855 是阶段变化、861 是 UInt32→UInt32 字典更新、858 是语音录制，不能冒充姓名或 HP 消息来源。

证据等级：**A=固定版本字节码/IL 明确调用链；B=真实流量与 A 相互印证；C=基于命名或统计的推断；D=未确认**。上述为 A（除特别标注者），`docs/PROTOCOL.md` 有更细的 token/RVA 和反例。

## 2. 传输层：从 PCAP 到“干净的应用消息”

`protocol.py` 的执行顺序：

1. 解析经典 PCAP（不读 pcapng），按 link type 取 IPv4/IPv6 UDP；跳过 IP 分片（计数）。
2. 过滤：只接受端口命中游戏本地 UDP 端口的**入站**包；忽略出站、控制/ACK、重复包。
3. `transport_segments()`：当一个 UDP 记录实际含多条消息时，用头校验（`byte0 == (length + flag + seq_bytes) & 0xFF`）和连续序号链拆分。只有**唯一完整解**才拆分，否则原样交给下一层并计错，绝不猜切点。
4. 单条头：首段 10 字节（8 字节公共头 + 2 字节），后续分片 8 字节；`flag & 0x20` 表示分片、`0x40` 表示后面还有分片、`0x80` 表示 Zstd 压缩。
5. 有界顺序重组：首段必须已出现；后续序号连续；15 秒、8 MiB、512 段、16 条流上限。缺片/乱序中断重建，单独计数。
6. Zstd 解压（`libzstd`，限制最大输出）。
7. 读 `module/command`，分派身份或场景消息。

为什么以前会漏名字：同一 PCAP 记录里连续两条 3/6 名单，旧版把整个载荷当成一条 Protobuf，尾部被当成非法字段，整条记录丢弃。v2.2 才补上“多结果”接口和两个后端读取点。

## 3. 身份与坐标关联

`identity.py` 解析 3/1、3/3、3/6、3/2005：

- 3/1 重置名单，并设置本地 UID/本地实体号。
- 3/3/3/6 增量名单；3/6 还可带移除 ID。
- 每个玩家必须有运行时实体号才进入表；姓名为 UTF-8 严格解码。

`server.py` 用 `local_port@peer` 隔离不同传输流。坐标实体类别 4 才尝试按 `id1` 匹配名单：

- 先按 UID 与本机本地 UID 比较得出 `is_local`；没有 UID 时才用本地实体号比较。
- 姓名只来自真实名单，不做位置接近、Owner 动作或上行自身坐标推断。
- 3/2005 可能表示当前观察目标；观战时“自己”不保证等于原登录账号。

## 4. 状态机与网页

后端每 0.12 秒轮询 PCAP 增量：

- Position 动作生成实体快照 + 60 点轨迹；
- 动作 31 更新 HP 原值和独立时间戳；
- 3/852 字段 7 与 3/6 移除同步删除实体和 HP；
- 300 秒过期、最多 512 实体/HP、名单最多 2048；
- 位置日志 16 MiB、元数据 8 MiB 后停止新增，避免一个会话写满存储；
- 诊断 JSON 约每 2 秒原子落盘，记录协议号、动作号、缓冲/分片/错误和“是否观测到身份/HP31”。

`app.js` 默认 X/Z 投影，3 秒未更新变灰、30 秒隐藏；自动选择 `is_local=true` 的最新实体并跟随；手动点选只换参考，不篡改身份。状态中明确显示“未观测到”而不是伪造值。

## 5. 抓包生命周期（v2.1 起）

旧版只在发现游戏端口后启动 `tcpdump`，并在端口列表变化时停启，造成数秒空窗和多个 PCAP。v2.1：

- 先启动单次 `tcpdump -i any -w capture-0001.pcap udp`，再起后端；
- `ss` 每秒取游戏 PID 的 UDP 端口，只更新解码端口集合；
- 端口新出现时，从有界短期缓存补解析该端口历史记录；
- 游戏 PID 变化则清空实体/身份/HP/顺序状态，并用进程开始时间排除旧进程流量；
- 默认 600 秒或会话目录约 64 MiB 停止；该体积检查按秒轮询，不是硬上限。

工程代价：原始 PCAP 是**全机 UDP**，可能含其他应用流量；应用层仍只解码游戏端口。是否采用这一模式，应在自己的隐私边界内决定。

## 6. 复现的三条路线

- **运行复现**：完整仓库手动复制到手机 → 手机 Ubuntu 检查/`deploy_android.py --android-local --write` → 原生 Android 条件检查 → 用户手动启动。电脑端可用 `--stage` 暂存，但它不会传输到手机。
- **解析复现**：`tools/replay_pcap.py` + 自己的 PCAP/CSV，检查坐标逐条一致和统计。
- **研究复现**：使用 `research/` 重做静态证据。只有 `restore_inputs.py` 强制固定哈希门禁；提取/反汇编工具记录哈希，使用者需自行核对固定输入。SDK 构建与依赖准备边界见 REPRODUCE。

具体命令和预期输出见 `docs/REPRODUCE.md`；证据边界见 `docs/VALIDATION.md`。
