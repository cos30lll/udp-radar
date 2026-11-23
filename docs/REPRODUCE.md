# 部署与复现

想了解解析器的开发过程，可读[从零实现 UDP 雷达](FROM_ZERO.md)和[证据索引](EVIDENCE_WALKTHROUGH.md)。

未另行指定时，在仓库根目录执行命令。电脑用来检查文件和准备部署目录。手机上的 Operit Ubuntu 负责运行 Python、加载 libzstd 和访问共享存储。检查 Android 系统命令、启动采集都需要 Android 原生 Root shell。Operit Ubuntu 显示的 UID 0 只在 proot 环境内有效。

## 环境要求

运行程序需要 Python 3.9 或更新版本、系统 libzstd 和浏览器。Android 侧请先准备 Root 权限、Operit Ubuntu、`tcpdump`、`ss`、`pidof`、`su` 和 runner 用到的系统命令。

复现研究部分需要自行准备固定版本的输入文件。Python 依赖见 `requirements-research.txt`，托管工程需要 .NET 8 SDK 和 Mono.Cecil 0.11.4，原生分析需要 `readelf` 和 `c++filt`。安装依赖及首次 NuGet restore 可能需要联网。依赖装好后可离线分析。

可以先运行这三项检查。

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
python3 tools/check_environment.py
```

`build_dist.py --check` 检查 Python 语法和 `src/`、`dist/` 的文件是否一致。`publish_check.py` 检查发布目录和清单。`check_environment.py` 在当前 Python 环境中找不到 libzstd 时返回 2。加上 `--android` 后，该命令只列出可见项目，并固定返回 2。

## A. 手机本地部署

1. 用 USB/MTP 等把完整仓库复制到手机共享存储，例如 `/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2`。保留中文启动/停止脚本名称。
2. 在手机的 Operit Ubuntu 中进入共享目录，检查依赖并复制运行文件。

```bash
cd '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2'
python3 tools/check_environment.py
python3 tools/deploy_android.py --android-local
python3 tools/deploy_android.py --android-local --write
```

用 `--android-local` 前，先确认手机的共享目录在 Operit Ubuntu 里已挂载且可写。部署命令会把九个运行文件和清单复制到 `/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/`。

自定义目录也要放在 runner 已绑定的 `/storage/emulated/0/` 下。`--operit-files` 用实际安装路径。

```bash
python3 tools/deploy_android.py --android-local --project-root /storage/emulated/0/Download/超自然行动 --operit-files /data/user/0/com.ai.assistance.operit/files --write
```

如果目标目录已有不同版本的文件，先用停止脚本结束旧会话，再按需加 `--overwrite`。

3. 在 Android **原生 Root shell** 中检查系统命令和文件。

```sh
sh '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2/tools/check_android.sh'
```

使用自定义 Operit 安装路径时，可以把路径作为脚本的第一个参数。脚本返回 0 表示列出的先决条件通过。

4. 准备采集时，在同一个 shell 中运行启动脚本。

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
```

在浏览器打开 `http://127.0.0.1:8765`，进入对局后查看 `capture.json`。`running` 应为 `true`，`game_pid` 应为非零值，`ports` 应有记录。诊断页可以查看是否收到 3/852、位置、名单和 HP 动作。默认采集 600 秒。脚本轮询目录大小，发现达到约 64 MiB 时停止，因此实际大小可能超过这个值。

