# UDP Radar

UDP Radar 在 Android 手机上读取游戏的 UDP 流量，把实体坐标、玩家名和 UID 显示在本机网页上。它用登录和名单消息标记本机玩家，血量显示动作 31 的整数原值。

v2.2 目前只在游戏 `1.35.20.001`（Unity `2022.3.62f3`，metadata v31）上验证过。手机需已 Root，Android 原生环境需要 `tcpdump` 和 `ss`，Operit Ubuntu 需要 Python 3.9 以上和 `libzstd`。采集时会短暂记录手机上所有应用的 UDP 流量，解析器用游戏进程的端口筛选数据。原始 PCAP 请留在本机。

## 安装到手机

### 在手机上复制

先把整个仓库复制到手机共享存储，例如 `/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2`。在手机的 **Operit Ubuntu** 里进入这个目录，依次检查依赖、预览复制计划和写入文件。

```sh
python3 tools/check_environment.py
python3 tools/deploy_android.py --android-local
python3 tools/deploy_android.py --android-local --write
```

已有旧版时，先停止旧会话。确认要替换文件后，可给最后一条命令加上 `--overwrite`。

在手机的 **Android 原生 Root shell** 里运行环境检查。仓库放在其他位置时，换成实际路径。

```sh
sh '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2/tools/check_android.sh'
```

### 在电脑上准备文件

也可以先在电脑上生成要复制的目录。

```sh
python3 tools/deploy_android.py --stage build/android-stage --write
```

把生成的 `build/android-stage/成品/udp-radar-v1/` 复制到手机项目目录下的 `成品/`。完整仓库也要复制一份到手机，以便运行上面的两个环境检查。[部署与复现](docs/REPRODUCE.md)里有完整的路径示例。

### 启动和停止

以下是默认路径下的启动命令。在手机的 **Android 原生 Root shell** 里执行。

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
```

启动后，用手机浏览器打开 `http://127.0.0.1:8765`。默认采集约 600 秒。想提前结束就运行停止脚本，关网页不会停掉采集。`udp-radar-v1` 是沿用的安装目录名。

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/停止.sh'
```

## 本地检查和离线回放

在仓库根目录执行以下命令，可以检查 Python 语法、`src/` 与 `dist/` 的一致性，以及发布清单。

```sh
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

要重新生成那九个运行文件的副本，运行 `python3 tools/build_dist.py --output build/runtime`。回放自己的 PCAP 时，可以先用 `python3 tools/replay_pcap.py --help` 查看参数。退出码和回放示例见 [部署与复现](docs/REPRODUCE.md)。`research/pcap_lab.py` 用来检查抓包里的消息分布和字段，`research/legacy_move50.py` 保留早期 `3/50` 消息的离线解析。

## 文档

- 从热更新程序集和抓包开始复现开发过程。[从零实现 UDP 雷达](docs/FROM_ZERO.md)
- 对照代码和消息字段，了解坐标、身份和血量是怎么确认的。[证据阅读指南](docs/EVIDENCE_WALKTHROUGH.md)
- 消息格式、分片处理和程序结构。[协议](docs/PROTOCOL.md) · [处理流程](docs/PIPELINE.md) · [架构](docs/ARCHITECTURE.md)
- 离线回放结果、现场反馈和已知限制。[验证记录](docs/VALIDATION.md) · [已知限制](docs/KNOWN_LIMITATIONS.md)
- 采集和分享数据时的注意事项。[隐私](docs/PRIVACY.md) · [适用范围](docs/SCOPE_AND_SAFETY.md)
- 核对发布文件和版本变化。[发布清单](docs/PUBLISH_CHECKLIST.md) · [发布记录](docs/RELEASE_REPAIR.md)

项目采用 MIT 许可证。[LICENSE](LICENSE)
