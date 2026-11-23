# 从零实现 UDP 雷达

从热更新程序集和原生 UDP 库找到消息解析器，再用测试 PCAP 核对坐标、姓名和 HP。文中的哈希、偏移和消息号对应固定版本。已有成品可直接看[部署指南](REPRODUCE.md)。

## 1. 工作目录和依赖

电脑可用 Linux 或 WSL Ubuntu，请从仓库根目录执行命令。研究环境需要 Python 3.9+、libzstd、git、unzip、binutils 和 .NET 8 SDK。

```bash
python3 --version
python3 tools/check_environment.py
dotnet --list-sdks
readelf --version
c++filt --version
python3 -m pip install -r requirements-research.txt
```

把自己的 APK、热更新、PCAP 和端口记录放进 `input/`，中间结果写入 `work/`。安装依赖和恢复 NuGet 包时可能联网。

## 2. 从 APK 提取热更新程序集

```bash
unzip -l input/game.apk
unzip input/game.apk -d work/apk
```

样本使用 Unity 2022.3.62f3。APK 同时有 ARM32 和 AArch64 库，下文使用 AArch64 的 `libjelib.so`。热更新文件名以 `updatescript` 开头。

```bash
find work/apk/assets/android/data/code -maxdepth 1 -type f -iname 'updatescript*'
```

找到与下表哈希匹配的 bundle，把实际路径传给 `--bundle`。

```bash
python3 research/extract_hotupdate.py --bundle input/update.bundle --output work/hotupdate
```

工具从 UnityFS `TextAsset` 的 `m_Script` 里提取带 MZ 头的候选文件，并写入 `asset-manifest.json`。用 Mono.Cecil 确认 DLL 里有可读方法体。

| 输入 | SHA256 |
|---|---|
| UpdateScript_500.dll | 1ce1e36603c3c481a03a321edc1d08f6ba24f165855021b808effbb90d84a5ec |
| libjelib.so | a6e64e050d3ac896bb5310e3bcfc80f8d724188b6db1955e216bb868641526f6 |
| 热更新 bundle | 63a76b500939a3b3e99233975abee294e31586cd6c33aaabd090193d3239eb11 |

### 可选的 metadata 和 IL2CPP 恢复

需要补查静态类型或 IL2CPP 地址时，可用以下脚本。脚本校验预设的输入哈希，IL2CPP 分支还要读取上一步的 metadata 报告。

```bash
python3 research/restore_inputs.py metadata --input work/apk/assets/bin/Data/Managed/Metadata/global-metadata.dat --output work/metadata-restored
python3 research/restore_inputs.py il2cpp --input work/apk/lib/arm64-v8a/libil2cpp.so --metadata-report work/metadata-restored/restore-report.json --output work/il2cpp-restored
```

恢复结果供静态分析。早期导出的 `dump.cs`、方法地址索引和 DummyDll 可用，部分附属输出和原生代码区仍不完整。

## 3. 从混淆程序集定位网络入口

```bash
dotnet build research/managed/StaticAssemblyInspect -c Release
dotnet build research/managed/ProtocolEvidenceInspect -c Release
dotnet build research/managed/StaticReferenceInspect -c Release
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- index work/hotupdate/UpdateScript_500.dll work/index
```

在 `candidate-index.json`、`type-index.tsv` 和 `network-crypto-calls.json` 里找 UDP 相关类型。

```bash
grep -Ein 'udp|socket|libUdp|ExternDll|DHPODGOMOID|NLJGAHGAAEH' work/index/type-index.tsv work/index/candidate-index.json
```

`DHPODGOMOID` 选择传输模式，`NLJGAHGAAEH` 经 `ExternDllManager` 调用 `libUdpConnect`、`libUdpSend` 和 `libUdpRecv`。

```bash
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- types work/hotupdate/UpdateScript_500.dll work/net-types DHPODGOMOID NLJGAHGAAEH ExternDllManager
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/net-il 0x06012A84 0x0601F599
```

跟着 P/Invoke 入口查应用头的读取位置和 handler 分派。

```bash
dotnet run --project research/managed/StaticReferenceInspect -c Release -- work/hotupdate/UpdateScript_500.dll work/recv-callers 0x0601F599
```

从 `references.json` 找调用位置，结合实际读写指令区分解析器、写入器和业务方法。

## 4. 手动采集 PCAP 和端口记录

在自己的 Android 设备上打开原生 Root shell，进场前开始采集。名单和本地 UID 可能只在初始化时收到，游戏端口要用同期的 PID 和 `ss` 记录确认。

```sh
SESSION='/storage/emulated/0/Download/超自然行动/日志/manual-session'
mkdir -p "$SESSION/tmp"
export TMPDIR="$SESSION/tmp"
pidof com.pi.czrxdfirst > "$SESSION/game-pids.txt"
ss -H -u -a -n -p -e > "$SESSION/sockets-before.txt"
/system/bin/tcpdump -p -i any -nn -s 0 -U -B 4096 -w "$SESSION/round.pcap" udp
```

