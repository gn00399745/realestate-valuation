# -*- coding: utf-8 -*-
"""
build_web_data.py
====================
把內政部實價登錄 Open Data（本期＋歷史季別）整理成「不動產估價工具箱」網頁用的
精簡 JSON（web/data/{縣市代碼}/{行政區}.json、web/data/index.json）。

只用 Python 標準函式庫，Mac 內建 python3 即可執行。

資料來源（皆免費、免登入）：
    本期：   https://plvr.land.moi.gov.tw/Download?type=zip&fileName=lvr_landcsv.zip
    歷史季別：https://plvr.land.moi.gov.tw/DownloadSeason?season=115S2&type=zip&fileName=lvr_landcsv.zip
    （付費的是實價查詢服務網的客製化「資料申請」，季別 Open Data 不收費）

用法（在 realestate 資料夾執行）：
    python3 build_web_data.py                     # 只整理現有資料（lvr_landcsv + lvr_history）
    python3 build_web_data.py --seasons 8         # 先下載近 8 季歷史資料（已下載者略過）再整理
    python3 build_web_data.py --current           # 先下載本期資料到 lvr_landcsv 再整理

每次執行都會把 lvr_landcsv（本期）另存一份到 lvr_history/cur_YYYYMMDD，
所以即使不下載季別，只要每旬更新本期，歷史也會逐步累積。
重複案件以「編號」去重。
"""
from __future__ import annotations
import argparse, csv, io, json, re, shutil, ssl, sys, time, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://plvr.land.moi.gov.tw"
HERE = Path(__file__).resolve().parent
SQM = 0.3025
TW = timezone(timedelta(hours=8))
COUNTIES = {"A": "臺北市", "B": "臺中市", "C": "基隆市", "D": "臺南市", "E": "高雄市", "F": "新北市",
            "G": "宜蘭縣", "H": "桃園市", "I": "嘉義市", "J": "新竹縣", "K": "苗栗縣", "M": "南投縣",
            "N": "彰化縣", "O": "新竹市", "P": "雲林縣", "Q": "嘉義縣", "T": "屏東縣", "U": "花蓮縣",
            "V": "臺東縣", "W": "金門縣", "X": "澎湖縣", "Z": "連江縣"}
# 依《不動產估價技術規則》§23，情況特殊且無法合理調整者不採用
SPECIAL = ["親友", "親屬", "關係人", "親等", "員工", "受僱", "法拍", "拍賣", "抵押權人", "強制執行",
           "急買", "急賣", "急售", "受贈", "贈與", "遺產", "共有物分割", "債權債務", "非市場",
           "含增建", "瑕疵", "凶宅", "毛胚", "特殊"]
BTYPES = ["住宅大樓", "華廈", "公寓", "透天厝", "套房", "店面", "辦公商業大樓", "廠辦", "工廠", "倉庫"]
CN = {"零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


# ---------------------------------------------------------------- download
def _ctx():
    try:
        import certifi  # 有裝就用，避免 macOS python 憑證問題
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    # Python 3.13 起預設開啟 VERIFY_X509_STRICT，政府 GRCA 憑證鏈缺少
    # Subject Key Identifier 會被拒絕（Missing Subject Key Identifier）。
    # 只關閉這項嚴格檢查，其餘憑證驗證照常進行。
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def _fetch_urllib(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (valuation-toolbox)"})
    with urlopen(req, context=_ctx(), timeout=180) as r:
        return r.read()


def _fetch_curl(url: str) -> bytes:
    """備援：使用系統 curl（macOS 內建，採用鑰匙圈的信任憑證）。"""
    import subprocess
    r = subprocess.run(["curl", "-sSfL", "--max-time", "300", "-A", "Mozilla/5.0", url],
                       capture_output=True, timeout=320)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "ignore").strip() or f"curl exit {r.returncode}")
    return r.stdout


def fetch_zip(url: str) -> bytes:
    try:
        data = _fetch_urllib(url)
    except Exception as e:
        print(f"(urllib 失敗：{e}；改用 curl) ", end="", flush=True)
        data = _fetch_curl(url)
    if data[:2] != b"PK":
        raise RuntimeError("下載內容不是 ZIP（可能該季尚未發布）")
    return data


