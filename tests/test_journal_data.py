"""
单元测试: journal_data.py 的期刊匹配逻辑。
"""
from journal_data import lookup_journal, normalize_journal_name


def test_normalize_strips_punctuation_and_case():
    assert normalize_journal_name("Nature.") == "nature"
    assert normalize_journal_name("BMJ (Clinical Research Ed.)") == "bmj (clinical research ed)"
    assert normalize_journal_name("  Multiple   Spaces  ") == "multiple spaces"


def test_lookup_exact_match_known_journal():
    result = lookup_journal("Nature Medicine")
    assert result is not None
    assert result["quartile"] == "Q1"
    assert result["if"] > 0


def test_lookup_case_insensitive():
    result = lookup_journal("nature medicine")
    assert result is not None
    assert result["quartile"] == "Q1"


def test_lookup_falls_back_to_abbreviation():
    # full name 未命中,但缩写命中
    result = lookup_journal(full_name="Some Unlisted Journal Name", abbrev_name="JAMA")
    assert result is not None
    assert result["quartile"] == "Q1"


def test_lookup_unknown_journal_returns_none():
    result = lookup_journal("A Completely Made Up Journal Of Nonsense 2099")
    assert result is None


def test_lookup_handles_empty_input():
    assert lookup_journal("", "") is None
    assert lookup_journal(None, None) is None


# ---- 回归测试: 之前的"子串包含匹配"兜底逻辑曾把完全不相关的期刊
# 错误匹配到内置数据库里的短期刊名(如 "Science" / "Cancer"),
# 导致这些期刊被打上错误的高影响因子。这里锁定几个真实抓到的错误案例,
# 确保精确匹配版本不会再犯同样的错误。

def test_lookup_does_not_false_match_generic_word_science():
    # "International journal of molecular sciences" 不应该被
    # 误判为 "Science"(56.9)—— 之前的 bug 正是如此。
    result = lookup_journal("International journal of molecular sciences")
    assert result is None


def test_lookup_does_not_false_match_translational_science():
    result = lookup_journal("Progress in molecular biology and translational science")
    assert result is None


def test_lookup_does_not_false_match_cancer_journal():
    # 真实期刊 "Cancer"(IF约6)不应该被误判为 "Nature Reviews Cancer"(78.5)
    result = lookup_journal("Cancer")
    assert result is None


def test_lookup_does_not_false_match_journal_of_hypertension():
    # "Journal of Hypertension" 和 "Hypertension" 是两本不同期刊,
    # 不应该互相匹配。
    result = lookup_journal("Journal of Hypertension")
    assert result is None
    # 但 "Hypertension" 本身应该精确命中
    assert lookup_journal("Hypertension") is not None