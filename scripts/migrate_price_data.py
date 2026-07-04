"""
数据迁移脚本：将 price_config.json 导入 SQLite price_records 表
用法: python migrate_price_data.py
"""
import json
import sqlite3
import os
import sys

# 路径
PRICE_CONFIG = os.path.join(os.path.expanduser("~"), ".workbuddy", "data", "price_config.json")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "samsung_ops.db")

def migrate():
    # 读取价格配置
    with open(PRICE_CONFIG, 'r', encoding='utf-8') as f:
        config = json.load(f)

    prices = config.get('prices', {})
    update_time = config.get('update_time', '')

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    imported = 0
    for model_code, model_data in prices.items():
        specs = model_data.get('specs', {})
        for spec, spec_data in specs.items():
            company_price = spec_data.get('company_price', 0)
            activity = spec_data.get('activity', '')

            # 遍历各平台
            for platform in ['京东自营', '九机网', '抖音小时达', '美团闪购']:
                platform_data = spec_data.get(platform, {})
                price = platform_data.get('price', 0)
                note = platform_data.get('note', '')
                time = platform_data.get('time', update_time)

                if price <= 0 and not note:
                    continue

                # 只在京东自营记录上存储 company_price 和 activity
                cp = company_price if platform == '京东自营' else 0
                act = activity if platform == '京东自营' else ''

                cur.execute("""
                    INSERT INTO price_records (model_code, spec, platform, price, company_price, activity, note, updated_at, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(model_code, spec, platform)
                    DO UPDATE SET price=excluded.price, company_price=excluded.company_price,
                                 activity=excluded.activity, note=excluded.note,
                                 updated_at=excluded.updated_at
                """, (model_code, spec, platform, price, cp, act, note, time))
                imported += 1

    conn.commit()
    conn.close()

    print(f"Migration complete: {imported} price records imported")
    print(f"Source: {PRICE_CONFIG}")
    print(f"Database: {DB_PATH}")

if __name__ == '__main__':
    if not os.path.exists(PRICE_CONFIG):
        print(f"Error: {PRICE_CONFIG} not found")
        sys.exit(1)
    migrate()
