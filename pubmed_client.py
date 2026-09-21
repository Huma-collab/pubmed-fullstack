"""
pubmed_client.py
封装 NCBI E-utilities 的 esearch / esummary / efetch 调用,
在服务端完成检索,避免浏览器直连 NCBI 时的 CORS / 速率限制问题。

年份分层抽样说明:
PubMed 的默认排序(不管是 date 还是 relevance/"Best Match")都天然偏向
新发表的文献 —— relevance 算法本身就把发表时间作为权重之一,对于
CRISPR、AI 这类近几年论文数量暴涨的热门领域,"最相关"和"最新"高度重合。
如果直接拿 retmax 条最相关结果去统计"按年份分布",几乎必然全部集中在
最近一年,统计图表就失去意义。所以这里改为按年份分桶抽样: 对最近 N 年
(默认6年)分别发起检索,每年份取一部分文献,再合并、去重、按需截断到
retmax 条 —— 这样"按年份统计"才是真正有代表性的分布,而不是排序算法的
副作用。
"""
import re
import time
from datetime import datetime
import xml.etree.ElementTree as ET

import requests

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

YEAR_BUCKETS = 6  # 分层抽样覆盖的年份数(含当前年)

# NCBI 的 HTTPS 端点偶尔会出现连接中途被重置(SSLEOFError/ConnectionError)
# 这类瞬时网络错误,和 retmax 大小、请求内容都无关。给所有对 eutils 的请求
# 加一层简单的重试 + 退避,避免整次检索因为一次网络抖动而直接失败。
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.8


def _get_with_retry(url: str, params: dict, timeout: int) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise last_exc  # type: ignore[misc]


def _rate_delay(api_key: str | None) -> float:
    # 有 API key: 上限10次/秒,留余量用 0.12s;无 key: 上限3次/秒,用 0.35s
    return 0.12 if api_key else 0.35


def esearch(
    term: str,
    retmax: int,
    api_key: str | None = None,
    mindate: str | None = None,
    maxdate: str | None = None,
) -> tuple[list[str], int]:
    # retmax=0 在 esearch 上是合法参数(esearchresult.count 仍会返回),
    # 但个别网络环境下用 0 会触发异常响应;这里统一至少请求 1 条,
    # 只探测总数时忽略返回的 idlist 即可,更稳妥。
    effective_retmax = max(retmax, 1)
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": effective_retmax,
        "term": term,
    }
    if mindate and maxdate:
        params["datetype"] = "pdat"
        params["mindate"] = mindate
        params["maxdate"] = maxdate
    if api_key:
        params["api_key"] = api_key
    resp = _get_with_retry(f"{EUTILS}/esearch.fcgi", params, timeout=20)
    data = resp.json()
    result = data.get("esearchresult", {})
    ids = result.get("idlist", [])
    count = int(result.get("count", "0") or 0)
    return (ids if retmax > 0 else []), count


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def stratified_search_by_year(
    term: str,
    retmax: int,
    api_key: str | None = None,
    current_year: int | None = None,
    year_buckets: int = YEAR_BUCKETS,
) -> tuple[list[str], int]:
    """按年份分层抽样检索 PMID,避免结果全部集中在最近一年。

    返回 (去重后的 PMID 列表(截断到 retmax), 该关键词的 PubMed 总命中数)。
    总命中数来自一次不带年份限制的检索(retmax=0),独立于分层抽样过程。
    """
    current_year = current_year or datetime.now().year
    _, total_count = esearch(term, 0, api_key)

    if total_count == 0:
        return [], 0

    years = list(range(current_year, current_year - year_buckets, -1))
    per_year = max(1, -(-retmax // len(years)))  # 向上取整,保证凑够 retmax

    seen: set[str] = set()
    ordered_ids: list[str] = []
    delay = _rate_delay(api_key)

    for year in years:
        ids, _ = esearch(
            term, per_year, api_key,
            mindate=f"{year}/01/01", maxdate=f"{year}/12/31",
        )
        for pmid in ids:
            if pmid not in seen:
                seen.add(pmid)
                ordered_ids.append(pmid)
        time.sleep(delay)

    return ordered_ids[:retmax], total_count


def esummary_batch(ids: list[str], api_key: str | None = None) -> list[dict]:
    params = {"db": "pubmed", "retmode": "json", "id": ",".join(ids)}
    if api_key:
        params["api_key"] = api_key
    resp = _get_with_retry(f"{EUTILS}/esummary.fcgi", params, timeout=30)
    data = resp.json()
    result = data.get("result", {})
    out = []
    for uid in result.get("uids", []):
        rec = result.get(uid)
        if rec:
            out.append(rec)
    return out


def efetch_abstracts_batch(ids: list[str], api_key: str | None = None) -> dict[str, str]:
    params = {"db": "pubmed", "retmode": "xml", "rettype": "abstract", "id": ",".join(ids)}
    if api_key:
        params["api_key"] = api_key
    resp = _get_with_retry(f"{EUTILS}/efetch.fcgi", params, timeout=30)
    root = ET.fromstring(resp.text)
    out = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        pmid = pmid_el.text
        abstract_texts = [
            (el.text or "") for el in article.findall(".//AbstractText")
        ]
        out[pmid] = " ".join(t for t in abstract_texts if t)
    return out


def fetch_all(term: str, retmax: int, api_key: str | None = None):
    """完整流程: 按年份分层检索 -> esummary(分批) -> efetch(分批),返回合并后的元数据列表。"""
    ids, count = stratified_search_by_year(term, retmax, api_key)
    if not ids:
        return [], count

    delay = _rate_delay(api_key)
    id_batches = _chunk(ids, 150)

    summaries: list[dict] = []
    for batch in id_batches:
        summaries.extend(esummary_batch(batch, api_key))
        time.sleep(delay)

    abstracts: dict[str, str] = {}
    for batch in id_batches:
        abstracts.update(efetch_abstracts_batch(batch, api_key))
        time.sleep(delay)

    return _merge(summaries, abstracts), count


def _extract_year(pubdate: str | None) -> int | None:
    if not pubdate:
        return None
    m = re.search(r"(\d{4})", pubdate)
    return int(m.group(1)) if m else None


def _merge(summaries: list[dict], abstracts: dict[str, str]) -> list[dict]:
    from journal_data import lookup_journal

    merged = []
    for s in summaries:
        uid = s.get("uid")
        title = s.get("title")
        if not uid or not title:
            continue
        year = _extract_year(s.get("pubdate") or s.get("sortpubdate"))
        journal_full = s.get("fulljournalname", "")
        journal_abbrev = s.get("source", "")
        jinfo = lookup_journal(journal_full, journal_abbrev)
        merged.append({
            "pmid": uid,
            "title": re.sub(r"<[^>]+>", "", title),
            "journal": journal_full or journal_abbrev or "未知期刊",
            "year": year,
            "authors": ", ".join(a.get("name", "") for a in s.get("authors", [])),
            "if": jinfo["if"] if jinfo else None,
            "quartile": jinfo["quartile"] if jinfo else "未收录",
            "abstract": abstracts.get(uid, ""),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
        })
    return merged