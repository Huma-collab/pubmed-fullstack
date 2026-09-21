"""
rag_summary.py
"基于文献摘要生成中文综述报告" 的检索增强生成(RAG)实现。

设计说明(面向面试展示的思考点):
1. PubMed/NCBI 没有现成的"摘要生成"接口,这一步必须自己做语义综合。
2. 检索(Retrieval): 用 TF-IDF 对所有拿到的摘要做向量化,以关键词+高频词
   作为查询,召回与主题最相关的一批摘要片段 —— 避免把全部摘要一股脑塞进
   Prompt(费token、且稀释重点),这是一个轻量版 RAG,不依赖外部向量数据库,
   对 demo 场景足够,同时保留了"检索-生成"两阶段的结构,方便后续替换成
   embedding + 向量库(如 FAISS/Chroma)。
3. 生成(Generation): 如果用户配置了可用的 LLM API(OpenAI 兼容协议,通过
   LangChain 的 ChatOpenAI 封装,支持自定义 base_url,因此也能接入
   DeepSeek/Moonshot/自建网关等),则调用真实模型,基于检索到的摘要生成
   中文综述;否则回退到规则统计版报告,不编造内容。
"""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def retrieve_relevant_abstracts(query: str, docs: list[dict], top_k: int = 20) -> list[dict]:
    """轻量 RAG 的检索阶段: TF-IDF + 余弦相似度召回与 query 最相关的文献。"""
    candidates = [d for d in docs if d.get("abstract")]
    if not candidates:
        return []
    corpus = [f"{d['title']} {d['abstract']}" for d in candidates]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=4000)
        matrix = vectorizer.fit_transform(corpus + [query])
        query_vec = matrix[-1]
        doc_vecs = matrix[:-1]
        sims = cosine_similarity(query_vec, doc_vecs).flatten()
    except ValueError:
        # 语料过小等边界情况,直接按影响因子/原顺序返回
        return candidates[:top_k]

    ranked = sorted(zip(candidates, sims), key=lambda x: x[1], reverse=True)
    return [d for d, _ in ranked[:top_k]]


def build_rule_based_report(keyword: str, pool: list[dict], all_docs: list[dict], word_freq: list[str]) -> str:
    quartile_counts = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0, "未收录": 0}
    for d in all_docs:
        quartile_counts[d.get("quartile", "未收录")] = quartile_counts.get(d.get("quartile", "未收录"), 0) + 1

    years = [d["year"] for d in pool if d.get("year")]
    y_min, y_max = (min(years), max(years)) if years else ("-", "-")
    ifs = [d["if"] for d in pool if d.get("if") is not None]
    avg_if = f"{sum(ifs) / len(ifs):.1f}" if ifs else "-"

    journal_counts: dict[str, int] = {}
    for d in pool:
        journal_counts[d["journal"]] = journal_counts.get(d["journal"], 0) + 1
    top_journals = [j for j, _ in sorted(journal_counts.items(), key=lambda x: x[1], reverse=True)[:5]]

    return f"""【"{keyword}"领域文献综述报告 — 规则统计版】

一、总体概况
本次检索共命中并分析 {len(all_docs)} 篇 PubMed 收录文献,时间跨度约为 {y_min} - {y_max} 年。其中纳入近5年高影响力排行(基于示例影响因子数据库匹配)的核心文献 {len(pool)} 篇,平均影响因子约为 {avg_if}。

二、期刊分布特征
纳入统计的文献中,Q1区期刊 {quartile_counts.get('Q1', 0)} 篇、Q2区 {quartile_counts.get('Q2', 0)} 篇、Q3区 {quartile_counts.get('Q3', 0)} 篇、Q4区 {quartile_counts.get('Q4', 0)} 篇,另有 {quartile_counts.get('未收录', 0)} 篇因期刊未被本地示例数据库收录暂无法分区。高频发表期刊包括:{'、'.join(top_journals) if top_journals else '暂无明显集中'}。

三、研究热点关键词
基于标题与摘要的词频统计,该领域近期研究中出现频率较高的英文关键词包括:{', '.join(word_freq) if word_freq else '暂无'}。这些高频词可初步反映当前研究的核心对象与常用方法学,建议结合具体文献摘要进一步人工研判研究方向的具体分支与临床/基础倾向。

四、说明与建议
本报告为不依赖大模型的规则统计版本,基于关键词频率与文献元数据自动生成,尚不能替代对文献内容的语义级理解与总结。若需要更接近人工撰写的中文综述(总结具体研究结论、机制假说、争议点等),请在页面"AI摘要配置"中填入可用的大模型 API,系统将基于检索到的真实摘要文本(RAG)生成更高质量的综述。"""


def generate_ai_report(
    keyword: str,
    pool: list[dict],
    word_freq: list[str],
    llm_base_url: str,
    llm_api_key: str,
    llm_model: str,
) -> str:
    """检索增强生成: 先用 TF-IDF 召回最相关摘要,再用 LangChain 的 ChatOpenAI 生成中文综述。"""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate

    retrieved = retrieve_relevant_abstracts(keyword, pool, top_k=20)
    if not retrieved:
        retrieved = pool[:20]

    abstracts_block = "\n\n".join(
        f"[{i + 1}] {d['title']}({d['journal']}, {d.get('year', 'NA')}, IF={d.get('if', 'NA')})\n"
        f"摘要: {d.get('abstract') or '(无摘要)'}"
        for i, d in enumerate(retrieved[:25])
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一名医学文献分析助手,擅长基于英文文献摘要撰写严谨、忠于原文的中文综述,不编造摘要未提及的内容。"),
        ("human",
         "关键词: {keyword}\n"
         "高频关键词参考: {word_freq}\n\n"
         "以下是通过检索召回的、与该关键词最相关的代表性 PubMed 文献标题与摘要:\n\n"
         "{abstracts}\n\n"
         "请基于以上摘要内容,用中文撰写一篇约500字左右的该领域简要综述报告,分点呈现"
         "(如: 研究背景 / 主要研究方向 / 代表性发现 / 局限与展望),语言简洁专业。"),
    ])

    llm = ChatOpenAI(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=llm_model or "gpt-4o-mini",
        temperature=0.4,
    )
    chain = prompt | llm
    result = chain.invoke({
        "keyword": keyword,
        "word_freq": ", ".join(word_freq),
        "abstracts": abstracts_block,
    })
    content = getattr(result, "content", None)
    if not content:
        raise RuntimeError("LLM 返回内容为空")
    return content.strip()
