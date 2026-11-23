# 发布检查清单

## 发布目录

1. `python3 tools/build_dist.py --check`：Python 语法与九个 src/dist 文件一致，不创建缓存。
2. `python3 tools/publish_check.py .`：本地发布树、文件哈希、SOURCE_ORIGIN 与有限隐私规则通过。任何警告需理解，OK 不等于全面审查。
3. 禁止 PCAP/CSV/JSONL/日志/游戏二进制/密钥/.env/未知文件，build/work/bin/obj/__pycache__ 等生成目录也不能打入包。工具会拒绝；先移出正式发布树，不靠 .gitignore 掩盖。
4. 清单不包含自身哈希；任何获授权的文档/工具修改都要刷新 FILES_SHA256.json。不得修改原运行哈希来掩盖运行文件变化。
5. 重新打包必须使用明确 UTF-8 名称的 ZIP。外层目录名保持 udp-radar-open-source-v2.2；四个中文脚本名可直接按预期路径读取，无需转码。
6. `python3 tools/publish_check.py . --archive /path/to/udp-radar-open-source-v2.2.zip` 检查 ZIP 名称、安全路径与内容一致性；ZIP 存放在仓库外。

## 人工及电脑端

- 人工复核公开文档没有玩家信息、服务器地址、会话路径、真实 token 或设备私人用户名；标准公共项目路径有意保留，不要声称没有任何绝对路径。
- 对 Git 执行 `git status --short`、`git ls-files`、`git diff --cached --stat`、`git diff --cached`，并独立审查已有历史。目录检查器不审查 Git 历史；敏感文件即使当前已删也可能留在历史中。
- 确认许可证 MIT 方案和署名、目标 owner/name、public/private、保留 dist 与项目路径的选择；授权公开代码不等于授权公开流量。
- 不将游戏用户反馈、文件一致性、退出码或本机暂存冒充跨设备实测。电脑端 .NET SDK 构建和手机实际运行仍各需真实验收。
- 不索取、保存、回显 GitHub token，不擅自 force push、改写历史或开 Pages/Release。

## 授权后的本地 Git 准备

以下只是顺序提示，不由包自动执行。先确认当前目录与是否已有仓库；已有仓库不要盲目重置分支。新仓库可 `git init -b main`，然后暂存、检查、`git commit`。用户名和邮箱由用户本机配置。确认 commit 已存在与远程地址后，才执行用户明确授权的推送。没有 workflow 时不能声称 CI 已通过。