会话结束后按 Ctrl+C，确认 `tcpdump` 退出，再保存一份场景内的端口表。通过 USB 或 MTP 把两份端口记录和 PCAP 复制到 `input/`。PCAP 含全机 UDP，留在本地。

## 5. 从 PCAP 读取 UDP

经典 PCAP 用 24 字节全局头和每条 16 字节记录头定位帧。magic 表示字节序和时间单位，尾读遇到只写了一半的记录时等下一轮。Android 的 `-i any` 常见 Linux cooked 113（16 字节头）和 276（20 字节头）。解析入口是 `PcapTail.poll` 和 `udp`。

IPv4 用 IHL、总长度和协议号定位 UDP，IPv6 目前只处理直接 UDP。按已确认的本地端口区分方向，入站看 `dport`，出站看 `sport`，两端同时命中时方向有歧义。IP 分片、非 UDP 和损坏记录分别计数。

## 6. UDP 传输头和应用载荷

```bash
python3 research/disassemble_native.py --so work/apk/lib/arm64-v8a/libjelib.so --output work/native
```

沿 `RecvLoop`、`udpParse`、`msgParse` 查看头字段、重组、解压和入队，再用 `AsyncSend` 核对发送端的写入。压缩分支调用 `Zstd::Decompress`。下行校验使用单片长度、flag 及序号的两个字节。[证据索引](EVIDENCE_WALKTHROUGH.md)

```python
valid = data[0] == ((len(data) + data[1] + data[2] + data[3]) & 0xff)
seq = int.from_bytes(data[2:4], 'little')
```

下行首片载荷从偏移 10 开始，后续片从偏移 8 开始，序号从偏移 2 开始。实测上行载荷偏移为 14，序号在字节 6～7，外层仍校验字节 1～3。上行分片和合包尚未支持。

`transport_segments` 先校验整条记录，失败时用完整头、单片校验和连续序号找切点。长度校验只有模 256 的结果，候选长度相隔 256 字节。整条载荷只有一种完整拆法时才拆分。

`0x20` 标记后续片，`0x40` 表示后面还有片，`0x80` 表示 Zstd 压缩。从首片按序拼齐后才解压。缺片、乱序和过期分别计数，缓存上限见[架构说明](ARCHITECTURE.md)。

## 7. 统计实际出现的应用消息

应用头由两个大端 `UInt16` 组成。

```python
module, command = struct.unpack_from('!HH', app)
body = app[4:]
```

命令里的 `45283` 是历史端口，下文命令都要换成自己确认的端口。辅助端口可能使用不同的传输头。

```bash
python3 research/pcap_lab.py survey input/round.pcap --ports 45283 --direction both --summary work/study/survey.json
```

`survey` 在 `commands` 中列出方向、消息号和应用消息数。退出码 3 时查看 `decode_errors`、分片计数和 `pending`。

最早从静态代码找到的是 3/50 BatchMove，向量采用自定义 wire 5、varint、ZigZag 和除 100。实测主会话出现的是下行 3/852 和上行 3/851，位置要从 852 的动作数组解析。早期工具仍可读取单独提取的 3/50 应用消息。

```bash
python3 research/legacy_move50.py --workspace . --kind app --input work/study/move50.app --output work/study/move50-decoded.json
```

## 8. 3/852 的路由和消息结构

```bash
dotnet run --project research/managed/ProtocolEvidenceInspect -c Release -- routes work/hotupdate/UpdateScript_500.dll work/routes.json 1 3 6 50 851 852 2005
```

路由属性 `HNMOBHFEEON` 的参数顺序为 `command`、`module`。3/852 路由到 `FMPDBDEEKGC::MMMFDMBPCAO`（`0x06016A77`），参数类型为 `BILKNBOMFCO`。

```bash
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- types work/hotupdate/UpdateScript_500.dll work/scene-types BILKNBOMFCO EMEOJKBBAAA FOOBJALACEJ
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/scene-il 0x06016A77 0x06026483 0x06004FBC 0x06012856
```

| 层级 | 字段 |
|---|---|
| 场景 `BILKNBOMFCO` | 4、5 为帧相关值，6 为重复实体，7 为移除编号 |
| 实体 `EMEOJKBBAAA` | 1、2、3 分别为 `id1`、`id2` 和类别，4 为动作列表 |
| 动作 `FOOBJALACEJ` | 1 为 kind，2 为 scale，3 为 Int64 列表（packed 或 unpacked），4 保留 |

```bash
python3 research/pcap_lab.py extract input/round.pcap --ports 45283 --direction in --message 3/852 --output work/study/scene.app
python3 research/pcap_lab.py fields work/study/scene.app --output work/study/scene-fields.json
python3 research/pcap_lab.py fields work/study/scene.app --path 6:1 --output work/study/entity-fields.json
python3 research/pcap_lab.py fields work/study/scene.app --path 6:1/4:1 --output work/study/action-fields.json
```

`fields` 从偏移 4 开始。`6:1/4:1` 是第一个实体里的第一个动作，索引从 1 开始。当前帧没有对应数据时，用 `--occurrence N` 另取一帧。标准定长 wire 1 和 5 用 `--standard-fixed` 查看，3/50 的自定义 wire 5 由上一节的脚本读取。

