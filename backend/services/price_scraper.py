"""
三星手机价格抓取服务 v2 — 使用 urllib，无第三方依赖
"""
import re, json, ssl
import sqlite3
from typing import Optional
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

# SSL 跳过验证（内网环境）
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/json",
}

# ── 九机网 product ID ────────────────────────────
JIUJI = {
    ("S9420","12+256G"): "492798", ("S9470","12+256G"): "492820",
    ("S9470","12+512G"): "492821", ("S9480","12+256G"): "492822",
    ("S9480","12+512G"): "492823", ("S9480","16+1TB"): "492824",
    ("ZFOLD7","12+256G"): "478720", ("ZFOLD7","12+512G"): "478721",
    ("ZFLIP7","12+256G"): "478722", ("ZFLIP7","12+512G"): "478723",
    ("W26","16+512G"): "478725", ("W26","16+1TB"): "478724",
}

# ── 京东 SKU ──────────────────────────────────────
JD_SKU = {
    ("S9420","12+256G"): "100013281904", ("S9470","12+256G"): "100013281908",
    ("S9470","12+512G"): "100013281910", ("S9480","12+256G"): "100013281914",
    ("S9480","12+512G"): "100013281916", ("S9480","16+1TB"): "100013281918",
    ("ZFOLD7","12+256G"): "100013281922", ("ZFOLD7","12+512G"): "100013281924",
    ("ZFLIP7","12+256G"): "100013281926", ("ZFLIP7","12+512G"): "100013281928",
    ("W26","16+512G"): "100013281930", ("W26","16+1TB"): "100013281932",
}

# ── 参考价（实在抓不到时使用）─────────────────
FALLBACK = {
    ("S9420","12+256G"): 4299, ("S9470","12+256G"): 5299,
    ("S9470","12+512G"): 5899, ("S9480","12+256G"): 6599,
    ("S9480","12+512G"): 7299, ("S9480","16+1TB"): 8999,
    ("ZFOLD7","12+256G"): 12999, ("ZFOLD7","12+512G"): 13999,
    ("ZFLIP7","12+256G"): 7499, ("ZFLIP7","12+512G"): 7999,
    ("W26","16+512G"): 15999, ("W26","16+1TB"): 17999,
}


def fetch_url(url: str) -> str:
    """抓取页面内容"""
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, context=CTX, timeout=3) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ⚠ {url[:60]}: {e}")
        return ""


def scrape_jiuji(model_code: str, spec: str) -> Optional[dict]:
    """抓取九机网价格 — v3: 域名改为 9ji.com，提取 Vue SSR JSON 中的 price 字段"""
    pid = JIUJI.get((model_code, spec))
    if not pid:
        return None

    html = fetch_url(f"https://www.9ji.com/product/{pid}.html")
    if not html:
        return None

    # 九机网 SSR 渲染，价格在嵌入的 JSON 中： "price":"5699"
    for pat in [
        r'"price"\s*:\s*"(\d+)"',          # 新版 JSON 格式
        r'"price"\s*:\s*(\d+)',             # 旧版数字格式
        r'"priceSale"\s*:\s*"(\d+)"',       # 促销价
        r'售价.*?(\d{4,6})',                 # 中文价格
        r'<em[^>]*>(\d{4,6})</em>',         # HTML 标签
    ]:
        # 取第一个匹配到的有效价格（JSON 中可能有多处，取第一处主价格）
        for m in re.finditer(pat, html):
            price = float(m.group(1))
            if 1000 < price < 50000:
                print(f"  九机 {model_code} {spec}: ¥{price:,.0f}")
                return {"model_code": model_code, "spec": spec, "platform": "九机网", "price": price}
    return None


def scrape_jd(model_code: str, spec: str) -> Optional[dict]:
    """抓取京东价格"""
    sku = JD_SKU.get((model_code, spec))
    if not sku:
        return None

    # 京东价格 API
    html = fetch_url(f"https://p.3.cn/prices/mgets?skuIds=J_{sku}")
    if html:
        try:
            data = json.loads(html)
            if data and len(data) > 0:
                p = float(data[0].get("p", 0))
                if p > 0:
                    print(f"  京东 {model_code} {spec}: ¥{p:,.0f}")
                    return {"model_code": model_code, "spec": spec, "platform": "京东", "price": p}
        except (json.JSONDecodeError, KeyError):
            pass

    return None


def scrape_all_sync() -> list:
    """同步抓取所有机型价格"""
    all_prices = []

    for (model, spec), _ in JIUJI.items():
        # 九机
        r1 = scrape_jiuji(model, spec)
        if r1:
            all_prices.append(r1)

        # 京东
        r2 = scrape_jd(model, spec)
        if r2:
            all_prices.append(r2)

    # 如果完全没抓到，使用参考价（首次填充）
    if not all_prices:
        print("⚠ 网络抓取均失败，使用参考价填充")
        for (model_code, spec), price in FALLBACK.items():
            all_prices.append({
                "model_code": model_code, "spec": spec,
                "platform": "参考价", "price": price,
            })

    return all_prices


def save_to_db(db_path: str, prices: list) -> dict:
    """保存价格到数据库"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    changes = []

    try:
        for p in prices:
            # 查旧价
            cur.execute(
                "SELECT price FROM price_records WHERE model_code=? AND spec=? AND platform=?",
                (p["model_code"], p["spec"], p["platform"]))
            row = cur.fetchone()

            if row:
                old_price = row[0]
                if abs(old_price - p["price"]) > 0.001:
                    changes.append({
                        "model_code": p["model_code"], "spec": p["spec"],
                        "platform": p["platform"], "old_price": old_price,
                        "new_price": p["price"], "diff": p["price"] - old_price,
                    })

            cur.execute("""
                INSERT INTO price_records (model_code, spec, platform, price, updated_at)
                VALUES (?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(model_code, spec, platform)
                DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at
            """, (p["model_code"], p["spec"], p["platform"], p["price"]))

        conn.commit()
    finally:
        conn.close()

    return {"total": len(prices), "changes": changes}
