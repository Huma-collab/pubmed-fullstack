"""
main.py — FastAPI 后端

端点:
  POST /api/search   关键词 -> PubMed 检索 -> 统计/词云/影响力排行
  POST /api/summary  基于检索结果的摘要,生成中文综述报告(RAG,可选接入LLM)

运行:
  pip install -r requirements.txt
  uvicorn main:app --reload
  浏览器打开 http://127.0.0.1:8000
"""
from collections import Counter
import re
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pubmed_client
import rag_summary

app = FastAPI(title="PubMed 文献分析 Demo API")

# 开发环境下允许所有来源跨域(如通过 VS Code Live Server 单独跑前端时);
# 生产环境应改为白名单具体域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below
between both but by can cannot could did do does doing down during each few for from further had
has have having he her here hers herself him himself his how i if in into is it its itself just
me more most my myself no nor not of off on once only or other our ours ourselves out over own
same she should so some such than that the their theirs them themselves then there these they
this those through to too under until up very was we were what when where which while who whom
why will with you your yours yourself yourselves using use used study studies result results
method methods conclusion conclusions background objective objectives patients patient group
groups compared between among may can also however significant significantly value non
""".split())


class SearchRequest(BaseModel):
    keyword: str
    retmax: int = 200
    pubmed_api_key: str | None = None


class SummaryRequest(BaseModel):
    keyword: str
    docs: list[dict]           # 前端传回 /api/search 得到的 merged 列表(或其子集)
    word_freq: list[str] = []
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z\-]{2,}", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def _compute_word_freq(docs: list[dict], top_n: int = 60) -> list[list]:
    counter: Counter = Counter()
    for d in docs:
        counter.update(_tokenize(f"{d.get('title', '')} {d.get('abstract', '')}"))
    return [[w, c] for w, c in counter.most_common(top_n)]


def _compute_year_counts(docs: list[dict]) -> dict:
    counts: Counter = Counter(d["year"] for d in docs if d.get("year"))
    years = sorted(counts.keys())
    return {"years": years, "values": [counts[y] for y in years]}


def _compute_quartile_counts(docs: list[dict]) -> dict:
    counts = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0, "未收录": 0}
    for d in docs:
        q = d.get("quartile", "未收录")
        counts[q] = counts.get(q, 0) + 1
    return counts


def _compute_avg_if_by_year(docs: list[dict]) -> dict:
    by_year: dict[int, list[float]] = {}
    for d in docs:
        if d.get("year") and d.get("if") is not None:
            by_year.setdefault(d["year"], []).append(d["if"])
    years = sorted(by_year.keys())
    values = [round(sum(by_year[y]) / len(by_year[y]), 1) for y in years]
    return {"years": years, "values": values}


def _compute_top100(docs: list[dict]) -> list[dict]:
    cutoff = datetime.now().year - 5
    eligible = [d for d in docs if d.get("year") and d["year"] >= cutoff and d.get("if") is not None]
    eligible.sort(key=lambda d: d["if"], reverse=True)
    return eligible[:100]


@app.post("/api/search")
def search(req: SearchRequest):
    keyword = req.keyword.strip()
    if not keyword:
        raise HTTPException(400, "关键词不能为空")
    try:
        docs, total_count = pubmed_client.fetch_all(keyword, req.retmax, req.pubmed_api_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"PubMed 请求失败: {e}") from e

    word_freq = _compute_word_freq(docs)
    top100 = _compute_top100(docs)

    return {
        "totalHits": total_count,
        "fetchedCount": len(docs),
        "docs": docs,
        "yearCounts": _compute_year_counts(docs),
        "quartileCounts": _compute_quartile_counts(docs),
        "avgIfByYear": _compute_avg_if_by_year(docs),
        "wordFreq": word_freq,
        "top100": top100,
    }


@app.post("/api/summary")
def summary(req: SummaryRequest):
    pool = req.docs if req.docs else []
    all_docs = pool
    top_pool = pool[:60] if len(pool) > 60 else pool

    if req.llm_base_url and req.llm_api_key:
        try:
            text = rag_summary.generate_ai_report(
                req.keyword, top_pool, req.word_freq,
                req.llm_base_url, req.llm_api_key, req.llm_model or "",
            )
            return {"text": text, "source": "ai"}
        except Exception as e:  # noqa: BLE001
            # 回退到规则版,同时把错误信息带回去,方便调试
            rule_text = rag_summary.build_rule_based_report(req.keyword, top_pool, all_docs, req.word_freq)
            return {"text": rule_text, "source": "rule", "llm_error": str(e)}

    rule_text = rag_summary.build_rule_based_report(req.keyword, top_pool, all_docs, req.word_freq)
    return {"text": rule_text, "source": "rule"}


# 静态前端文件(index.html / app.js)挂载在根路径,必须放在所有 /api 路由之后,
# 否则会把 /api/* 也当作静态资源处理。
app.mount("/", StaticFiles(directory="static", html=True), name="static")
