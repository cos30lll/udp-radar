# 证据检索与阅读：怎样从 token 走到字段语义

配合 [FROM_ZERO.md](FROM_ZERO.md) 第3、6、8～10章使用。这里是固定输入的检索路线，不附游戏IL/汇编全文或玩家流量。所有token只适用于SHA256为`1ce1e36603c3c481a03a321edc1d08f6ba24f165855021b808effbb90d84a5ec`的UpdateScript_500.dll；原生VA只适用于本文固定libjelib。

## 1. 三种托管工具分别解决什么

| 工具/模式 | 输入 | 输出 | 应检查的内容 |
|---|---|---|---|
| StaticAssemblyInspect index | 程序集、输出目录 | 类型索引、网络候选、外部调用 | 候选来源，不把关键词命中当业务结论 |
| StaticAssemblyInspect types | 程序集、目录、类型全名或0x02类型token | selected-types.json | 字段类型、方法token、是否有方法体 |
| StaticAssemblyInspect il | 程序集、目录、0x06方法token或完整方法名 | 每方法IL文本 | 真实load/call/store/branch与参数流 |
| ProtocolEvidenceInspect routes | 程序集、输出文件、command列表 | module3路由 | command/module参数顺序、handler参数类型 |
| ProtocolEvidenceInspect attrs | 程序集、输出文件、token | 自定义attribute | 路由属性实际构造参数 |
| ProtocolEvidenceInspect mentions | 程序集、输出文件、类型名片段 | 字段/签名引用 | 缩小检索，尚不是调用链 |
| StaticReferenceInspect | 程序集、输出目录、成员token | references.json及调用方IL | 指令operand确实引用目标，而非仅字节相似 |

空输出不算通过：types的selected、il的methods、routes的records、references的hits需要核对。某些消息在分派表而不是普通直接call出现，也要读注册/委托构造代码。所有工具在电脑.NET 8 SDK的标准构建仍需真实执行，本包不以表格存在冒充构建成功。

## 2. 网络入口与早期批量移动分支

| 问题 | token/类型 | 阅读目标 |
|---|---|---|
| 传输模式选择 | 0x06012A84；DHPODGOMOID | 模式枚举如何选择实现，不能以枚举存在推断本局模式 |
| 应用头与批量移动分派 | 0x0601F599；NLJGAHGAAEH | 何处读取module/command，何处进入body解析 |
| 原生包装入口 | ExternDllManager、NLJGAHGAAEH | P/Invoke module/entrypoint，libUdpConnect/Send/Recv |
| 3/50批量parser | 0x0600547B；MNEHOHLMOCB | field1重复PMEEGHODBLL；解析计数不是另一个wire字段 |
| 3/50单项parser | 0x0601F901；PMEEGHODBLL | field1 lookup_id；field2/3两个向量；4/5/6其他值 |
| 向量parser | 0x0601861A；DHFLOFIEDAF | wire5标签但调用varint/ZigZag；除100 |
| 向量writer | 0x06018617 | 量化与写出用于交叉验证，不替代parser |
| varint/ZigZag helper | 0x0601EE65、0x0601EE70 | 整数位处理，而非标准float/fixed32 |
| 查找对象与传向量 | 0x06016A68 | lookup_id进入字典，不是UID |
| 位置/外推消费 | 0x0601DD55、0x0601DD41 | 第一向量进入位置；第二乘deltaTime后用于外推 |
| 向量轴序/写入 | 0x06021E2D、0x0601EE66 | Vector3构造次序与编码对应 |

这条3/50支线有静态语义，主真实样本实际走3/852，因此不能将其当作最终雷达坐标编码。保留历史分支是解释如何排除错误主线，不是扩充已验收消息范围。

## 3. 从3/852路由到场景、实体、动作

| 层级 | token | 类型/证据点 |
|---|---|---|
| 场景handler | 0x06016A77 | FMPDBDEEKGC::MMMFDMBPCAO(BILKNBOMFCO,Int32)，遍历/删除如何进入业务 |
| 场景parser | 0x06026483 | BILKNBOMFCO，field6反复调用实体parser，field7移除ID |
| 实体parser | 0x06004FBC | EMEOJKBBAAA，field1/2/3标识、field4动作数组 |
| 动作parser | 0x06012856 | FOOBJALACEJ，kind、scale、Int64列表，packed/unpacked |
| 位置消费 | 0x06002E55 | action的values/scale送入Vector3辅助，再进入位置方法 |
| 三值→Vector3 | 0x06021E2E | 依次取array[offset+0/1/2]，scale>0时分别div，否则原浮点 |
| 向量写入变体 | 0x06021E29 | 同类三分量赋值/缩放逻辑 |

以0x06021E2E为例，需实际看到`ldelem.i8 → conv.r4 → ldarg scale → div`重复三次，再`newobj UnityEngine.Vector3`，而不是只读签名。再看0x06002E55从FOOBJALACEJ取values和scale，证明输入来自该动作。独立真实PCAP原值/CSV对照提供第二层证据。

## 4. 名单字段、字典键与本地身份

