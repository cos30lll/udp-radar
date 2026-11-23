# 发布检查

更新 `FILES_SHA256.json` 中改动过的条目，移走抓包、日志和生成目录，再运行下面两条命令。

```sh
python3 tools/build_dist.py --check
python3 tools/publish_check.py .
```

提交前用 `git diff --cached` 核对文件，尤其是来源、许可证和私人数据。

发 ZIP 时，外层目录名用 `udp-radar-open-source-v2.2`，文件名用 UTF-8。压缩包放在仓库外，可用下面的命令核对。

```sh
python3 tools/publish_check.py . --archive /path/to/udp-radar-open-source-v2.2.zip
```

[发布记录](RELEASE_REPAIR.md)
