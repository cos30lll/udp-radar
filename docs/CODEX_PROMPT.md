# 给电脑端 Codex 的提示词

解压后打开仓库，复制以下内容：

---
请先阅读 AGENTS.md、README.md、docs、SOURCE_ORIGIN.json。运行代码是 v2.2-names-candidate，发布工具/文档修订 release-r1。

先只读审计，不创建远程、不推送、不启动游戏/抓包/后端、不部署手机、不截图或读取 UI 层级：
1. 运行 `python3 tools/build_dist.py --check` 与 `python3 tools/publish_check.py .`，记录实际结果。不在干净树运行 compileall 生成缓存。
2. 按需运行 `python3 tools/check_environment.py` 检查电脑 Python/libzstd；缺库不等于发布目录损坏，不能宣称手机就绪。
3. 确认 src/dist 九个运行文件与 SOURCE_ORIGIN 哈希一致；不得更改它们或来源哈希来消除错误。
4. 人工检查隐私、Git 暂存和已有历史。检查器只是有限规则，不代表所有敏感信息都已排除。原始 PCAP、日志、玩家数据、游戏文件、凭据不得提交。
5. 电脑暂存只用 --stage，文件需手动复制手机；--android-local 不是远程部署。读 REPRODUCE 的环境分层，不代跑真实设备操作。
6. .NET 8 三工程标准 SDK 构建尚待真实电脑验收；安装/restore 可能联网，未经授权不把网络依赖准备说成已离线完成。
7. 给出问题清单、未验证边界与准备推送的文件范围，等待用户确认 owner/name、可见性、MIT 方案与署名、是否保留 dist 和标准项目路径。只有用户本轮明确授权才进行远程发布。

不要把用户原机满意反馈改写成 CI 或跨设备验收；不为增加测试数重复整套回归。不索取、保存或显示 token。用户要求停止时立即停下。
---

## 获准发布后

新仓库的本地准备示例：

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
git diff --cached
# 人工确认无敏感资料，身份配置由用户完成：
git commit -m "Initial public source release"
# 确认用户提供的远程地址、可见性和本轮授权后才操作：
git remote add origin <用户确认的仓库地址>
git push -u origin main
```

已有仓库先检查当前分支、历史和远程，不照抄初始化或覆盖配置。缺少 commit 时不能直接推送。不得自作主张发布 Release/Pages、上传 ZIP、强推或处理凭据。
