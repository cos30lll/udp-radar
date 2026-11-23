# UDP Radar

Android 上的 UDP 雷达。在手机浏览器里看实体坐标、玩家名、UID 和血量。v2.2 已在游戏版本 `1.35.20.001` 上验证。

## 怎么用

手机需 Root，Android 上装好 `tcpdump` 和 `ss`，Operit Ubuntu 里准备 Python 3.9+ 和 `libzstd`。

把整个仓库复制到手机共享存储，在 **Operit Ubuntu** 中进入仓库目录并安装。

```sh
python3 tools/deploy_android.py --android-local --write
```

在 **Android 原生 Root shell** 中启动。

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
```

打开 `http://127.0.0.1:8765`。默认运行约 10 分钟，提前结束就运行同目录下的 `停止.sh`。

## 文档

- [安装、排错与离线回放](docs/REPRODUCE.md)
- [从零实现](docs/FROM_ZERO.md) · [协议字段](docs/PROTOCOL.md) · [实现流程](docs/PIPELINE.md)
- [测试记录](docs/VALIDATION.md) · [抓包与日志](docs/PRIVACY.md)

[MIT 许可证](LICENSE)