| 目的 | token | 应证明的关系 |
|---|---|---|
| 姓名UI入口 | 0x0600EE78 | CzrPlayerNameUI::SetInitData的字符串、UID、实体号来源 |
| 姓名getter消费 | 0x060038F2 | 角色显示链读取哪个getter |
| 角色构造 | 0x06003CEB、0x0602392C | 名单数据进入角色UID/姓名字段，而非按附近实体猜 |
| 玩家协议parser | 0x0601CD83 | MNKGAOHNBGO field1 UInt32实体号/JIEGLOEJFBC，field2 UInt64 UID/JJEPKIGHOKG，field3字符串/MEFMBKGEBKK |
| 场景类别分派 | 0x0600654A | 类别4，从EMEOJKBBAAA::KLCGKFOJHMD查玩家字典 |
| 名单连接业务 | 0x0600651A | MNKGAOHNBGO::JIEGLOEJFBC查同一命名空间/字典 |
| 登录parser | 0x060110F7 | EEMEFKNFFEB field2本地UID、field3本地实体号、field5名单容器 |
| 名单parser | 0x0601B524、0x0601BF43 | 列表/移除ID结构，对照具体消息类和packed分支 |
| 3/1 handler | 0x06016ACF | 接收初始化并写本地状态 |
| 3/3 handler | 0x06016B3B | 名单更新的路由和数据流 |
| 3/6 handler | 0x06016A5A | 增删列表，不是任意文本通知 |
| 3/2005 handler | 0x060183A3 | 当前观察目标语义，不等同最初登录账号 |

路由属性HNMOBHFEEON先command后module，固定3/1属性参数即1、3。导出routes后用attrs复核已知handler，避免整个协议号表颠倒。

字典连接判定必须同时解释两边键来源。只见“有一个UInt32”不足以认为它是实体ID，更不能把实体field2硬当账号UID。

## 5. HP原值的证据终点

| 目的 | token | 应读到的事实 |
|---|---|---|
| 玩家动作分派 | 0x060038F8 | kind31进入对应生命处理 |
| 玩家HP处理 | 0x06003ACA | values[0]经conv.i4写GPJFBHCPDAB |
| NPCHP处理 | 0x06002DAA | 同样从第一值取得Int32生命原值 |

额外values、写入另一成员、名字像MaxHP都不能单独证明最大血量；本版本只显示首值原值，不计算百分比。每次报告实际HP变化还需用户现场验证，IL说明语义不代替现场表现。

## 6. 原生传输证据怎样重新生成

libjelib固定SHA256：a6e64e050d3ac896bb5310e3bcfc80f8d724188b6db1955e216bb868641526f6。

```bash
python3 research/disassemble_native.py --so /path/to/libjelib.so --output work/native
```

| 函数/范围 | 用途 | 阅读重点 |
|---|---|---|
| RecvLoop，固定函数VA0x5a49c | socket接收至解析 | recvfrom后长度和调用参数 |
| udpParse，固定函数VA0x5b9e8 | 头/握手/分片/解压 | 不同flag分支与偏移，不统一固定跳头 |
| AsyncSend局部0x5ab78..0x5abbc | 校验字节生成 | length+flag+seq低字节+seq高字节，模256 |
| udpParse局部0x5bf04..0x5bf74 | 分片有效载荷拼接 | 首段起点10、后续8，完整后送处理 |
| msgParse/PushMsg/GetMsg | 应用队列边界 | 何时开始托管应用头，内存复制长度 |
| GetMsg，固定函数VA0x5c2a0 | 原生到托管取消息 | 消息长度与拷贝边界 |

readelf动态符号可以找函数；外部调用可能经PLT，需读目标对应Zstd::Decompress等再解释用途。本辅助工具主要导出函数，不替读者自动解释所有PLT关系；可用readelf/反汇编器继续查看relocation与符号。

这些是ELF VA，不是文件偏移，也不是运行进程绝对地址。脚本先按PT_LOAD换算；其他版本/架构必须重做，不直接套常量。

## 7. 把证据记录为别人可以核对的材料

每条发现至少记录：输入SHA256、版本、token/VA、完整方法名、关键读取/写入语句位置、调用者与消费者、观察到的真实消息号、验证等级。无需把游戏代码全文塞进开源包，也不靠截图替代结构证据。

建议私人研究表：`claim → parser → field → consumer → conversion → PCAP event → status`。公开时只保留方法定位和脱敏统计，删去玩家UID/姓名、端点、原消息字节和原始流量。

不要把历史“已导出IL”升级成新环境构建已通过，也不要把“同一解析器CSV回读一致”升级成独立游戏坐标真值。详见VALIDATION与FROM_ZERO。


## 8. 上下行外壳的流量补证边界

下行首片10/后续8与序号2是成品主线；已有真实主业务会话上行应用起点14、序号6，不能对称套用。新的pcap_lab先按方向区分，再对照历史分析脚本和实际3/851/852分布。上行分片/合包恢复未扩展，明确计为未支持；完整3/851业务schema仍未确认。

这一差异在新增工具第一次真实样本核对时暴露：下行852数量正确，上行module/command离散异常。修复的是研究辅助工具，不修改原成品的入站解码逻辑，不把曾失败的一次核对记为通过。
