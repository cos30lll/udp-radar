# 架构

| 文件 | 职责 |
| --- | --- |
| `runner.sh` | 在 Android 上运行 `tcpdump` 和 `ss`，通过 proot Ubuntu 启动后端 |
| `protocol.py` | 读取 PCAP，将 UDP 载荷解析为应用消息 |
| `identity.py` | 解析名单和身份消息，状态由后端保存 |
| `server.py` | 每 0.12 秒轮询 PCAP，把实体状态放在本机 HTTP 接口上 |
| `app.js` | 每 400 ms 请求 `/api/state`，用 Canvas 绘制 |

后端监听 `127.0.0.1`，Host 校验只接受带当前端口的 `127.0.0.1` 或 `localhost`。传输流按 `local_port@peer` 隔离，序号按 `kind + event_type` 比较。游戏 PID 变更时清空实体、HP、身份、序号、分片和去重状态，再按新进程的开始时间过滤旧记录。

## 资源上限

| 项目 | 上限 |
| --- | --- |
| 位置日志 / 元数据 | 16 MiB / 8 MiB，超出后停止追加 |
| 待确认端口的缓存 | 15 秒、8 MiB 或 8,192 条 |
| 传输分片 | 15 秒、8 MiB、512 段，最多 16 条流 |
| 实体和 HP | 各 512 项，300 秒过期 |
| 名单 | 2,048 项 |
| 会话 | 默认 600 秒，或目录大小轮询到约 64 MiB |

## 排查

| 现象 | 查看 |
| --- | --- |
| 页面一直在识别端口 | `capture.json` 里的 `ports`、`sockets.latest.txt`、`ss` 权限 |
| 没有 `server-ready.json` | `server.log` 里的 proot 或 Python 启动日志 |
| 应用解码失败 | `diagnostics.json` 里的 `decoder_last_errors`、`stats.decode_errors` 和 `unsupported_ip_fragments` |
| 采集提前退出 | `capture-exits.txt` 和 `end-reason.txt`，`tcpdump` 异常会结束会话 |
| 网页打不开 | `curl http://127.0.0.1:8765/api/state` |

诊断 JSON 约每 2 秒原子写入一次，记录协议号、动作号、缓存、分片、解码错误以及身份和 HP 的接收状态。