手动停止时执行下面的命令。

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/停止.sh'
```

排错时依次查 `server.log`、`capture-0001.log`、`capture.json`、`diagnostics.json`、`sockets.latest.txt` 和 `end-reason.txt`。这些文件只留在本地。

## B. 电脑暂存和手动传输

```bash
python3 tools/deploy_android.py --stage build/android-stage
python3 tools/deploy_android.py --stage build/android-stage --write
```

`--stage` 指定电脑上的暂存目录。`--project-root` 是脚本部署后在 Android 上使用的路径。把暂存目录里的 `成品/udp-radar-v1` 手动复制到手机项目根目录下的 `成品/`。仍需把完整仓库传到手机，按[手机本地部署](#a-手机本地部署)检查 Operit Ubuntu 和 Android 原生环境。日志目录会在启动时创建。

省略 `--stage` 和 `--android-local` 时，部署命令只显示计划。写入时要指定其中一种模式。

## C. 构建运行目录

```bash
python3 tools/build_dist.py --output build/runtime
```

命令复制九个运行文件并生成 `runtime-manifest.json`。运行发布检查前请把生成的 `build/` 目录移出仓库。

## D. 离线解析 PCAP

```bash
python3 tools/replay_pcap.py /path/to/your.pcap --ports 38516,41003 --summary build/my-summary.json
```

把例子里的端口换成已确认的本机游戏 UDP 端口。工具读取经典 PCAP，并先检查记录结构。每个输出都要用尚未存在的路径，`--summary` 和 `--events` 分别指定。用 `--events` 导出的 JSONL 只留在本地。

有基线 CSV 时，可以逐条对照坐标。

```bash
python3 tools/replay_pcap.py /path/to/baseline.pcap --ports 45063,45283 --expected-csv /path/to/coordinates.csv --summary build/baseline-summary.json
```

CSV 列名依次是 `packet,category,entity_field1,entity_field2,scale,raw_x,raw_y,raw_z,frame_field4,frame_field5,timestamp,x,y,z`。已有样本包含 8184 个包，7101 条坐标的原始值、XYZ、顺序和时间戳均与基线逐条一致。样本原始流量留在本地。

退出码

- `0` 表示观察到事件，且未发现应用错误或已知的未处理情况。
- `2` 表示参数、输入结构、解码或 CSV 对照出错。查看 `status`、`input_error` 和 `last_error`。
- `3` 表示未观察到目标事件，或遇到未支持的流量、截短记录、未收齐或已丢弃的传输分片。查看 `status`、`stats` 和 `unhandled_indicators`。

即使 `csv_match=true`，无关的 IP 分片也可能使工具返回 3。重放报告和哈希同样只留在本地。

## E. 固定版本研究

安装研究依赖并尝试构建 .NET 工程。此步骤可能需要联网。

```bash
python3 -m pip install -r requirements-research.txt
dotnet --list-sdks
dotnet build research/managed/StaticAssemblyInspect -c Release
dotnet build research/managed/ProtocolEvidenceInspect -c Release
dotnet build research/managed/StaticReferenceInspect -c Release
```

三个工程尚未用标准 .NET SDK 实际构建。运行发布检查前，把生成的 `bin/`、`obj/` 和 `work/` 移到仓库外。

提取程序集并建立索引。

```bash
python3 research/extract_hotupdate.py --bundle /path/to/updatescript_bundle --output work/hotupdate
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- index work/hotupdate/UpdateScript_500.dll work/index
dotnet run --project research/managed/ProtocolEvidenceInspect -c Release -- attrs work/hotupdate/UpdateScript_500.dll work/attrs.json 0x0601CD83
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/il 0x0601CD83
python3 research/disassemble_native.py --so /path/to/libjelib.so --output work/native
```

提取得到 TextAsset 和 `asset-manifest.json`，`index` 生成 `candidate-index.json` 和 `type-index.tsv`。`il` 目录保存所选 token 的指令文本，`native` 目录包含匹配符号的汇编及清单。确认输出非空，并将工具记录的输入哈希与下列值核对。这里的 token 只适用于同一份程序集。

固定输入的 SHA-256

- UpdateScript_500.dll：1ce1e36603c3c481a03a321edc1d08f6ba24f165855021b808effbb90d84a5ec
- libjelib.so：a6e64e050d3ac896bb5310e3bcfc80f8d724188b6db1955e216bb868641526f6
- 热更新 bundle：63a76b500939a3b3e99233975abee294e31586cd6c33aaabd090193d3239eb11

也可以生成用于分析的 metadata 和 IL2CPP 副本。

```bash
python3 research/restore_inputs.py metadata --input /path/to/global-metadata.dat --output work/metadata-restored
python3 research/restore_inputs.py il2cpp --input /path/to/libil2cpp.so --metadata-report work/metadata-restored/restore-report.json --output work/il2cpp-restored
```

`restore_inputs.py` 会先核对输入的 SHA-256，哈希不匹配就退出。输出仅供离线分析。协议字段说明见[协议笔记](PROTOCOL.md)，其余 HP 值的含义仍需核对对应的 IL。

## E2. 查看 PCAP 中的消息字段

用 PID 和 `ss` 确认本机端口，再替换命令里的示例值 `45283`。同一次采集中的其他端口可能走不同的传输协议。

```bash
python3 research/pcap_lab.py survey /path/to/round.pcap --ports 45283 --direction both --summary work/survey.json
python3 research/pcap_lab.py extract /path/to/round.pcap --ports 45283 --direction in --message 3/852 --output work/scene.app
python3 research/pcap_lab.py fields work/scene.app --output work/scene-fields.json
python3 research/pcap_lab.py fields work/scene.app --path 6:1 --output work/entity-fields.json
python3 research/pcap_lab.py fields work/scene.app --path 6:1/4:1 --output work/action-fields.json
```

`extract` 输出四字节应用头和消息体。`fields` 默认从偏移 4 开始读，`--path` 按 `field:occurrence` 逐层进入长度限定字段。如果选中的帧没有实体或动作，换一条消息或检查字段出现次数。字段含义要结合读取该值的 IL 确认。输出仅供本地分析。

`pcap_lab.py` 复用本项目的固定版本传输解析。返回 0 表示读到应用消息且未记录已知问题，2 表示出错，3 表示结果不完整或未匹配。旧版 3/50 消息可以交给 `legacy_move50.py`，输入为已提取的应用消息体。

## F. 发布

先把 `build/`、`work/`、`bin/`、`obj/` 等生成目录移出仓库，再运行检查。

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
# 若仍持有与当前目录完全一致的原始发布 ZIP，可额外检查：
python3 tools/publish_check.py . --archive /path/to/udp-radar-open-source-v2.2.zip
```

发布文件有变动时，更新 `FILES_SHA256.json`。`SOURCE_ORIGIN.json` 记录原机运行文件的哈希，用来核对发布内容。提交前核对 Git 暂存区、历史、许可证和隐私信息，见[发布清单](PUBLISH_CHECKLIST.md)。
