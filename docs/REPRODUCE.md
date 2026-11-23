# 可复现指南

命令从仓库根目录执行。先区分三个环境：电脑负责检查/暂存/Git；手机 Operit Ubuntu 负责 Python/libzstd 和可见共享文件操作；手机 Android 原生 Root shell 负责系统命令检查与用户主动启动采集。proot 的 uid 0 不等于 Android 真 Root。

## 0. 输入与依赖

运行：Python >=3.9、系统 libzstd、浏览器；Android 还需要 Root、tcpdump、ss、pidof、su、runner 使用的系统文本/进程命令，以及已有 Operit Ubuntu。不是独立 APK，不提供通用 Root/proot 安装器。

研究：用户自行持有固定版本文件；Python 依赖见 requirements-research.txt，托管工程依赖 .NET 8 SDK 和 Mono.Cecil 0.11.4，原生分析需 readelf/c++filt。依赖安装、首次 NuGet restore 可能联网；后续已有依赖的分析不访问游戏服务。原始输入不随包提供。

只读检查：

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
python3 tools/check_environment.py
```

前两项验证 Python 语法/src-dist 一致性及发布树/清单，不代表游戏验收。第三项只检查**当前 Python**；缺 libzstd 返回 2。`--android` 仅输出静态可见性，始终返回 2 标记设备检查不完整，不自动提权。

## A. 手机本地部署

1. 用 USB/MTP 等把完整仓库复制到手机共享存储，例如 `/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2`。保留中文启动/停止脚本名称。
2. 在手机 Operit Ubuntu 中进入该目录：

```bash
cd '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2'
python3 tools/check_environment.py
python3 tools/deploy_android.py --android-local
python3 tools/deploy_android.py --android-local --write
```

`--android-local` 是操作者明确确认该文件系统映射目标手机共享存储，不是工具自动识别设备。若路径不可见或无权限，停止并检查挂载，不能改在电脑上执行同一默认路径冒充手机部署。默认最终目录为 `/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/`，部署只复制九个运行文件和清单，不启动任何服务。

自定义路径必须处于 runner 已绑定的 `/storage/emulated/0/` 下；Operit 路径用实际安装值：

```bash
python3 tools/deploy_android.py --android-local --project-root /storage/emulated/0/Download/超自然行动 --operit-files /data/user/0/com.ai.assistance.operit/files --write
```

已有不同文件会拒绝覆盖。用户先执行停止脚本，再明确决定是否使用 `--overwrite`；停止旧会话不由部署器自动完成。

3. 用户在 Android **原生 Root shell** 检查：

```sh
sh '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2/tools/check_android.sh'
```

自定义 Operit 安装路径可作为该脚本第一个参数。脚本只检查调用环境、命令和文件，不启动 proot、tcpdump、后端或游戏，不通过 su 自动提权。即使返回 0，也只表示列出的先决项，没有证明实际对局可用。

4. 用户准备实际采集时，在 Android 原生 shell 手动启动：

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
```

浏览器打开 `http://127.0.0.1:8765`；自行进入对局。capture.json 中 running 为 true、game_pid 非零、ports 非空；诊断里观察 3/852、位置、名单和 HP 动作是否到达。不要把“未收到”当作已恢复。默认 600 秒，目录约 64 MiB 轮询停止，不是硬上限。

