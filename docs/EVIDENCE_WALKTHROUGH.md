# UDP 协议分析的证据索引

托管 token 对应 `UpdateScript_500.dll`，原生 VA 对应 `libjelib.so`。输入哈希、提取和回放命令见[实现教程](FROM_ZERO.md)。

## 托管工具

- `StaticAssemblyInspect` 的 `index` 找候选，`types` 列字段和方法，`il` 导出方法体。
- `ProtocolEvidenceInspect` 的 `routes` 列路由，`attrs` 核对属性参数，`mentions` 搜字段和签名。
- `StaticReferenceInspect` 在 `references.json` 中列出引用，附上调用方 IL。分派表还需看注册和委托构造。

## 网络入口和 3/50

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

## 3/852 场景解析

| 层级 | token | 类型/证据点 |
|---|---|---|
| 场景handler | 0x06016A77 | FMPDBDEEKGC::MMMFDMBPCAO(BILKNBOMFCO,Int32)，遍历/删除如何进入业务 |
| 场景parser | 0x06026483 | BILKNBOMFCO，field6反复调用实体parser，field7移除ID |
| 实体parser | 0x06004FBC | EMEOJKBBAAA，field1/2/3标识、field4动作数组 |
| 动作parser | 0x06012856 | FOOBJALACEJ，kind、scale、Int64列表，packed/unpacked |
| 位置消费 | 0x06002E55 | action的values/scale送入Vector3辅助，再进入位置方法 |
| 三值→Vector3 | 0x06021E2E | 依次取array[offset+0/1/2]，scale>0时分别div，否则原浮点 |
| 向量写入变体 | 0x06021E29 | 同类三分量赋值/缩放逻辑 |

`0x06021E2E` 按分量执行 `ldelem.i8 → conv.r4 → ldarg scale → div`，再构造 `UnityEngine.Vector3`。

## 名单和本地身份

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

`HNMOBHFEEON` 的参数按 `command`、`module` 排列。3/1 对应 `(1, 3)`，可用 `attrs` 复核。

## HP

| 目的 | token | 应读到的事实 |
|---|---|---|
| 玩家动作分派 | 0x060038F8 | kind31进入对应生命处理 |
| 玩家HP处理 | 0x06003ACA | values[0]经conv.i4写GPJFBHCPDAB |
| NPCHP处理 | 0x06002DAA | 同样从第一值取得Int32生命原值 |

## 原生 UDP 函数

地址为 ELF VA。脚本按 `PT_LOAD` 转成文件偏移。

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

PLT 调用可用 `readelf` 的重定位和符号表核对。[验证记录](VALIDATION.md)
