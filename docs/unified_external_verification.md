# 公开安装核验

本候选的本地完整验收和独立复建已通过。公开附件上传后的重新下载、干净安装及完整回归仍待实际执行；本文件当前不宣称这些步骤通过。完成后以对应 SHA 和修订的实际核验记录更新。

公开安装命令：

```bash
git clone --branch v1.10.1-repair-code.1 https://github.com/yyh427/fineAtlas-V1.git
cd fineAtlas-V1
python3 -m pip install .
python3 scripts/download_single.py --manifest unified_data.json --output-dir /path/to/fineatlas
python3 scripts/verify_unified_install.py --database /path/to/fineatlas/fineatlas.sqlite \
  --manifest unified_data.json --expected-validation docs/unified_validation.json \
  --output /path/to/install-audit
```
