# AGENTS.md

## 本地检查

在仓库根目录运行以下命令。

```sh
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

有 Android 环境问题时，参照 [部署与复现](docs/REPRODUCE.md) 分别检查手机的 Operit Ubuntu 和 Android 原生 Root shell。

## 修改与验证

- 修改发布文件后，同步 `FILES_SHA256.json`。`SOURCE_ORIGIN.json` 记录原机运行文件的哈希，更新运行代码时按 [贡献指南](CONTRIBUTING.md) 核对来源和验证记录。
- 协议变更优先做离线验证，样本用合成数据或自己的抓包。运行日志、抓包、玩家信息、游戏二进制和凭据留在仓库之外。
- 提交时说明实际运行过的检查。已有结果可查 [验证记录](docs/VALIDATION.md)。