def extract(data: bytes, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            base = n.split("/")[-1]
            if re.match(r"^[a-z]_lvr_land_[abc]\.csv$", base, re.I) or base == "build_time.xml":
                (dest / base).write_bytes(z.read(n))


def recent_seasons(n: int) -> list[str]:
    t = date.today()
    y, q = t.year - 1911, (t.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        q -= 1
        if q < 1:
            q, y = 4, y - 1
        out.append(f"{y}S{q}")
    return out


# ---------------------------------------------------------------- parsing
def cn_num(s: str):
    if s.isdigit():
        return int(s)
    n = cur = 0
    for ch in s:
        if ch in CN:
            cur = CN[ch]
        elif ch == "十":
            n += (cur or 1) * 10; cur = 0
        elif ch == "百":
            n += (cur or 1) * 100; cur = 0
        else:
            return None
    return n + cur if s else None


def floor_of(t: str):
    if not t:
        return None
    base = "地下" in t
    core = re.sub(r"地下|地上|層|樓|之.*", "", re.split(r"[，,、]", t.strip())[0]).strip()
    n = cn_num(core)
    return None if n is None else (-n if base else n)


def roc(s: str):
    s = re.sub(r"\D", "", s or "")
    if len(s) < 6:
        return None
    s = s.zfill(7)
    try:
        d = date(int(s[:3]) + 1911, int(s[3:5]) or 1, int(s[5:7]) or 1)
    except ValueError:
        return None
    # 原始資料偶有民國年誤植而落在未來，這類日期不可信，直接排除
    return None if (d - date.today()).days > 31 else d


def btype_of(s: str) -> str:
    for b in BTYPES:
        if b in (s or ""):
            return b
    return "其他"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def read_rows(path: Path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    start = 2 if len(rows) > 1 and rows[1] and re.match(r"^[A-Za-z]", rows[1][0] or "") else 1
    return [dict(zip(head, r)) for r in rows[start:] if len(r) > 5]


def pick(d: dict, *keys):
    for k in keys:
        if k in d:
            return d[k]
    return ""


COLS = ["addr", "date", "floor", "tfloor", "btype", "age", "area", "unit", "total", "parkPrice",
        "pkBundled", "landPing", "remark", "extra", "multi"]


def _building_rec(r, dt, tot, area_key, park_area_key, park_price_key, extra=""):
    """房地／預售／租賃共用：扣除車位面積與車位價格後求單價（元/坪）。"""
    ba = num(pick(r, *area_key))
    pa = num(pick(r, *park_area_key))
    pp = num(r.get(park_price_key))
    has_pk = bool(r.get("車位類別", "").strip()) or pa > 0
    area = (ba - (pa if pp > 0 else 0)) * SQM
    if area <= 3:
        return None
    unit = (tot - pp) / area
    cp = roc(r.get("建築完成年月"))
    age = round(max(0.0, (dt - cp).days / 365.25), 1) if cp else None
    return [r.get("土地位置建物門牌", ""), int(dt.strftime("%Y%m%d")), floor_of(pick(r, "移轉層次", "租賃層次")),
            floor_of(r.get("總樓層數", "")), btype_of(r.get("建物型態")), age, round(area, 2), round(unit),
            round(tot), round(pp), 1 if (has_pk and pp == 0) else 0,
            round(num(pick(r, "土地移轉總面積平方公尺", "土地面積平方公尺")) * SQM, 2),
            r.get("備註", "")[:40], extra, _multi(r)]


def _multi(r):
    """交易筆棟數含 2 棟（戶）以上建物者，總價為多戶合計，單價不宜直接比較。"""
    m = re.search(r"建物(\d+)", r.get("交易筆棟數", "") or r.get("租賃筆棟數", "") or "")
    return 1 if (m and int(m.group(1)) > 1) else 0


def zone_of(r):
    z = r.get("都市土地使用分區", "").strip()
    if z:
        return z
    # 非都市土地保留「使用分區/使用地編定」，網頁據以推估國土功能分區
    nz = "/".join(x for x in (r.get("非都市土地使用分區", "").strip(), r.get("非都市土地使用編定", "").strip()) if x)
    return ("非都市-" + nz) if nz else "未載明"


ZONE_CLASS = [("保護區", "保護"), ("保育區", "保護"), ("公共設施", "公設"), ("保留地", "公設"), ("道路", "公設"), ("公園", "公設"), ("學校", "公設"),
              ("住宅", "住"), ("住", "住"), ("商業", "商"), ("商", "商"), ("產業", "工"), ("工業", "工"), ("工", "工"),
              ("農業", "農"), ("農", "農"), ("保護", "保護"), ("保存", "保護"), ("風景", "保護")]
LAND_EXCLUDE = ["公共設施保留地", "道路用地", "政府機關標讓售"]


def zone_class(z: str) -> str:
    if z.startswith("非都市"):
        return "非都市"
    core = z.split(":")[-1]
    for k, c in ZONE_CLASS:
        if k in core:
            return c
    return "其他"


def parse_a(path: Path, sale: dict, land: dict):
    """不動產買賣：房地 → sale；純土地 → land（元/坪土地）。"""
    for r in read_rows(path):
        tg = r.get("交易標的", "")
        remark = r.get("備註", "")
        if any(k in remark for k in SPECIAL):
            continue
        dt = roc(r.get("交易年月日"))
        tot = num(r.get("總價元"))
        if not dt or tot <= 0:
            continue
        sid = r.get("編號") or f"{path.name}:{r.get('土地位置建物門牌')}:{dt}"
        if tg == "土地":
            lp = num(r.get("土地移轉總面積平方公尺")) * SQM
            if lp < 1 or any(k in remark for k in LAND_EXCLUDE):
                continue
            z = zone_of(r)
            land[sid] = (r.get("鄉鎮市區", ""), [r.get("土地位置建物門牌", ""), int(dt.strftime("%Y%m%d")), None, None, zone_class(z),
                         None, round(lp, 2), round(tot / lp), round(tot), 0, 0, round(lp, 2), remark[:40], z, 0])
            continue
        if "建物" not in tg:
            continue
        rec = _building_rec(r, dt, tot, ("建物移轉總面積平方公尺", "建物移轉總面積"),
                            ("車位移轉總面積平方公尺",), "車位總價元")
        if rec and 5e3 < rec[7] < 1e7:
            sale[sid] = (r.get("鄉鎮市區", ""), rec)


def parse_b(path: Path, pre: dict):
    """預售屋買賣：排除已解約案件。"""
    for r in read_rows(path):
        if r.get("解約情形", "").strip():
            continue
        if any(k in r.get("備註", "") for k in SPECIAL) or "建物" not in r.get("交易標的", ""):
            continue
        dt = roc(r.get("交易年月日"))
        tot = num(r.get("總價元"))
        if not dt or tot <= 0:
            continue
        rec = _building_rec(r, dt, tot, ("建物移轉總面積平方公尺", "建物移轉總面積"),
                            ("車位移轉總面積平方公尺",), "車位總價元",
                            extra=(r.get("建案名稱", "") + " " + r.get("棟及號", "")).strip())
        if rec and 5e3 < rec[7] < 1e7:
            rec[5] = 0.0
            pre[r.get("編號") or f"{path.name}:{rec[0]}:{dt}"] = (r.get("鄉鎮市區", ""), rec)


def parse_c(path: Path, rent: dict):
    """不動產租賃：單價為每月元/坪（扣除車位租金與車位面積）。"""
    for r in read_rows(path):
        if any(k in r.get("備註", "") for k in SPECIAL) or "房屋" not in r.get("交易標的", ""):
            continue
        dt = roc(r.get("租賃年月日"))
        tot = num(r.get("總額元"))
        if not dt or tot <= 0:
            continue
        extra = "|".join(x for x in [r.get("出租型態", ""), "附傢俱" if r.get("有無附傢俱") == "有" else "",
                                     r.get("租賃住宅服務", "")] if x)
        rec = _building_rec(r, dt, tot, ("建物總面積平方公尺", "建物總面積"),
                            ("車位面積平方公尺",), "車位總額元", extra=extra)
        if rec and 50 < rec[7] < 10000:
            rent[r.get("編號") or f"{path.name}:{rec[0]}:{dt}"] = (r.get("鄉鎮市區", ""), rec)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="整理實價登錄資料供網頁使用")
    ap.add_argument("--current", action="store_true", help="先下載本期資料到 lvr_landcsv")
    ap.add_argument("--seasons", type=int, default=0, help="下載近 N 季歷史資料（已存在者略過）")
    ap.add_argument("--src", default=str(HERE / "lvr_landcsv"), help="本期資料夾")
    ap.add_argument("--history", default=str(HERE / "lvr_history"), help="歷史資料夾")
    ap.add_argument("--out", default=str(HERE / "web" / "data"), help="輸出資料夾")
    ap.add_argument("--max-months", type=int, default=30, help="只保留交易日期近 N 個月")
    a = ap.parse_args()
    src, hist, outdir = Path(a.src), Path(a.history), Path(a.out)

    if a.current:
        print("下載本期資料…")
        extract(fetch_zip(f"{BASE}/Download?type=zip&fileName=lvr_landcsv.zip"), src)
    for s in recent_seasons(a.seasons):
        d = hist / s
        if d.exists() and any(d.glob("*_lvr_land_a.csv")):
            print(f"{s} 已存在，略過")
            continue
        try:
            print(f"下載 {s} …", end=" ", flush=True)
            extract(fetch_zip(f"{BASE}/DownloadSeason?season={s}&type=zip&fileName=lvr_landcsv.zip"), d)
            print("完成")
            time.sleep(2)
        except Exception as e:
            print(f"失敗：{e}")

    # 本期另存一份，讓歷史逐旬累積
    bt = src / "build_time.xml"
    if bt.exists():
        stamp = datetime.fromtimestamp(bt.stat().st_mtime).strftime("%Y%m%d")
        snap = hist / f"cur_{stamp}"
        if not snap.exists():
            snap.mkdir(parents=True)
            for f in src.glob("*_lvr_land_[abc].csv"):
                shutil.copy2(f, snap / f.name)
            shutil.copy2(bt, snap / bt.name)

    dirs = [src] + sorted(p for p in hist.glob("*") if p.is_dir())
    cutoff = int((date.today().replace(day=1).toordinal() - a.max_months * 30.44))
    cutoff = int(date.fromordinal(cutoff).strftime("%Y%m%d"))
    outdir.mkdir(parents=True, exist_ok=True)
    index = {"built": datetime.now(TW).strftime("%Y-%m-%d %H:%M"), "sources": [p.name for p in dirs], "counties": {}}
    for code, name in COUNTIES.items():
        sets = {"sale": {}, "presale": {}, "rent": {}, "land": {}}
        for d in dirs:
            f = d / f"{code.lower()}_lvr_land_a.csv"
            if f.exists():
                parse_a(f, sets["sale"], sets["land"])
            f = d / f"{code.lower()}_lvr_land_b.csv"
            if f.exists():
                parse_b(f, sets["presale"])
            f = d / f"{code.lower()}_lvr_land_c.csv"
            if f.exists():
                parse_c(f, sets["rent"])
        rows = {k: sorted((x for x in v.values() if x[1][1] >= cutoff), key=lambda x: x[1][1]) for k, v in sets.items()}
        if not any(rows.values()):
            continue
        cdir = outdir / code
        cdir.mkdir(parents=True, exist_ok=True)
        dists = sorted({x[0] for v in rows.values() for x in v if x[0]})
        dinfo = {}
        for di in dists:
            doc = {"county": name, "district": di, "cols": COLS}
            pref = (name, name.replace("臺", "台"), di)
            for k, v in rows.items():
                out = []
                for x in v:
                    if x[0] != di:
                        continue
                    r = list(x[1])
                    a = r[0] or ""
                    for p in pref:
                        if a.startswith(p):
                            a = a[len(p):]
                    r[0] = a
                    out.append(r)
                doc[k] = out
            (cdir / f"{di}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            dinfo[di] = {k: len(doc[k]) for k in rows}
        dates = [x[1][1] for v in rows.values() for x in v]
        index["counties"][code] = {"name": name, **{k: len(v) for k, v in rows.items()},
                                   "from": min(dates), "to": max(dates), "districts": dinfo}
        print(f"{code} {name}：成屋 {len(rows['sale']):,}、預售 {len(rows['presale']):,}、租賃 {len(rows['rent']):,}、"
              f"土地 {len(rows['land']):,} 筆，{len(dists)} 個行政區")
    (outdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成，輸出到 {outdir}")


if __name__ == "__main__":
    main()
