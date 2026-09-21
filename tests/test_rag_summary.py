"""
单元测试: rag_summary.py 的检索(TF-IDF）与规则版报告生成。
LLM 生成路径(generate_ai_report)不在此处测试真实网络调用,
而是用 mock 验证"调用了正确的 prompt 结构 / 出错时会向上抛出以便主程序回退"。
"""
from unittest.mock import patch, MagicMock

import pytest

from rag_summary import retrieve_relevant_abstracts, build_rule_based_report


SAMPLE_DOCS = [
    {
        "title": "CRISPR editing of BCL11A in sickle cell disease",
        "journal": "Nature Medicine",
        "year": 2023,
        "if": 82.9,
        "quartile": "Q1",
        "abstract": "gene therapy crispr sickle cell hemoglobin induction trial",
    },
    {
        "title": "Deep learning for chest X-ray pneumonia classification",
        "journal": "Radiology",
        "year": 2021,
        "if": 12.1,
        "quartile": "Q1",
        "abstract": "convolutional neural network pneumonia detection radiograph imaging",
    },
    {
        "title": "CRISPR-Cas9 therapy for beta-thalassemia patients",
        "journal": "The Lancet",
        "year": 2022,
        "if": 168.9,
        "quartile": "Q1",
        "abstract": "gene editing thalassemia transfusion independence stem cells",
    },
]


def test_retrieve_ranks_relevant_docs_first():
    ranked = retrieve_relevant_abstracts("CRISPR gene therapy", SAMPLE_DOCS, top_k=2)
    titles = [d["title"] for d in ranked]
    assert "Deep learning for chest X-ray pneumonia classification" not in titles
    assert len(ranked) == 2


def test_retrieve_handles_empty_doc_list():
    assert retrieve_relevant_abstracts("anything", [], top_k=5) == []


def test_retrieve_handles_docs_without_abstracts():
    docs = [{"title": "No abstract here", "abstract": ""}]
    assert retrieve_relevant_abstracts("query", docs, top_k=5) == []


def test_rule_based_report_contains_keyword_and_counts():
    report = build_rule_based_report(
        keyword="CRISPR gene therapy",
        pool=SAMPLE_DOCS,
        all_docs=SAMPLE_DOCS,
        word_freq=["crispr", "gene", "therapy"],
    )
    assert "CRISPR gene therapy" in report
    assert "3 篇" in report  # len(all_docs) == 3
    assert "规则统计版" in report
    assert "crispr" in report


def test_rule_based_report_handles_no_matched_impact_factor():
    docs = [{"title": "x", "journal": "Unknown", "year": 2020, "if": None, "quartile": "未收录", "abstract": "a"}]
    report = build_rule_based_report("test kw", docs, docs, [])
    assert "test kw" in report
    assert "平均影响因子约为 -" in report


def test_generate_ai_report_raises_on_empty_llm_response():
    """当 LLM 返回空内容时应抛出异常,交由调用方(main.py)回退到规则版报告。"""
    from rag_summary import generate_ai_report

    fake_llm = MagicMock()
    fake_chain = MagicMock()
    fake_chain.invoke.return_value = MagicMock(content="")
    fake_llm.__or__ = MagicMock(return_value=fake_chain)

    with patch("langchain_openai.ChatOpenAI", return_value=fake_llm), \
         patch("langchain_core.prompts.ChatPromptTemplate.from_messages") as mock_prompt:
        mock_prompt.return_value.__or__ = MagicMock(return_value=fake_chain)
        with pytest.raises(RuntimeError):
            generate_ai_report(
                keyword="CRISPR",
                pool=SAMPLE_DOCS,
                word_freq=["crispr"],
                llm_base_url="https://fake.example.com/v1",
                llm_api_key="fake-key",
                llm_model="fake-model",
            )
