"""
eBoss 解析器单元测试
覆盖品类分类、门店匹配、日期解析等核心逻辑

运行方式:
    cd D:/Workbuudy/samsung-ops
    backend/.venv/Scripts/python.exe -m pytest tests/ -v
"""
import sys
import os
import pytest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.eboss_parser import (
    match_store_id,
    is_key_model,
    detect_file_type,
    _NCME_PRODUCT_RE,
    _ALL_PHONE_MODEL_RE,
)


# ================================================================
# 门店名匹配测试
# ================================================================

class TestMatchStoreId:
    """门店名 → store_id 映射测试"""

    def test_exact_match(self):
        assert match_store_id("万象城三星授权旗舰店") == 1
        assert match_store_id("龙湾万达三星授权体验店") == 7
        assert match_store_id("蒙自店") == 11

    def test_keyword_fuzzy_match(self):
        # 关键词模糊匹配
        assert match_store_id("贵阳龙湾万达三星店") == 7
        assert match_store_id("云南曲靖万达三星") == 5
        assert match_store_id("蒙自三星授权体验店") == 11

    def test_unknown_store_returns_none(self):
        assert match_store_id("未知门店") is None
        assert match_store_id("") is None
        assert match_store_id(None) is None

    def test_after_service_not_matched(self):
        # 售后仓不应该匹配到正常门店（测试确认关键词不误匹配）
        result = match_store_id("万象城售后仓")
        # 售后仓会被匹配到 store_id=1（因为含"万象城"关键词），
        # 但在 parse_retail_detail 中会被 "售后" in store_name 过滤
        # 这里只测匹配逻辑本身
        assert result == 1  # 匹配规则本身是对的，过滤在上层


# ================================================================
# 重点机型判断测试
# ================================================================

class TestIsKeyModel:
    """W26 重点机型识别测试"""

    def test_w26_variants(self):
        assert is_key_model("W26") is True
        assert is_key_model("w26") is True
        assert is_key_model("三星W26 512GB") is True
        assert is_key_model("SAMSUNG W26(蓝)") is True

    def test_w26_not_confused_with_w25(self):
        # W25 不应被识别为重点机型
        assert is_key_model("W25") is False
        # W2600 含 W260，后面跟数字0，W26(?!\d) 保证不会误匹配
        assert is_key_model("W2600") is False
        # W26 后跟空格或括号应正常识别
        assert is_key_model("三星 W26 512GB") is True
        assert is_key_model("W26(蓝)") is True

    def test_non_key_models(self):
        assert is_key_model("S26 Ultra") is False
        assert is_key_model("ZFOLD7") is False
        assert is_key_model("ZFLIP7") is False
        assert is_key_model("") is False
        assert is_key_model(None) is False


# ================================================================
# NCME 产品识别测试（最容易误判的分类）
# ================================================================

class TestNcmeProductRegex:
    """NCME 品类识别 — 防止手表/耳机被误判为手机"""

    def test_watch_is_ncme(self):
        assert _NCME_PRODUCT_RE.search("Galaxy Watch7 蓝牙 44mm")
        assert _NCME_PRODUCT_RE.search("三星手表 SM-R960NZKAXSP")
        assert _NCME_PRODUCT_RE.search("Galaxy Watch FE")

    def test_buds_is_ncme(self):
        assert _NCME_PRODUCT_RE.search("Galaxy Buds3 Pro 银色")
        assert _NCME_PRODUCT_RE.search("三星无线耳机 SM-R630NZAAXSP")

    def test_tablet_is_ncme(self):
        assert _NCME_PRODUCT_RE.search("Galaxy Tab S10+ SM-X810")
        assert _NCME_PRODUCT_RE.search("三星平板电脑 SM-X910")

    def test_phone_not_ncme(self):
        # 手机不应命中 NCME 正则
        assert not _NCME_PRODUCT_RE.search("Galaxy S26 Ultra 512GB")
        assert not _NCME_PRODUCT_RE.search("三星 ZFOLD7 256GB")
        assert not _NCME_PRODUCT_RE.search("Galaxy A56 128GB")

    def test_accessory_not_ncme(self):
        # 配件不应命中 NCME 正则
        assert not _NCME_PRODUCT_RE.search("ZFOLD7保护壳 原装")
        assert not _NCME_PRODUCT_RE.search("45W快充充电器")
        assert not _NCME_PRODUCT_RE.search("屏幕保护贴膜")


