"""
单元测试: main.py 的 FastAPI 端点。
外部依赖(NCBI 网络请求、真实大模型调用)全部 mock 掉,
保证测试快速、稳定、可离线运行。
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_static_frontend_is_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "PubMed" in resp.text


def test_search_rejects_empty_keyword():
    resp = client.post("/api/search", json={"keyword": "   ", "retmax": 50})
    assert resp.status_code == 400


def test_search_returns_expected_shape_with_mocked_pubmed():
    fake_docs = [
        {
            "pmid": "1", "title": "CRISPR gene therapy trial", "journal": "Nature Medicine",
            "year": 2023, "authors": "A, B", "if": 82.9, "quartile": "Q1",
            "abstract": "gene therapy crispr trial results",
            "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
        },
        {
            "pmid": "2", "title": "Older unrelated paper", "journal": "Unknown Journal",
            "year": 2015, "authors": "C", "if": None, "quartile": "未收录",
            "abstract": "",
            "url": "https://pubmed.ncbi.nlm.nih.gov/2/",
        },
    ]
    with patch("main.pubmed_client.fetch_all", return_value=(fake_docs, 2)):
        resp = client.post("/api/search", json={"keyword": "CRISPR gene therapy", "retmax": 50})

    assert resp.status_code == 200
    data = resp.json()
    assert data["totalHits"] == 2
    assert data["fetchedCount"] == 2
    assert len(data["docs"]) == 2
    assert "years" in data["yearCounts"]
    assert set(data["quartileCounts"].keys()) >= {"Q1", "Q2", "Q3", "Q4", "未收录"}
    # top100 只应包含近5年内且有IF的文献 -> 应该只剩第一篇
    assert len(data["top100"]) == 1
    assert data["top100"][0]["pmid"] == "1"


def test_search_returns_502_when_pubmed_client_fails():
    with patch("main.pubmed_client.fetch_all", side_effect=RuntimeError("network down")):
        resp = client.post("/api/search", json={"keyword": "test", "retmax": 50})
    assert resp.status_code == 502


def test_summary_falls_back_to_rule_based_when_no_llm_config():
    resp = client.post("/api/summary", json={
        "keyword": "CRISPR",
        "docs": [{"title": "x", "journal": "Nature", "year": 2023, "if": 60, "quartile": "Q1", "abstract": "a"}],
        "word_freq": ["crispr"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "rule"
    assert "CRISPR" in data["text"]


def test_summary_uses_ai_path_when_llm_config_present_and_succeeds():
    with patch("main.rag_summary.generate_ai_report", return_value="这是AI生成的中文综述。"):
        resp = client.post("/api/summary", json={
            "keyword": "CRISPR",
            "docs": [{"title": "x", "journal": "Nature", "year": 2023, "if": 60, "quartile": "Q1", "abstract": "a"}],
            "word_freq": ["crispr"],
            "llm_base_url": "https://fake.example.com/v1",
            "llm_api_key": "fake-key",
            "llm_model": "fake-model",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "ai"
    assert data["text"] == "这是AI生成的中文综述。"


def test_summary_falls_back_to_rule_when_ai_call_raises():
    with patch("main.rag_summary.generate_ai_report", side_effect=RuntimeError("LLM API 请求失败: 401")):
        resp = client.post("/api/summary", json={
            "keyword": "CRISPR",
            "docs": [{"title": "x", "journal": "Nature", "year": 2023, "if": 60, "quartile": "Q1", "abstract": "a"}],
            "word_freq": ["crispr"],
            "llm_base_url": "https://fake.example.com/v1",
            "llm_api_key": "bad-key",
            "llm_model": "fake-model",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "rule"
    assert "llm_error" in data
