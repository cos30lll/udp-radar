# 发布记录

运行版本为 `v2.2-names-candidate`。`release-r1` 和 `release-r2` 随附的九个运行文件与 `SOURCE_ORIGIN.json` 中的记录一致。

## release-r1（2026-11-23）

- ZIP 用 Python 的 `zipfile` 打包，保留四个中文脚本文件名。发布检查核对文件类型、UTF-8 文本、私有目录、发布清单、运行文件哈希，以及可选的 ZIP 内容。
- 部署工具要求指定 `--stage` 或 `--android-local` 才能写入，分别用于电脑暂存和手机本地复制。部署报告中 `transferred` 和 `started` 都为 `false`。
- `tools/` 和 `research/` 的文本读写显式指定 UTF-8。终端里的结构化报告使用 ASCII 转义，避免中文在部分终端乱码。
- 文档保留可追溯的入站统计（2830 条），删掉口径不一致的双向总数。补充了固定样本哈希和 HP 字段的限制。
- 重放工具会保护输入和已有输出。摘要与事件文件须使用不同路径。工具先检查经典 PCAP 结构，再按错误、无事件和部分处理的情况返回状态。
- Python 和 `libzstd` 在当前 Python 环境里检查。Android 原生命令用 `check_android.sh` 在 Root shell 下检查，`--android` 参数只报告当前环境可见的信息。

本版检查了语法、文件一致性和辅助工具。`.NET 8` 工程的 SDK 构建仍待验证。

## release-r2（2026-11-23）

- 新增从零实现教程和证据阅读指南，覆盖输入文件、传输、协议字段、后端和网页。部署命令继续放在复现指南里。
- 新增 `research/pcap_lab.py`，用于双向分布统计、应用消息提取和嵌套字段检查。`research/legacy_move50.py` 保留早期发现的自定义编码分支。
- 修正 `restore_inputs.py` 中可选 IL2CPP 分析对 metadata 报告的依赖。

使用已有样本检查了提取、恢复依赖、双向统计和场景、实体、动作字段。具体结果见[验证记录](VALIDATION.md)。
