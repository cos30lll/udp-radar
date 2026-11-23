# UDP Radar · Android 本地被动雷达

从本机 UDP 流量还原固定版本的实体坐标、动作 31 HP 原值、协议姓名/UID，并按协议标记本机身份。只读网页监听 `127.0.0.1:8765`；不注入、不改游戏内存、不主动发包、不操作角色。

运行代码：`v2.2-names-candidate`。发布工具/文档修订：`release-r2`，2026-11-23。九个 `src/` 与 `dist/udp-radar-v2.2/` 运行文件保留原机已验证字节，未因发布修复重新验收游戏。用户原机曾反馈“好了，完美了”；不代表跨设备或所有对局有效。

## 从零实现，请先读这两篇

1. **[从零实现 UDP 雷达](docs/FROM_ZERO.md)**：17 个阶段，从 APK/热更新提取、定位托管/原生收发，到 PID/端口与 PCAP、传输恢复、3/50→3/852 的真实转折、坐标/身份/HP 取证、状态机、持续采集、HTTP/Canvas 与诊断验收。
2. **[证据检索与阅读](docs/EVIDENCE_WALKTHROUGH.md)**：每个结论该导出哪些 token/函数、看什么指令和字段关系，避免只拿结果常量照抄。

新增 `research/pcap_lab.py` 提供双向应用分布统计、选中消息提取和显式嵌套字段检查；`research/legacy_move50.py` 保留早期静态分支，说明为什么不能套到实际3/852。它们只读本地文件，输出含私人数据，不进入公开包。

部署步骤是后半程，不能替代协议分析。若只想运行现成程序，继续下文与 REPRODUCE；若要复做开发过程，按 FROM_ZERO 的顺序执行并逐步保留证据。

## 边界先读

- 仅有固定游戏 `1.35.20.001`、Unity `2022.3.62f3`、metadata v31 的证据；其他版本未验证。
- 抓包阶段会限时记录**全机 UDP**，仅将已由 `ss` 关联游戏 PID 的端口送入解码。原始 PCAP 可能包含其他应用隐私，不得公开。
- 坐标按各消息 scale 还原；HP 只显示已确认的 Int32 原值，不假定最大血量。姓名按运行时实体号关联类别 4，不按坐标猜身份或敌我。
- 支持唯一连续链的合包拆分及已捕获完整顺序的传输分片；IP 分片、缺片和乱序不保证恢复。
- 不是 APK：需要 Root、系统 tcpdump/ss，以及已有 Operit proot Ubuntu/Python/libzstd 环境。换设备需要自行准备，不能保证直接可用。

## 电脑端先检查

在解压后的仓库根目录执行，只读检查不会创建 Python 缓存：

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

可选检查当前 Python 解码依赖：

```bash
python3 tools/check_environment.py
```

`libzstd_loadable=true` 仅说明当前 Python 能加载库，不说明手机 Root 或运行环境已就绪。Windows 上如不具备系统 libzstd，可在自己的 WSL/Ubuntu 中准备解析环境；仅整理 GitHub 仓库不要求运行手机后端。

## 部署到自己的手机

**电脑运行 Python 不会把文件传到手机。** 两条路线任选，详见 `docs/REPRODUCE.md`。

### 路线一：完整仓库先复制到手机

用 USB/MTP 等方式将整个解压目录复制到手机，例如：

`/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2`

在手机 **Operit Ubuntu** 中进入该目录，确认共享存储可见后执行：

```bash
python3 tools/check_environment.py
python3 tools/deploy_android.py --android-local
python3 tools/deploy_android.py --android-local --write
```

这只是本地复制，不启动游戏/抓包/服务。若已有不同文件，先由用户结束旧会话，再决定是否加 `--overwrite`。

在手机 **Android 原生 Root shell**，不是 proot Ubuntu，执行只读先决条件检查：

```sh
sh '/storage/emulated/0/Download/超自然行动/分享包/udp-radar-open-source-v2.2/tools/check_android.sh'
```

该脚本不自动提权、不启动 proot；需先由用户进入 Android 原生 Root shell。最后，只有用户准备实际采集时才手动启动：

```sh
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/启动.sh'
# 浏览器打开 http://127.0.0.1:8765
# 结束时：
sh '/storage/emulated/0/Download/超自然行动/成品/udp-radar-v1/停止.sh'
```

默认约 600 秒；关闭网页不停止后端。共享目录沿用 `udp-radar-v1` 是路径兼容，不是代码版本。

### 路线二：电脑暂存，再手动传输

```bash
python3 tools/deploy_android.py --stage build/android-stage --write
```

该命令只在电脑创建暂存树；将其中 `成品/udp-radar-v1/` 目录复制到手机项目根目录下的 `成品/`，而不是把电脑暂存路径作为手机路径。需同时把完整仓库传到手机，才能运行其 `tools/check_android.sh` 和在手机 Ubuntu 检查 Python/libzstd。工具不会通过 ADB 自动传输，也不验证设备运行。

## 构建、解析与研究

```bash
python3 tools/build_dist.py --output build/runtime
python3 tools/replay_pcap.py --help
```

构建仅复制九个解释型运行文件并生成清单，不编译 APK。默认输出 `build/` 不可直接留在正式发布树；完成工具实验后清理或移动到包外，再跑发布检查。

离线解析需要自行持有 PCAP；输出为私人数据。重放退出码：0 表示观察到事件且未记录应用错误/已知未处理指标；2 表示参数、输入、解码或对照错误；3 表示未观察到目标事件或部分处理。**0 仍不是全部流量或现场功能完整性的保证。**

研究工具另需 .NET 8 SDK、Mono.Cecil 0.11.4、UnityPy 1.25.4、capstone 5.0.9、readelf/c++filt。安装与首次 restore 可能联网；依赖备齐后才能离线分析。三个 .NET 工程的标准 SDK 构建留待电脑端验证，不能称为本轮构建已通过。

## 文档与 Codex 交接

- `docs/FROM_ZERO.md`、`EVIDENCE_WALKTHROUGH.md`：从零开发完整主线与代码证据检索。
- `docs/REPRODUCE.md`：环境分层、部署/解析/研究命令、预期结果与排错。
- `docs/PIPELINE.md`、`PROTOCOL.md`、`ARCHITECTURE.md`：实现流程、固定版本证据与资源上限。
- `docs/VALIDATION.md`、`KNOWN_LIMITATIONS.md`：原机反馈、历史离线统计、未验证边界。
- `docs/PRIVACY.md`、`SCOPE_AND_SAFETY.md`：隐私、全机抓包风险和用途边界。
- `docs/PUBLISH_CHECKLIST.md`、`CODEX_PROMPT.md`、`RELEASE_REPAIR.md`：发布和电脑端交接。
- `SOURCE_ORIGIN.json`：原机九个运行文件哈希；`FILES_SHA256.json`：除自身之外的发布文件哈希。

电脑端 Codex 先读 `AGENTS.md`，再按 `docs/CODEX_PROMPT.md` 审计。包不含游戏二进制、原始流量、GitHub 凭据或远程仓库配置；未经本轮明确授权不得创建远程仓库或推送。当前 MIT 方案与署名仍需发布者确认，不代表许可证已被用户单独审定。
