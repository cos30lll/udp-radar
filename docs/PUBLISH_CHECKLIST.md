# 发布检查

## 发布目录

```bash
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

第一条命令检查 Python 语法，并核对 `src/` 和 `dist/` 的九个运行文件。第二条核对文件清单、原版运行文件的哈希和常见隐私问题。两个检查都不生成 Python 缓存。

修改文档或工具后，更新 `FILES_SHA256.json` 里对应的条目。清单省略自身的哈希，原版运行文件的校验值记在 `SOURCE_ORIGIN.json`。

把私有输入和生成文件移出发布目录，包括 PCAP、CSV、JSONL、日志、游戏二进制、密钥、`.env` 以及 `build/`、`work/`、`bin/`、`obj/`、`__pycache__/`。发布检查也会拒绝未知文件类型和这些目录里的 Git 忽略文件。

## 提交前

用 `git status --short`、`git ls-files`、`git diff --cached --stat` 和 `git diff --cached` 核对待发布内容，另查一遍 Git 历史。重点找玩家信息、服务器地址、会话路径、凭据和个人设备路径。文档用到的共享存储路径是部署示例。

核对 MIT 许可证和署名，再确认目标仓库、可见性、`dist/` 和文档中的部署路径。机器上的文件检查、.NET 构建和手机实测应分别记录结果。

新仓库可以用 `git init -b main` 初始化。配置本地提交者姓名和邮箱后，暂存文件并检查差异，再用 `git commit` 提交。推送前核对分支和远程地址。

## ZIP

把压缩包放在仓库目录之外，保留 `udp-radar-open-source-v2.2` 为外层目录，并以 UTF-8 编码文件名。打包后核对四个中文脚本的路径和包内内容。

```bash
python3 tools/publish_check.py . --archive /path/to/udp-radar-open-source-v2.2.zip
```
