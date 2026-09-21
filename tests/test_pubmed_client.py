"""
单元测试: pubmed_client.py 中不依赖网络的纯函数(年份解析、数据合并、
按年份分层抽样的调度逻辑)。
不测试 esearch/esummary/efetch 本身真实发出的网络请求 —— 那部分属于集成
测试范畴;这里用 unittest.mock.patch 打桩掉 esearch,只验证
stratified_search_by_year 的调度/去重/截断逻辑是否正确。
"""
from unittest.mock import patch

import pytest

from pubmed_client import _extract_year, _merge, stratified_search_by_year


def test_extract_year_from_full_date():
    assert _extract_year("2023 Jan 15") == 2023


def test_extract_year_from_year_only():
    assert _extract_year("2021") == 2021


def test_extract_year_handles_missing_date():
    assert _extract_year(None) is None
    assert _extract_year("") is None


def test_extract_year_handles_garbage_string():
    assert _extract_year("no date here") is None


def test_merge_builds_expected_fields():
    summaries = [{
        "uid": "123",
        "title": "A <i>Study</i> of Something",
        "pubdate": "2022 Jun",
        "fulljournalname": "Nature Medicine",
        "source": "Nat Med",
        "authors": [{"name": "Smith J"}, {"name": "Lee K"}],
    }]
    abstracts = {"123": "This is the abstract text."}

    merged = _merge(summaries, abstracts)

    assert len(merged) == 1
    rec = merged[0]
    assert rec["pmid"] == "123"
    assert rec["title"] == "A Study of Something"  # HTML 标签被剥离
    assert rec["year"] == 2022
    assert rec["journal"] == "Nature Medicine"
    assert rec["authors"] == "Smith J, Lee K"
    assert rec["abstract"] == "This is the abstract text."
    assert rec["if"] is not None  # Nature Medicine 应命中内置数据库
    assert rec["quartile"] == "Q1"
    assert rec["url"] == "https://pubmed.ncbi.nlm.nih.gov/123/"


def test_merge_skips_records_without_uid_or_title():
    summaries = [
        {"uid": "1", "title": ""},          # 无标题,应跳过
        {"uid": "", "title": "Has title"},  # 无uid,应跳过
        {"uid": "2", "title": "Valid"},
    ]
    merged = _merge(summaries, {})
    assert len(merged) == 1
    assert merged[0]["pmid"] == "2"


def test_merge_marks_unknown_journal_as_not_indexed():
    summaries = [{
        "uid": "999",
        "title": "Some paper",
        "pubdate": "2020",
        "fulljournalname": "A Totally Unlisted Journal",
        "source": "",
        "authors": [],
    }]
    merged = _merge(summaries, {})
    assert merged[0]["if"] is None
    assert merged[0]["quartile"] == "未收录"


def _fake_esearch_factory(per_year_ids: dict[int, list[str]], total_count: int):
    """构造一个假的 esearch,用于测试 stratified_search_by_year 的调度逻辑,
    不发出任何真实网络请求。"""
    def _fake_esearch(term, retmax, api_key=None, mindate=None, maxdate=None):
        if mindate is None:
            # 无年份限制的探测调用,只用来拿总命中数
            return [], total_count
        year = int(mindate.split("/")[0])
        ids = per_year_ids.get(year, [])
        return ids[:retmax], 0
    return _fake_esearch


@patch("pubmed_client.time.sleep", return_value=None)
def test_stratified_search_collects_ids_across_multiple_years(_mock_sleep):
    per_year_ids = {
        2026: ["a1", "a2"],
        2025: ["b1", "b2"],
        2024: ["c1", "c2"],
        2023: ["d1", "d2"],
        2022: ["e1", "e2"],
        2021: ["f1", "f2"],
    }
    fake = _fake_esearch_factory(per_year_ids, total_count=500)
    with patch("pubmed_client.esearch", side_effect=fake):
        ids, total = stratified_search_by_year(
            "CRISPR", retmax=12, current_year=2026, year_buckets=6,
        )
    assert total == 500
    # 应该从每一年都拿到了文献,而不是全部挤在最新一年
    years_represented = {pmid[0] for pmid in ids}  # 用前缀字母代表年份桶
    assert years_represented == {"a", "b", "c", "d", "e", "f"}
    assert len(ids) == 12


@patch("pubmed_client.time.sleep", return_value=None)
def test_stratified_search_deduplicates_ids(_mock_sleep):
    # 同一个 pmid 在不同年份桶重复出现(理论上不该发生,但要保证去重是安全的)
    per_year_ids = {
        2026: ["dup", "a2"],
        2025: ["dup", "b2"],
        2024: [], 2023: [], 2022: [], 2021: [],
    }
    fake = _fake_esearch_factory(per_year_ids, total_count=10)
    with patch("pubmed_client.esearch", side_effect=fake):
        ids, _ = stratified_search_by_year("kw", retmax=20, current_year=2026, year_buckets=6)
    assert ids.count("dup") == 1


@patch("pubmed_client.time.sleep", return_value=None)
def test_stratified_search_truncates_to_retmax(_mock_sleep):
    per_year_ids = {y: [f"{y}-{i}" for i in range(10)] for y in range(2021, 2027)}
    fake = _fake_esearch_factory(per_year_ids, total_count=1000)
    with patch("pubmed_client.esearch", side_effect=fake):
        ids, _ = stratified_search_by_year("kw", retmax=7, current_year=2026, year_buckets=6)
    assert len(ids) == 7


@patch("pubmed_client.time.sleep", return_value=None)
def test_stratified_search_returns_empty_when_no_hits(_mock_sleep):
    fake = _fake_esearch_factory({}, total_count=0)
    with patch("pubmed_client.esearch", side_effect=fake):
        ids, total = stratified_search_by_year("nonexistent kw xyz", retmax=50)
    assert ids == []
    assert total == 0


def test_get_with_retry_recovers_from_transient_failure():
    """模拟 NCBI 偶发的连接中断(如 SSLEOFError),验证会自动重试并最终成功,
    而不是让一次网络抖动就搞垮整次检索。"""
    import requests as requests_module
    from pubmed_client import _get_with_retry

    call_count = {"n": 0}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def flaky_get(url, params=None, timeout=None):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise requests_module.exceptions.ConnectionError("simulated SSL EOF")
        return FakeResponse()

    with patch("pubmed_client.requests.get", side_effect=flaky_get), \
         patch("pubmed_client.time.sleep", return_value=None):
        resp = _get_with_retry("https://fake.example.com", {}, timeout=10)

    assert call_count["n"] == 3
    assert isinstance(resp, FakeResponse)


def test_get_with_retry_raises_after_exhausting_attempts():
    import requests as requests_module
    from pubmed_client import _get_with_retry

    def always_fails(url, params=None, timeout=None):
        raise requests_module.exceptions.ConnectionError("permanently down")

    with patch("pubmed_client.requests.get", side_effect=always_fails), \
         patch("pubmed_client.time.sleep", return_value=None):
        with pytest.raises(requests_module.exceptions.ConnectionError):
            _get_with_retry("https://fake.example.com", {}, timeout=10)


def test_esearch_with_retmax_zero_returns_empty_ids_but_real_count():
    """探测总命中数的调用(retmax=0)不应该返回任何 id,只应该返回 count。"""
    from pubmed_client import esearch

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"esearchresult": {"idlist": ["1"], "count": "12345"}}

    with patch("pubmed_client.requests.get", return_value=FakeResponse()):
        ids, count = esearch("some term", 0)

    assert ids == []
    assert count == 12345