停止：

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/停止.sh'
```

排错依次查 server.log、capture-0001.log、capture.json、diagnostics.json、sockets.latest.txt、end-reason.txt；它们是私人运行资料，不提交仓库。

## B. 电脑暂存和手动传输

```bash
python3 tools/deploy_android.py --stage build/android-stage
python3 tools/deploy_android.py --stage build/android-stage --write
```

--stage 是电脑本地输出根，--project-root 是写进脚本的最终 Android 路径，两者不能混为一谈。把暂存树中的 `成品/udp-radar-v1` 手动复制到最终手机项目根下的 `成品/`。日志目录会由用户启动时创建。仍需完整仓库提供依赖检查工具，并按 A 分别检查手机 Ubuntu 和 Android 原生环境。不会自动通过 ADB 或网络传输。

默认不带 --stage/--android-local 的部署命令只显示计划；裸 --write 会被拒绝，避免电脑误写默认手机路径。

## C. 构建运行目录

```bash
python3 tools/build_dist.py --output build/runtime
```

输出九个运行文件与 runtime-manifest.json，是解释型文件复制，不是 APK 编译，不启动服务。`build/` 属于开发产物，不得出现在最终发布树；发布检查会拒绝该目录。

## D. 离线解析：需要自己的经典 PCAP

```bash
python3 tools/replay_pcap.py /path/to/your.pcap --ports 38516,41003 --summary build/my-summary.json
```

端口是已确认的本机游戏 UDP 端口，不是远端端口。所有输出都必须使用新路径，工具不覆盖已有文件，也不允许 summary/events 重合或覆盖 PCAP/CSV。PCAP 记录结构会先检查；不支持 pcapng。--events 是可选私人 JSONL，切勿提交。

持有合法基线 CSV 时：

```bash
python3 tools/replay_pcap.py /path/to/baseline.pcap --ports 45063,45283 --expected-csv /path/to/coordinates.csv --summary build/baseline-summary.json
```

CSV 字段：packet,category,entity_field1,entity_field2,scale,raw_x,raw_y,raw_z,frame_field4,frame_field5,timestamp,x,y,z。历史固定样本 8184 包、7101 条坐标逐条 raw/XYZ/顺序/时间戳一致；未提供公开流量，因此读者不能无输入重做私人样本验收。

退出码：
- 0：观察到事件，没有已记录的应用错误或已知未处理指标；不是网络完整性保证。
- 2：参数/输入结构/解码/CSV 对照出错，检查 status、input_error、last_error。
- 3：无目标事件，或存在未支持流量、截短捕获、未完成/丢弃传输分片，查看 status、stats、unhandled_indicators。

坐标 CSV 匹配与全流量完整性是两个判断：csv_match=true 仍可能因为无关 IP 分片而返回 3。重放报告和哈希也按私人诊断处理。

## E. 固定版本研究：需要自己的输入

依赖准备（可能联网）：

```bash
python3 -m pip install -r requirements-research.txt
dotnet --list-sdks
dotnet build research/managed/StaticAssemblyInspect -c Release
dotnet build research/managed/ProtocolEvidenceInspect -c Release
dotnet build research/managed/StaticReferenceInspect -c Release
```

这三个标准 .NET SDK 构建命令留待电脑端实际验收；打包环境没有 SDK，未宣称构建成功。构建 bin/obj、研究 work 输出属于私有/生成资料，移出正式发布树后再做发布检查。

提取并建立索引：

```bash
python3 research/extract_hotupdate.py --bundle /path/to/updatescript_bundle --output work/hotupdate
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- index work/hotupdate/UpdateScript_500.dll work/index
dotnet run --project research/managed/ProtocolEvidenceInspect -c Release -- attrs work/hotupdate/UpdateScript_500.dll work/attrs.json 0x0601CD83
dotnet run --project research/managed/StaticAssemblyInspect -c Release -- il work/hotupdate/UpdateScript_500.dll work/il 0x0601CD83
python3 research/disassemble_native.py --so /path/to/libjelib.so --output work/native
```

预期提取 TextAsset 与 asset-manifest.json，index 生成 candidate-index.json/type-index.tsv；IL 目录生成所选 token 的文本，native 目录含匹配符号的汇编和 manifest。必须检查输出非空，token 只适用于固定程序集。提取和原生反汇编会记录输入哈希，但**不会强制限定固定哈希**，需要使用者主动核对。

固定输入识别值：
- UpdateScript_500.dll：1ce1e36603c3c481a03a321edc1d08f6ba24f165855021b808effbb90d84a5ec
- libjelib.so：a6e64e050d3ac896bb5310e3bcfc80f8d724188b6db1955e216bb868641526f6
- 热更新 bundle：63a76b500939a3b3e99233975abee294e31586cd6c33aaabd090193d3239eb11

可选恢复：

```bash
python3 research/restore_inputs.py metadata --input /path/to/global-metadata.dat --output work/metadata-restored
python3 research/restore_inputs.py il2cpp --input /path/to/libil2cpp.so --output work/il2cpp-restored
```

只有恢复入口强制校验已知输入 SHA256，不匹配即拒绝；结果是离线分析副本，不是可安装/运行游戏库。详细方法证据见 PROTOCOL.md；额外 HP 字段用途仍须回到固定 IL 复核。

## F. 发布

先把 build/work/bin/obj 等生成资料移到仓库外的私人位置。用修复后的检查器：

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
# 若仍持有与当前目录完全一致的原始发布 ZIP，可额外检查：
python3 tools/publish_check.py . --archive /path/to/udp-radar-open-source-v2.2.zip
```

检查器不更新清单。授权修改文件后需由维护者更新 FILES_SHA256.json，不能为了让检查通过而擅改 SOURCE_ORIGIN.json 或已验收运行文件。Git 索引和历史、许可证及人工隐私审查按 PUBLISH_CHECKLIST.md 继续；未经明确授权不创建远程或推送。
