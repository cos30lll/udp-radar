# UDP 协议分析的证据索引

托管 token 对应 `UpdateScript_500.dll`，SHA-256 为 `1ce1e36603c3c481a03a321edc1d08f6ba24f165855021b808effbb90d84a5ec`。原生 VA 对应第 6 节列出的 `libjelib.so`。完整操作见实现教程第 3、6、8～10 节。[实现教程](FROM_ZERO.md)

## 1. 托管程序集检查工具

| 工具/模式 | 输入 | 输出 | 应检查的内容 |
|---|---|---|---|
| StaticAssemblyInspect index | 程序集、输出目录 | 类型索引、网络候选、外部调用 | 关键词命中位置及外部调用 |
| StaticAssemblyInspect types | 程序集、目录、类型全名或0x02类型token | selected-types.json | 字段类型、方法token、是否有方法体 |
| StaticAssemblyInspect il | 程序集、目录、0x06方法token或完整方法名 | 每方法IL文本 | 真实load/call/store/branch与参数流 |
| ProtocolEvidenceInspect routes | 程序集、输出文件、command列表 | module3路由 | command/module参数顺序、handler参数类型 |
| ProtocolEvidenceInspect attrs | 程序集、输出文件、token | 自定义attribute | 路由属性实际构造参数 |
| ProtocolEvidenceInspect mentions | 程序集、输出文件、类型名片段 | 字段/签名引用 | 按字段和签名缩小搜索范围 |
| StaticReferenceInspect | 程序集、输出目录、成员token | references.json及调用方IL | IL 指令的操作数是否引用目标 |

导出后检查 `types` 的 `selected`、`il` 的 `methods`、`routes` 的 `records` 和引用报告的 `hits`。消息可能由分派表或委托调用，沿注册和委托构造代码也能找到入口。三个工具的 .NET 8 SDK 构建有单独的验证记录。

## 2. 网络入口与早期批量移动分支

| 问题 | token/类型 | 阅读目标 |
|---|---|---|
| 传输模式选择 | 0x06012A84；DHPODGOMOID | 分支实际选择了哪个传输实现 |
| 应用头与批量移动分派 | 0x0601F599；NLJGAHGAAEH | 何处读取module/command，何处进入body解析 |
| 原生包装入口 | ExternDllManager、NLJGAHGAAEH | P/Invoke module/entrypoint，libUdpConnect/Send/Recv |
| 3/50批量parser | 0x0600547B；MNEHOHLMOCB | field 1 重复读取 PMEEGHODBLL，计数由解析器维护 |
| 3/50单项parser | 0x0601F901；PMEEGHODBLL | field1 lookup_id；field2/3两个向量；4/5/6其他值 |
| 向量parser | 0x0601861A；DHFLOFIEDAF | wire5标签但调用varint/ZigZag；除100 |
| 向量writer | 0x06018617 | 与解析器对照量化和写出方式 |
| varint/ZigZag helper | 0x0601EE65、0x0601EE70 | varint 读取及 ZigZag 位运算 |
| 查找对象与传向量 | 0x06016A68 | `lookup_id` 用作字典键 |
| 位置/外推消费 | 0x0601DD55、0x0601DD41 | 第一向量进入位置；第二乘deltaTime后用于外推 |
| 向量轴序/写入 | 0x06021E2D、0x0601EE66 | Vector3构造次序与编码对应 |

3/50 的结构来自静态分析。实测主会话采用 3/852，雷达的坐标解码以第 3 节的消息结构为准。

## 3. 3/852 的场景、实体和动作

| 层级 | token | 类型/证据点 |
|---|---|---|
| 场景handler | 0x06016A77 | FMPDBDEEKGC::MMMFDMBPCAO(BILKNBOMFCO,Int32)，遍历/删除如何进入业务 |
| 场景parser | 0x06026483 | BILKNBOMFCO，field6反复调用实体parser，field7移除ID |
| 实体parser | 0x06004FBC | EMEOJKBBAAA，field1/2/3标识、field4动作数组 |
| 动作parser | 0x06012856 | FOOBJALACEJ，kind、scale、Int64列表，packed/unpacked |
| 位置消费 | 0x06002E55 | action的values/scale送入Vector3辅助，再进入位置方法 |
| 三值→Vector3 | 0x06021E2E | 依次取array[offset+0/1/2]，scale>0时分别div，否则原浮点 |
| 向量写入变体 | 0x06021E29 | 同类三分量赋值/缩放逻辑 |

`0x06021E2E` 先执行三遍 `ldelem.i8 → conv.r4 → ldarg scale → div`，再调用 `newobj UnityEngine.Vector3`。`0x06002E55` 从 `FOOBJALACEJ` 取出 `values` 和 `scale` 作为输入。另用真实 PCAP 的原值和 CSV 核对换算结果。

## 4. 名单字段、字典键与本地身份