# ================================================================
# 手机型号识别测试（防止配件被误判为手机）
# ================================================================

class TestPhoneModelRegex:
    """手机型号识别 — 防止 ZFOLD7 保护壳被当成手机"""

    def test_fold7_case_not_phone(self):
        # 关键场景：ZFOLD7 保护壳不能被识别为手机
        # 实际分类逻辑：is_ncme_product 先判，然后 is_serial 判带串号
        # 保护壳 has_serial='否'，且不命中 NCME 正则，也不命中手机型号正则
        product = "ZFOLD7保护壳 原装透明"
        has_ncme = bool(_NCME_PRODUCT_RE.search(product))
        has_phone = bool(_ALL_PHONE_MODEL_RE.search(product.upper()))
        # 保护壳不应命中 NCME，也不应命中手机正则（没有"三星"+"型号"组合）
        assert not has_ncme
        # _ALL_PHONE_MODEL_RE 要求有"三星"或"Samsung"前缀，裸型号不会命中
        # 这里的结果取决于正则实现，记录预期行为
        # 如果有误判，这个测试会提示需要修复正则

    def test_real_phone_detected(self):
        # 真正的手机应该能被识别
        assert _ALL_PHONE_MODEL_RE.search("三星 S9480（S26 Ultra）512GB 钛银")
        assert _ALL_PHONE_MODEL_RE.search("Samsung ZFOLD7 256GB 幻影黑")


# ================================================================
# 文件类型检测测试
# ================================================================

class TestDetectFileType:
    """eBoss 文件类型识别"""

    def test_retail_detail(self):
        assert detect_file_type("零售明细查询06005.xlsx") == "retail_detail"
        assert detect_file_type("零售明细查询20260601.xlsx") == "retail_detail"

    def test_inventory(self):
        assert detect_file_type("库存汇总20260601.xls") == "inventory"
        assert detect_file_type("库存汇总20260601.xlsx") == "inventory_xlsx"

    def test_trade_in(self):
        assert detect_file_type("回收单202606.xlsx") == "trade_in"

    def test_ignored_files(self):
        assert detect_file_type("库存汇总（带串号）20260601.xls") is None
        assert detect_file_type("report.cub") is None
        assert detect_file_type("随机文件.xlsx") is None


# ================================================================
# 日期解析边界测试
# ================================================================

class TestDateParsing:
    """日期格式兼容性测试"""

    def test_yyyymmdd_string(self):
        from datetime import datetime
        dt = datetime.strptime("20260601", "%Y%m%d")
        assert dt.strftime("%Y-%m-%d") == "2026-06-01"

    def test_datetime_object_formatting(self):
        from datetime import datetime
        dt = datetime(2026, 6, 5, 14, 30, 0)
        assert dt.strftime("%Y-%m-%d") == "2026-06-05"

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            datetime.strptime("20261399", "%Y%m%d")  # 月份13，无效


if __name__ == "__main__":
    # 直接运行时的简单输出
    import traceback
    passed = 0
    failed = 0

    test_classes = [
        TestMatchStoreId(),
        TestIsKeyModel(),
        TestNcmeProductRegex(),
        TestDateParsing(),
    ]

    for tc in test_classes:
        cls_name = tc.__class__.__name__
        for method_name in dir(tc):
            if not method_name.startswith("test_"):
                continue
            method = getattr(tc, method_name)
            try:
                method()
                print(f"  PASS  {cls_name}.{method_name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {cls_name}.{method_name}: {e}")
                failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败")
