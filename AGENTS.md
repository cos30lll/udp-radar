# AGENTS.md

改动后更新 `FILES_SHA256.json`，再在仓库根目录运行下面两条命令。

```sh
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

改动运行文件时同步 `src/` 和 `dist/`，在提交中说明验证依据。[贡献指南](CONTRIBUTING.md)
