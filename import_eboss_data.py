"""导入亿博士数据到数据库（只使用最新零售明细文件，避免旧文件覆盖新数据）"""
import sys
sys.path.insert(0, r'D:\Workbuudy\samsung-ops')
from backend.services.eboss_parser import scan_eboss_directory, parse_retail_detail, parse_trade_in
import sqlite3

DB = r'D:\Workbuudy\samsung-ops\data\samsung_ops.db'

print('=== 导入亿博士数据到销售看板 ===')

files = scan_eboss_directory(r'C:\eBoss\Local')
conn = sqlite3.connect(DB)
cur = conn.cursor()

total = 0

# Step 0: 只取最新零售明细文件（旧文件数据不完整，会被最新文件覆盖）
retail_detail_files = [f for f in files if 'retail_detail' in f['filetype']]
if not retail_detail_files:
    print('[WARN] 未找到零售明细文件')
else:
    # 按文件名中的序号排序，取最大的（最新的）
    retail_detail_files.sort(key=lambda f: f['filename'], reverse=True)
    latest_retail = retail_detail_files[0]
    print(f'\n[INFO] 只处理最新零售明细: {latest_retail["filename"]}')

    records = parse_retail_detail(latest_retail['filepath'])
    if records:
        dates = list(set(r['date'] for r in records))
        ph = ','.join('?' * len(dates))
        cur.execute(f'DELETE FROM daily_sales WHERE date IN ({ph}) AND source="eboss"', dates)
        print(f'  清除旧数据: {cur.rowcount} 条')

        n = 0
        for r in records:
            cur.execute(
                'INSERT OR REPLACE INTO daily_sales(date,store_id,phone_sales,ncme_sales,phone_qty,key_model_qty,accessory_sales,trade_in_qty,source) VALUES(?,?,?,?,?,?,?,0,"eboss")',
                (r['date'], r['store_id'], r['phone_sales'], r['ncme_sales'], r['phone_qty'], r['key_model_qty'], r['accessory_sales']))
            n += 1
        conn.commit()
        total += n
        print(f'  导入: {n} 条')

    # 如果有更早月份的数据在历史文件中（最新文件不含），补充导入
    if len(retail_detail_files) > 1:
        latest_months = set(r['date'][:7] for r in records) if records else set()
        oldest_file = retail_detail_files[-1]  # 最旧的文件通常有更多历史数据
        if oldest_file['filename'] != latest_retail['filename']:
            old_records = parse_retail_detail(oldest_file['filepath'])
            old_months = set(r['date'][:7] for r in old_records) if old_records else set()
            missing_months = old_months - latest_months
            if missing_months:
                missing_records = [r for r in old_records if r['date'][:7] in missing_months]
                print(f'\n[INFO] 补充历史月份 {sorted(missing_months)}: {len(missing_records)} 条')
                for mp in missing_months:
                    cur.execute("DELETE FROM daily_sales WHERE source='eboss' AND date LIKE ?", (mp + '%',))
                for r in missing_records:
                    cur.execute(
                        'INSERT INTO daily_sales(date,store_id,phone_sales,ncme_sales,phone_qty,key_model_qty,accessory_sales,trade_in_qty,source) VALUES(?,?,?,?,?,?,?,0,"eboss")',
                        (r['date'], r['store_id'], r['phone_sales'], r['ncme_sales'], r['phone_qty'], r['key_model_qty'], r['accessory_sales']))
                conn.commit()
                total += len(missing_records)

# Step 2: 导入回收单
for f in files:
    if f['filetype'] != 'trade_in':
        continue
    print(f'\n处理: {f["filename"]}')
    records = parse_trade_in(f['filepath'])
    if not records:
        continue
    n = 0
    for r in records:
        cur.execute(
            'INSERT INTO daily_sales(date,store_id,phone_sales,ncme_sales,phone_qty,key_model_qty,accessory_sales,trade_in_qty,source) VALUES(?,?,0,0,0,0,0,?,"eboss") ON CONFLICT(date,store_id) DO UPDATE SET trade_in_qty=excluded.trade_in_qty',
            (r['date'], r['store_id'], r['trade_in_qty']))
        n += 1
    conn.commit()
    print(f'  更新回收: {n} 条')

# Step 3: 验证
cur.execute('SELECT COUNT(*), SUM(phone_sales), SUM(phone_qty), SUM(key_model_qty) FROM daily_sales')
cnt, sales, qty, w26 = cur.fetchone()
print(f'\n=== 导入完成 ===')
print(f'总记录: {cnt} 条')
print(f'手机销售额: {sales or 0:.0f}')
print(f'手机台量: {qty or 0}')
print(f'重点机型(W26): {w26 or 0}')
print(f'\n✅ 数据已更新到数据库，请刷新销售看板页面')

conn.close()