## 9. 确认坐标

`0x06002E55` 把动作的值和 `scale` 交给 `0x06021E2E`，构造 `Vector3` 后写入位置。只为恰好有三个值的 kind 1 动作生成坐标。

```bash
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/position-il 0x06002E55 0x06021E2E 0x06021E29
dotnet run --project research/managed/StaticReferenceInspect -c Release -- work/hotupdate/UpdateScript_500.dll work/position-callers 0x06021E2E
```

```python
signed = unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned
xyz = [raw / scale if scale > 0 else float(raw) for raw in values]
```

回放可保存原始整数、`scale`、包号、序号及换算结果。

```bash
python3 tools/replay_pcap.py input/round.pcap --ports 45063,45283 --summary work/study/replay-summary.json --events work/study/events.jsonl
```

有基线 CSV 时加 `--expected-csv`。历史样本 8184 包中解出的 7101 条位置与 CSV 逐条吻合。

## 10. 姓名、UID、本地身份和 HP

### 名单和本地身份

从 `CzrPlayerNameUI::SetInitData` 追到 `MNKGAOHNBGO`。其解析器 `0x0601CD83` 依次读取 `UInt32` 实体号、`UInt64` UID 和 UTF-8 姓名。

```bash
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/name-il 0x0600EE78 0x060038F2 0x06003CEB 0x0602392C 0x0601CD83
dotnet run --project research/managed/StaticReferenceInspect -c Release -- work/hotupdate/UpdateScript_500.dll work/name-callers 0x0600EE78
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/identity-link-il 0x0600654A 0x0600651A
```

两处查字典的代码都以类别 4 的 `id1` 对应名单里的运行时实体号。UID 以字符串交给浏览器，保留 64 位精度。

| 消息 | 固定已解析内容 | 状态动作 |
|---|---|---|
| 3/1 登录/初始化 | field2本地UID、field3本地实体号、field5名单容器 | 清旧流身份/实体并建立本地状态 |
| 3/3 名单 | field1玩家列表 | 更新名单 |
| 3/6 名单增删 | field1玩家列表、field2删除ID packed/unpacked | 增量更新并删对应实体/HP |
| 3/2005 当前观察目标 | field 1，本地观察 UID | 记录当前观察目标，登录 UID 单独保留 |

同一流内优先用非零 UID 识别本地玩家，也可匹配本地实体号。上行 3/851 的完整结构仍待确认。

### HP

```bash
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/hp-il 0x060038F8 0x06003ACA 0x06002DAA
```

玩家动作 31 由 `0x06003ACA` 处理，首值经 `conv.i4` 写入生命值字段。NPC 同样取首值。

```python
hp = ((values[0] + (1 << 31)) % (1 << 32)) - (1 << 31)
```

HP 和位置可能先后到达，后端单独保存 HP 原值和时间戳。

## 11. 接入后端和网页

实时读取和端口确认后的补解析都消费 `feed_many` 返回的全部事件。

```python
for timestamp, packet, link, frame in reader.poll():
    for event in decoder.feed_many(timestamp, packet, link, frame):
        state.apply(event)
```

按 `local_port@peer` 区分流，再加 `category/id1/id2` 组成实体键。身份和场景分别检查序号，16 位回绕用 `(new-old)&65535`，超过 32767 当作旧序号。游戏进程换代以及收到 3/1 时清理相关状态，旧进程的缓存用开始时间过滤。

Android 先启动持续抓包，再运行 proot 后端。`ss` 每秒刷新端口归属，端口确认后补解析缓存里的记录，避免重启抓包时漏掉进场名单。进程、状态和日志的细节见[架构说明](ARCHITECTURE.md)。

网页从本地 `/api/state` 读取快照，以参考实体或本地实体为中心绘制 X/Z 平面。`span` 是可见世界宽度，`sign` 默认为 `-1`。

```text
pixels_per_unit = W / span
screen_x = W/2 + (world_x - center_x) * pixels_per_unit
screen_y = H/2 + sign * (world_z - center_z) * pixels_per_unit
```

## 12. 排查缺失姓名

历史样本第 115 条 PCAP 记录的 156 字节 UDP 载荷里有两条 3/6 名单，序号为 15、16。旧版把两条当成同一条 Protobuf 消息，误读第二条传输头时出现 `zero identity field`。按连续序号拆包并消费所有事件后读出了 4 个名单条目。第 97、98 条记录是一组顺序分片，补齐后坐标由 4363 条增至 4429 条。

遇到同类问题，先看 `capture.json` 的端口，再查 `identity_messages`、`roster_players` 和 `decode_errors`。收到名单但点上没有名字时，核对流、类别、`id1` 和重置顺序。HP 缺失时先查 `hp_actions` 里有没有动作 31。[验证记录](VALIDATION.md)

## 13. 发布

发布前检查分发目录和发布清单。原始样本、游戏文件和会话日志留在本地。[发布清单](PUBLISH_CHECKLIST.md)

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```
