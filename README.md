# UDP Radar

UDP Radar 读取游戏发到 Android 手机上的 UDP 数据，在本机浏览器里画出实体位置和轨迹。收到玩家名单后，页面会显示姓名和 UID，收到血量更新时会显示最近一次的 HP。

v2.2 适配游戏版本 `1.35.20.001`。缺名问题已在原设备确认修复，离线回放得到的 7101 条坐标也与原记录逐条吻合。[测试记录](docs/VALIDATION.md)

## 怎么用

需要一台已 Root 的 Android 手机。Android 系统里要有 `tcpdump` 和 `ss`，Operit Ubuntu 里要有 Python 3.9+ 和 `libzstd`。

把整个仓库复制到手机共享存储，在 **Operit Ubuntu** 中进入仓库目录并安装。

```sh
python3 tools/deploy_android.py --android-local --write
```

安装完成后，切到 **Android 原生 Root shell** 启动雷达。

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
```

在手机浏览器打开 `http://127.0.0.1:8765`。默认采集 10 分钟，目录达到约 64 MiB 时也会停止。要提前结束，运行同目录下的 `停止.sh`。

## 文档

- [安装、排错与离线回放](docs/REPRODUCE.md)
- [从零实现](docs/FROM_ZERO.md) · [协议字段](docs/PROTOCOL.md) · [实现流程](docs/PIPELINE.md)
- [测试记录](docs/VALIDATION.md) · [已知限制](docs/KNOWN_LIMITATIONS.md) · [抓包与日志](docs/PRIVACY.md)

[MIT 许可证](LICENSE)
