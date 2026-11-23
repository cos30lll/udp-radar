# 架构与实现细节

## 进程与数据流

- Android `runner.sh`：单次 `tcpdump` + proot Ubuntu 里的 `server.py`；每秒 `ss` 更新游戏 PID/端口；只更新解码归属，不重启抓包。
- `server.py`：HTTP 只监听 `127.0.0.1`，用 Host 校验限制回环；轮询 PCAP 增量。
- `protocol.py`：无 socket，只读 PCAP；`Decoder.feed_many` 返回一个记录内的所有应用结果。
- `identity.py`：纯解析，不持有全局状态。
- `app.js`：每 400 ms 拉取 `/api/state`，canvas 绘图；不连接外网。

## 状态隔离

- 传输流键：`local_port@peer`。不同服务器/端口不共享身份或顺序号。
- 游戏 PID 变化：清空实体、HP、身份、顺序、分片、去重集合，并用进程开始时间排除旧流量。
- 顺序键按 `kind + event_type` 分开，身份通知与场景更新不用同一序号比较。
- 端口新增：把有界缓存中命中新端口的记录补解析；只接受当前游戏开始时间之后的记录。

## 资源上限

| 项目 | 上限 |
|---|---|
| 位置日志 | 16 MiB（追加停止） |
| 元数据 | 8 MiB |
| 短期待归属缓存 | 15 秒 / 8 MiB / 8,192 条 |
| 传输分片 | 15 秒 / 8 MiB / 512 段 / 16 流 |
| 实体 | 512；300 秒过期 |
| HP | 512；300 秒过期 |
| 名单 | 2,048 |
| 会话 | 默认 600 秒；目录约 64 MiB 轮询停止 |

## 失败模式

- 端口识别失败：`capture.json.ports` 为空，页面提示等待识别；查 `sockets.latest.txt` 和 `ss` 权限。
- 后端未就绪：`server-ready.json` 未生成，看 `server.log`；常见是 proot/Ubuntu Python 路径缺失。
- 应用解码错误：`diagnostics.json.decoder_last_errors` / `stats.decode_errors`；不要把错误当作已解析。
- 未支持分片：`unsupported_ip_fragments` 等单独计数；缺片不重建。
- 进程退出：`capture-exits.txt`、`end-reason.txt`；tcpdump 异常会停止会话而不是假装继续。
- 网页连不上：只允许 127.0.0.1/localhost 对应端口；用 `curl http://127.0.0.1:8765/api/state` 可做本地只读检查。

## 为什么不用“直接读游戏内存/注入”

项目目标是**被动网络解析**：避免注入、避免改写游戏状态、避免服务端伪造。代价是看不到网络里没有的东西（例如未发送给本机的其他玩家数据、服务端不下发的最大血量/地图）。任何增强都不应把推断写成已确认事实。
