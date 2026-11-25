# 部署与复现

除另有说明，命令都在仓库根目录执行。手机需要 Root 和系统命令 `tcpdump`、`ss`、`pidof`、`su`。Python 3.9+ 和 `libzstd` 装在 Operit Ubuntu 里。

## A. 手机本地部署

把完整仓库复制到手机共享存储。在 Operit Ubuntu 里切换到实际存放仓库的目录，先检查环境、预览部署路径，再用 `--write` 写入文件。

```sh
cd '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2'
python3 tools/check_environment.py
python3 tools/deploy_android.py --android-local
python3 tools/deploy_android.py --android-local --write
```

自定义项目目录用 `--project-root`，放在 `/storage/emulated/0/` 下。Operit 安装路径有变动时用 `--operit-files`。更新旧版前先停止采集，需要覆盖原文件时给部署命令加 `--overwrite`。

在 Android 原生 Root shell 中检查环境，然后启动。

```sh
sh '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2/tools/check_android.sh'
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
```

打开 `http://127.0.0.1:8765`。默认采集 600 秒，目录达到约 64 MiB 时也会停止。如果要提前结束，在同一个 shell 中执行：

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/停止.sh'
```

页面没收到数据时，先看 `capture.json` 中的 `running`、`game_pid` 和 `ports`，再查 `diagnostics.json` 中的 3/852、位置、名单和 HP 计数。服务启动失败看 `server.log`，采集进程的问题看 `capture-0001.log` 和 `end-reason.txt`。端口归属见 `sockets.latest.txt`。原始 PCAP 和日志留在本地。

## 电脑暂存

```sh
python3 tools/deploy_android.py --stage build/android-stage --write
```

把 `build/android-stage/成品/udp-radar-v1/` 复制到手机项目根目录下的 `成品/`。仓库也要复制到手机，用来执行手机环境检查。[手机本地部署](#a-手机本地部署)

只需导出运行文件和清单时，用 `python3 tools/build_dist.py --output build/runtime`。

## PCAP 回放

把 `--ports` 换成当时通过游戏 PID 和 `ss` 确认的本机 UDP 端口。工具会拒绝覆盖已有输出，请给结果取个新文件名。`--events` 导出的 JSONL 含逐条事件，保存在本机即可。

```sh
python3 tools/replay_pcap.py /path/to/your.pcap --ports 38516,41003 --summary build/my-summary.json
python3 tools/replay_pcap.py /path/to/baseline.pcap --ports 45063,45283 --expected-csv /path/to/coordinates.csv --summary build/baseline-summary.json
```

| 退出码 | 结果 |
|---|---|
| 0 | 读到事件，未发现已知的应用错误或未处理情况 |
| 2 | 参数、输入结构、解码或 CSV 核对出错，查看 `status`、`input_error`、`last_error` |
| 3 | 无目标事件，或存在未支持、截短、未收齐或已丢弃的记录，查看 `stats` 和 `unhandled_indicators` |

`csv_match=true` 时仍可能因未支持的 IP 分片返回 3。历史基线见 [测试记录](VALIDATION.md)。

## 固定版本研究

准备自己的固定版本文件。Python 依赖见 `requirements-research.txt`，托管工程需要 .NET 8 SDK 和 Mono.Cecil 0.11.4，原生分析需要 `readelf` 和 `c++filt`。构建前可用 `dotnet --list-sdks` 检查 SDK。

```sh
python3 -m pip install -r requirements-research.txt
dotnet build research/managed/StaticAssemblyInspect -c Release
dotnet build research/managed/ProtocolEvidenceInspect -c Release
dotnet build research/managed/StaticReferenceInspect -c Release
```

提取热更新程序集、导出 IL、恢复 metadata 和核对输入哈希的步骤见[实现教程](FROM_ZERO.md)。查某条消息对应的解析方法，可用[协议分析索引](EVIDENCE_WALKTHROUGH.md)。

用下面的命令查看应用消息和字段。例子中的端口要换成本机实际端口。

```sh
python3 research/pcap_lab.py survey /path/to/round.pcap --ports 45283 --direction both --summary work/survey.json
python3 research/pcap_lab.py extract /path/to/round.pcap --ports 45283 --direction in --message 3/852 --output work/scene.app
python3 research/pcap_lab.py fields work/scene.app --path 6:1/4:1 --output work/action-fields.json
```

`extract` 写出四字节应用头和消息体。`fields` 从偏移 4 开始，按 `字段号:出现次数` 逐层进入。旧版 3/50 消息用 `legacy_move50.py` 查看。

## 发布检查

把生成的 `build/`、`work/`、`bin/`、`obj/` 移出仓库。文件改动后更新 `FILES_SHA256.json`，再核对发布目录。

```sh
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

同时核对 ZIP 时给第二条命令加上 `--archive /path/to/udp-radar-open-source-v2.2.zip`。[发布清单](PUBLISH_CHECKLIST.md)
