# PubMed 文献分析 Demo(FastAPI + RAG）

全栈版本:Python (FastAPI) 后端 + 静态前端,替代了纯客户端 HTML 版本,
以对齐岗位 JD 中对 Python / 全栈 / RAG 实战经验的要求。

## 架构

```
关键词
  │
  ▼
FastAPI /api/search  ── 调 NCBI E-utilities (esearch/esummary/efetch)
  │                       在服务端完成检索,规避浏览器 CORS / 速率限制问题
  ▼
journal_data.py       ── 匹配内置期刊 IF / JCR 分区示例数据库
  │
  ▼
返回: 统计(按年/分区/平均IF)、词云词频、影响力Top100
  │
  ▼
前端渲染图表 / 词云 / 排行表(Chart.js)
  │
  ▼
FastAPI /api/summary  ── RAG 两阶段:
  1) 检索: TF-IDF + 余弦相似度,从抓取到的摘要中召回与关键词最相关的一批
  2) 生成: 若配置了大模型 API → LangChain ChatOpenAI 生成中文综述
           否则 → 回退到规则统计版报告(不编造内容)
```

## 运行方式

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

浏览器打开 http://127.0.0.1:8000 即可(前端由后端一并托管,无需额外起前端服务)。

## 设计取舍说明(用于现场讲解)

- **为什么检索/摘要抓取放在后端而不是浏览器直连 NCBI**:避免依赖 NCBI 的 CORS
  策略是否稳定、避免把速率限制逻辑暴露在前端、也方便后续加缓存/队列。
- **为什么用 TF-IDF 而不是向量数据库做检索**:demo 规模下(几十到几百篇摘要)
  TF-IDF 足够快且零额外依赖;如果要生产化,替换点就是
  `rag_summary.retrieve_relevant_abstracts`,换成 embedding + FAISS/Chroma
  即可,其余流程(Prompt 构造、生成、回退)不用动。
- **为什么保留规则统计版兜底**:PubMed 本身没有摘要生成能力,若不接入大模型,
  诚实地展示统计结果比让页面报错或返回空更符合产品思维。
- **影响因子/分区数据来源**:没有公开免费的实时 IF API,demo 内置了一份
  ~150 本常见期刊的参考数据(`journal_data.py`),未覆盖的期刊会标注"未收录"。

## 单元测试

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

测试范围(全部离线运行,不依赖真实网络/NCBI/大模型 API):

- `test_journal_data.py` — 期刊名归一化、精确匹配、缩写回退匹配、未收录期刊
- `test_pubmed_client.py` — 发表年份解析、esearch/esummary/efetch 结果合并逻辑
  (数据合并用手工构造的假数据测试,真实的 NCBI 网络请求属于集成测试范畴,
  不在单元测试里覆盖)
- `test_rag_summary.py` — TF-IDF 检索排序是否召回真正相关的文献、规则版报告
  内容正确性、LLM 返回空内容时是否正确抛错(供上层回退)
- `test_main.py` — FastAPI 端点行为:`/api/search`/`/api/summary` 的正常路径、
  参数校验(400)、下游失败时的错误处理(502)、AI摘要成功/失败时的回退逻辑
  (均使用 `unittest.mock.patch` 打桩掉 `pubmed_client.fetch_all` 与
  `rag_summary.generate_ai_report`,测试跑起来不会真的调用 PubMed 或大模型)

## 目录结构

```
main.py            FastAPI 入口,路由与统计计算
pubmed_client.py   NCBI E-utilities 封装
journal_data.py    期刊 IF / 分区示例数据库
rag_summary.py     RAG 检索 + 报告生成(规则版 / LLM版）
tests/             单元测试(pytest)
requirements.txt
requirements-dev.txt
static/
  index.html       前端页面
  app.js           前端逻辑(调用 /api/search、/api/summary）
```
