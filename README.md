# 不動產估價工具箱

依《不動產估價技術規則》與內政部實價登錄開放資料，試算臺灣各地不動產價格的網頁工具（PWA，可安裝到手機主畫面）。

| 勘估類別 | 比較標的 | 估價方法 |
|---|---|---|
| 成屋買賣 | 實價登錄成屋買賣 | 比較法、收益法、成本法 |
| 租賃 | 實價登錄租賃 | 租賃實例比較法、積算法 |
| 預售屋 | 實價登錄預售屋（排除解約） | 比較法、成本法 |
| 建商開發 | 實價登錄土地交易 | 土地比較法、土地開發分析法、合建分回、購地利潤率 |

比較法依 §25～§27 自動檢核調整率上限（單項 15%、總調整 30%）、試算價格差距（20%）與比較標的件數（三件以上）。

## 結構

```
index.html              網頁本體（單檔）
manifest.webmanifest    PWA 設定
sw.js                   離線快取
icons/                  App 圖示
scripts/build_web_data.py      下載並整理實價登錄資料（只用標準函式庫）
scripts/publish_site.sh        把網頁＋data/ 發布到 site 分支
.github/workflows/update-data.yml  每月 2、12、22 日自動下載資料並發布
vercel.json             Vercel 標頭設定
```

## 分支

- `main`：程式碼。`data/` 不進版控。
- `site`：網頁與資料的單一 commit，每次發布強制覆蓋，**Vercel 的 Production Branch 設為 `site`**。
  資料在 `data/{縣市代碼}/{行政區}.json`，索引為 `data/index.json`。

## 手動更新並發布

```bash
scripts/publish_site.sh               # 下載本期＋近 8 季 → 整理 → 發布到 site 分支
SKIP_BUILD=1 scripts/publish_site.sh  # 直接發布現有 data/
```

GitHub Actions 也可以在 Actions 頁面手動執行「更新實價登錄資料並發布」。

資料來源：[內政部不動產成交案件實際資訊資料供應系統](https://plvr.land.moi.gov.tw/DownloadOpenData)（本期與季別資料皆免費）。

本工具為試算參考，不構成不動產估價師出具之估價報告書。