| 目的 | token | 应证明的关系 |
|---|---|---|
| 姓名UI入口 | 0x0600EE78 | CzrPlayerNameUI::SetInitData的字符串、UID、实体号来源 |
| 姓名getter消费 | 0x060038F2 | 角色显示链读取哪个getter |
| 角色构造 | 0x06003CEB、0x0602392C | 名单里的 UID 和姓名怎样写入角色字段 |
| 玩家协议parser | 0x0601CD83 | MNKGAOHNBGO field1 UInt32实体号/JIEGLOEJFBC，field2 UInt64 UID/JJEPKIGHOKG，field3字符串/MEFMBKGEBKK |
| 场景类别分派 | 0x0600654A | 类别4，从EMEOJKBBAAA::KLCGKFOJHMD查玩家字典 |
| 名单连接业务 | 0x0600651A | MNKGAOHNBGO::JIEGLOEJFBC查同一命名空间/字典 |
| 登录parser | 0x060110F7 | EEMEFKNFFEB field2本地UID、field3本地实体号、field5名单容器 |
| 名单parser | 0x0601B524、0x0601BF43 | 列表/移除ID结构，对照具体消息类和packed分支 |
| 3/1 handler | 0x06016ACF | 接收初始化并写本地状态 |
| 3/3 handler | 0x06016B3B | 名单更新的路由和数据流 |
| 3/6 handler | 0x06016A5A | 对名单执行新增和移除 |
| 3/2005 handler | 0x060183A3 | 更新当前观察目标的 UID |

路由属性 `HNMOBHFEEON` 先收 `command`，再收 `module`。例如 3/1 对应的参数依次是 1、3。导出 `routes` 后，用 `attrs` 复核已知 handler 的参数顺序。

判断两个字典能否关联，要追清两边的键从哪里来。这里用的是类别 4 的 `id1` 和名单里的运行时实体号。

## 5. HP 原值

| 目的 | token | 应读到的事实 |
|---|---|---|
| 玩家动作分派 | 0x060038F8 | kind31进入对应生命处理 |
| 玩家HP处理 | 0x06003ACA | values[0]经conv.i4写GPJFBHCPDAB |
| NPCHP处理 | 0x06002DAA | 同样从第一值取得Int32生命原值 |

这一调用链能确认首值是 `Int32` HP 原值。其余 `values` 和其他成员的含义还未确认，因此页面只显示原值。HP 变化要在实际场景中观察。

## 6. 原生 UDP 函数

`libjelib.so` 的 SHA-256 为 `a6e64e050d3ac896bb5310e3bcfc80f8d724188b6db1955e216bb868641526f6`。

```bash
python3 research/disassemble_native.py --so /path/to/libjelib.so --output work/native
```

| 函数/范围 | 用途 | 阅读重点 |
|---|---|---|
| RecvLoop，固定函数VA0x5a49c | socket接收至解析 | recvfrom后长度和调用参数 |
| udpParse，固定函数VA0x5b9e8 | 头/握手/分片/解压 | 各 flag 分支读取的字段和偏移 |
| AsyncSend局部0x5ab78..0x5abbc | 校验字节生成 | length+flag+seq低字节+seq高字节，模256 |
| udpParse局部0x5bf04..0x5bf74 | 分片有效载荷拼接 | 首段起点10、后续8，完整后送处理 |
| msgParse/PushMsg/GetMsg | 应用队列边界 | 何时开始托管应用头，内存复制长度 |
| GetMsg，固定函数VA0x5c2a0 | 原生到托管取消息 | 消息长度与拷贝边界 |

用 `readelf` 的动态符号找函数。外部调用经过 PLT 时，再查看重定位和符号，确认目标是否为 `Zstd::Decompress` 等函数。

表中地址均为 ELF VA，脚本按 `PT_LOAD` 将其换算为文件偏移。换版本或架构后需要重新定位。

## 7. 记录分析证据

记录输入的 SHA-256 和版本、token 或 VA、完整方法名、读写字段的位置、调用方和使用方、实测消息号及验证范围。

私人研究表可按 `claim → parser → field → consumer → conversion → PCAP event → status` 记录。公开材料保留方法位置和脱敏统计，玩家 UID、姓名、端点、消息原始字节和流量留在本地。

历史 IL 导出、当前 SDK 构建、CSV 核对和游戏内验证各有单独记录。[验证记录](VALIDATION.md)


## 8. 上下行传输头的样本验证

成品按下行首片偏移 10、后续片偏移 8、序号偏移 2 解析。真实主会话中，上行应用数据从偏移 14 开始，序号从偏移 6 开始。`pcap_lab.py` 按方向使用这些偏移，并用历史分析脚本和实测的 3/851、3/852 分布核对。上行分片和合包计为未支持，3/851 的完整消息结构仍待确认。

辅助工具第一次用真实样本核对时，下行 852 的数量正确，上行却出现大量分散的 `module/command`。重新区分传输头后，上行结果才与样本吻合。成品的入站解码沿用原实现。
