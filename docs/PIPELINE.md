# UDP 雷达的实现流程

后端从 PCAP 读取 UDP 记录，拆出身份和场景消息，再把实体状态交给网页绘制。开发步骤和程序集、汇编的查阅方法见[从零实现](FROM_ZERO.md)和[证据阅读指南](EVIDENCE_WALKTHROUGH.md)。

## 输入

复现需要自己持有的游戏安装和热更新文件，以及自己的设备和账号产生的流量。手机上用 Android Root 环境抓包和查端口，用 proot Ubuntu 运行 Python。

仓库不包含 APK、`libil2cpp.so`、`global-metadata.dat`、`UpdateScript`、原始 Dump、PCAP、CSV 或会话日志。

## 协议和字段来源

分析使用托管热更新程序集 `UpdateScript_500.dll` 和原生库 `libjelib.so`，工具都在 `research/`。

1. 用 `research/extract_hotupdate.py` 从 UnityFS TextAsset 提取托管 DLL。
2. 用 `research/managed/StaticAssemblyInspect` 的 `index` 模式调用 Mono.Cecil，建立类型和方法索引，按网络关键词查找候选。
3. 用 `ProtocolEvidenceInspect routes` 查看路由属性，找出 `module/command` 对应的处理方法，再按候选 token 导出 IL。
4. 用 `research/disassemble_native.py` 对原生库反汇编，重点看 `JeUdpClient::udpParse`、`AsyncSend`、`msgParse`、`RecvLoop`、`JeMsgQueue::PushMsg`。

以下字段来自固定版本的代码。

- 上行和下行的应用消息格式为 `module(u16 BE) + command(u16 BE) + protobuf-like payload`。
- 3/852 更新场景。实体的字段 1、2、3 分别是运行时编号、次编号和类别，字段 4 是动作列表。
- Position 对应动作 1。三个整数分量按消息里的 `scale`（1000）换算为世界坐标。
- HP 动作为 31。第一值经 `conv.i4` 写入生命值字段，其余值的用途和最大血量仍待确认。
- 玩家消息的字段 1 是实体号，字段 2 是 UInt64 UID，字段 3 是 UTF-8 姓名。登录消息 3/1 还保存本地 UID 和实体号。
- 3/6 更新玩家名单，字段 2 用 packed 或 unpacked UInt32 记录移除的编号。场景消息 3/852 的字段 7 也可删除实体。
- 样本在游戏 UDP 流量中捕获到身份消息。TCP 和独立 RPC 在身份初始化中的作用仍待确认。
- 855 对应阶段变化，861 对应 UInt32→UInt32 字典更新，858 对应语音录制。

这里确认的字段和调用链属于 A 级证据。流量与代码相符时记为 B，基于命名或统计的推断记为 C，尚无结论的记为 D。token、RVA 和反例见[协议说明](PROTOCOL.md)。

## 从 PCAP 提取应用消息

`protocol.py` 按以下顺序处理记录。

1. 读取经典 PCAP，按链路类型提取 IPv4 或 IPv6 的 UDP 数据。遇到 IP 分片时跳过并计数。
2. 保留发往游戏本地 UDP 端口的入站数据包，跳过出站包、控制包、ACK 和重复包。
3. `transport_segments()` 用头校验（`byte0 == (length + flag + seq_bytes) & 0xFF`）和连续序号拆分同一条 UDP 记录里的多条消息。只有一种完整拆法时才拆分，其余情况传递原始记录并计入错误。
4. 首段的头长 10 字节（8 字节公共头加 2 字节），后续分片的头长 8 字节。标志位 `0x20` 表示分片，`0x40` 表示后面还有分片，`0x80` 表示 Zstd 压缩。
5. 从首段开始按序号重组，最多保留 16 条流。每条待重组消息有 15 秒、8 MiB 和 512 段的限制。缺片或乱序时中断并单独计数。
6. Zstd 解压（`libzstd`，限制最大输出）。
7. 读 `module/command`，分派身份或场景消息。

旧版漏姓名的一个原因是同一条 PCAP 记录里有两条连续的 3/6 名单消息。解析器把整个载荷当成一条 Protobuf 消息，遇到第二条消息开头就报错并丢弃记录。v2.2 允许同一条记录返回多条结果，后端的两个读取点也改为逐条处理。

## 身份与坐标

`identity.py` 解析 3/1、3/3、3/6 和 3/2005。

- 3/1 重置名单，并设置本地 UID 和实体号。
- 3/3 和 3/6 更新名单，3/6 还可带上要移除的 ID。
- 只记录带运行时实体号的玩家，姓名按 UTF-8 严格解码。

`server.py` 用 `local_port@peer` 区分传输流，再按 `id1` 给类别为 4 的坐标实体匹配名单。

- 优先比较玩家 UID 和本地 UID 来设置 `is_local`。缺少 UID 时，改用本地实体号。
- 姓名只来自真实名单，不做位置接近、Owner 动作或上行自身坐标推断。
- 3/2005 可能表示当前观察目标。观战时标为“自己”的实体可能和登录账号不同。

## 后端状态与网页显示

后端每 0.12 秒读取一次 PCAP 增量。

- Position 动作生成实体快照和 60 点轨迹。
- 动作 31 更新 HP 原值和独立时间戳。
- 收到 3/852 字段 7 或 3/6 的移除通知时，同时删除实体和 HP。
- 状态在 300 秒后过期。实体和 HP 最多各保留 512 项，名单最多 2048 项。
- 位置日志写到 16 MiB 后停止追加，元数据对应上限为 8 MiB。
- 诊断 JSON 约每 2 秒原子落盘，记录协议号、动作号、缓冲/分片/错误和“是否观测到身份/HP31”。

`app.js` 默认投影到 X/Z 平面。实体 3 秒未更新时变灰，30 秒后隐藏。视图跟随最新的 `is_local=true` 实体，也可以手动选择参考实体。缺少身份或 HP 数据时，页面显示“未观测到”。

## 抓包和端口更新

旧版发现游戏端口后才启动 `tcpdump`，端口列表一变就重启，会留下数秒空窗并产生多个 PCAP。v2.1 改为单次持续抓包。

- 运行 `tcpdump -i any -w capture-0001.pcap udp` 开始采集，再启动后端。
- 每秒用 `ss` 查询游戏 PID 的 UDP 端口并更新解码端口列表。
- 发现新端口后，从有大小和时长限制的缓存里补解析该端口的记录。
- 游戏 PID 变化时，清空实体、身份、HP 和序号状态，按进程开始时间排除旧流量。
- 默认运行 600 秒。目录大小按秒检查，达到约 64 MiB 时也会停止。

原始 PCAP 记录全机 UDP，可能包含其他应用的流量。应用层只解码游戏端口。

## 复现

- 在手机上运行时，先复制完整仓库，在 Ubuntu 中检查依赖并执行 `deploy_android.py --android-local --write`。再到 Android 原生环境检查并启动。也可以用 `--stage` 在电脑上暂存文件，再传到手机。
- 用自己的 PCAP 和 CSV 运行 `tools/replay_pcap.py`，逐条核对坐标和统计结果。
- 用 `research/` 复查静态证据。`restore_inputs.py` 只接受预设哈希的固定输入，提取和反汇编脚本会输出哈希供核对。

命令、依赖和预期输出见[复现指南](REPRODUCE.md)，历史样本结果见[验证记录](VALIDATION.md)。
