#!/usr/bin/env bash
# ============================================================
# 發布網站到 site 分支（Vercel 從 site 分支部署）
#
# site 分支每次都是「單一 commit」並強制覆蓋，只含網頁與資料，
# 不會讓 repo 因為每旬更新資料而無限膨脹；main 分支只放程式碼。
#
# 用法（在 repo 根目錄）：
#   scripts/publish_site.sh                 # 下載本期＋近 8 季、整理資料後發布
#   SKIP_BUILD=1 scripts/publish_site.sh    # 直接發布現有 data/，不重新整理
#   BUILD_ARGS="--src ../lvr_landcsv --history ../lvr_history --out data" scripts/publish_site.sh
# ============================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BUILD_ARGS="${BUILD_ARGS:---current --seasons ${SEASONS:-8} --src lvr_landcsv --history lvr_history --out data}"
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  python3 scripts/build_web_data.py ${BUILD_ARGS}
fi
[ -f data/index.json ] || { echo "找不到 data/index.json，請先整理資料"; exit 1; }

CUR="$(git rev-parse --abbrev-ref HEAD)"
git branch -D _site_tmp >/dev/null 2>&1 || true
git checkout -q --orphan _site_tmp
git rm -rq --cached . >/dev/null
git add -f index.html manifest.webmanifest sw.js vercel.json icons data
git commit -q -m "網站發布 $(date +%Y-%m-%d)"
git push -f origin _site_tmp:site
git checkout -qf "${CUR}"
git branch -D _site_tmp >/dev/null
echo "已發布到 site 分支"
