"""价格采集 API"""
from fastapi import APIRouter, Depends
from backend.dependencies import get_current_user, require_admin, require_manager_or_admin
from datetime import datetime

router = APIRouter()


@router.post("/scrape-now")
async def trigger_scrape(
    user: dict = Depends(get_current_user)
):
    """手动触发价格抓取"""

    try:
        from backend.services.price_scraper import scrape_all_prices, save_prices_to_db
        import asyncio

        prices = await scrape_all_prices()
        db_path = "data/samsung_ops.db"
        result = await save_prices_to_db(db_path, prices)

        # 通知
        if result["changes"]:
            from backend.services.scheduler_service import _notify_admin
            lines = [f"【{c['platform']}】{c['model_code']} {c['spec']} ¥{c['old_price']:.0f}→¥{c['new_price']:.0f}" for c in result["changes"]]
            await _notify_admin("价格变动", "\n".join(lines[:10]))

        return {
            "status": "ok",
            "total": result["total"],
            "changes_count": len(result["changes"]),
            "changes": result["changes"][:20],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/latest")
async def get_latest_prices(
    user: dict = Depends(get_current_user)
):
    """获取最新价格"""
    from backend.models.database import get_db

    db = await get_db()
    cursor = await db.execute("""
        SELECT model_code, spec, platform, price,
               company_price, activity, note, updated_at
        FROM price_records
        ORDER BY model_code, spec, platform
    """)
    rows = [dict(r) for r in await cursor.fetchall()]

    # 按机型分组
    grouped = {}
    for r in rows:
        key = f"{r['model_code']}_{r['spec']}"
        if key not in grouped:
            grouped[key] = {
                "model_code": r["model_code"],
                "spec": r["spec"],
                "prices": {},
                "updated_at": r["updated_at"],
            }
        grouped[key]["prices"][r["platform"]] = {
            "price": r["price"],
            "company_price": r["company_price"],
            "activity": r["activity"],
            "note": r["note"],
        }
        if r["updated_at"] and r["updated_at"] > grouped[key].get("updated_at", ""):
            grouped[key]["updated_at"] = r["updated_at"]

    return list(grouped.values())


# 模型名称映射
_MODEL_INFO = {
    "S9380": {"name": "Galaxy S25", "series": "S 系列"},
    "S9420": {"name": "Galaxy S26", "series": "S 系列"},
    "S9470": {"name": "Galaxy S26+", "series": "S 系列"},
    "S9480": {"name": "Galaxy S26 Ultra", "series": "S 系列"},
    "ZFOLD7": {"name": "Galaxy Z Fold7", "series": "折叠屏"},
    "ZFLIP7": {"name": "Galaxy Z Flip7", "series": "折叠屏"},
    "W26": {"name": "Galaxy W26", "series": "心系天下"},
    "A56": {"name": "Galaxy A56", "series": "A 系列"},
    "A57": {"name": "Galaxy A57", "series": "A 系列"},
}


@router.get("/dashboard")
async def price_dashboard(
    user: dict = Depends(get_current_user)
):
    """价格看板 - 返回前端所需格式"""
    from backend.models.database import get_db

    db = await get_db()
    cursor = await db.execute("""
        SELECT model_code, spec, platform, price,
               company_price, activity, note, updated_at
        FROM price_records
        ORDER BY model_code, spec, platform
    """)
    rows = [dict(r) for r in await cursor.fetchall()]

    # 按机型分组 → 按规格分组
    model_map: dict[str, dict] = {}
    for r in rows:
        mc = r["model_code"]
        if mc not in model_map:
            model_map[mc] = {
                "code": mc,
                "name": _MODEL_INFO.get(mc, {}).get("name", mc),
                "series": _MODEL_INFO.get(mc, {}).get("series", "其他"),
                "specs": {},
            }
        spec_key = r["spec"]
        specs = model_map[mc]["specs"]
        if spec_key not in specs:
            specs[spec_key] = {
                "spec": r["spec"],
                "company_price": r["company_price"] or 0,
                "activity": r["activity"] or "",
                "prices": {},
            }

        specs[spec_key]["prices"][r["platform"]] = {
            "price": r["price"] or 0,
            "time": r["updated_at"] or "",
        }

    # 展平 specs dict → list
    models = []
    for mc, mdata in sorted(model_map.items()):
        entry = {
            "code": mdata["code"],
            "name": mdata["name"],
            "series": mdata["series"],
            "specs": list(mdata["specs"].values()),
        }
        models.append(entry)

    return {"models": models}
