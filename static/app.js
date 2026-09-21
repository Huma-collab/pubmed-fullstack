// ============================================================
// app.js — 前端逻辑(调用本地 FastAPI 后端 /api/search、/api/summary)
// ============================================================

// 若前端单独用 Live Server 跑在别的端口,把这里改成后端地址,例如
// const API_BASE = "http://127.0.0.1:8000";
// 若前端就是由 FastAPI 的 StaticFiles 一起提供服务(推荐),留空即可(同源)。
const API_BASE = "";

const state = {
  keyword: "",
  merged: [],
  wordFreqRaw: [],
  llmConfig: { baseUrl: "", apiKey: "", model: "" },
};

function $(sel) { return document.querySelector(sel); }
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function setStatus(msg) { $("#statusLine").textContent = msg; }
function setProgress(pct) { $("#progressBar").style.width = Math.max(0, Math.min(100, pct)) + "%"; }

async function runPipeline() {
  const keyword = $("#keywordInput").value.trim();
  if (!keyword) {
    alert("请输入检索关键词");
    return;
  }
  state.keyword = keyword;
  const retmax = parseInt($("#retmaxSelect").value, 10);
  const pubmedApiKey = $("#apiKeyInput").value.trim();
  state.llmConfig.baseUrl = $("#llmBaseUrl").value.trim();
  state.llmConfig.apiKey = $("#llmApiKey").value.trim();
  state.llmConfig.model = $("#llmModel").value.trim();

  $("#runBtn").disabled = true;
  $("#resultsArea").classList.add("hidden");
  $("#progressWrap").classList.remove("hidden");
  setProgress(8);
  setStatus("正在请求后端: PubMed 检索 + 元数据/摘要抓取...(服务端处理,可能需要几秒到十几秒)");

  try {
    const searchRes = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, retmax, pubmed_api_key: pubmedApiKey || null }),
    });
    if (!searchRes.ok) {
      const errBody = await searchRes.json().catch(() => ({}));
      throw new Error(errBody.detail || `后端 /api/search 请求失败 (${searchRes.status})`);
    }
    const data = await searchRes.json();
    setProgress(60);

    if (!data.docs || data.docs.length === 0) {
      setStatus("未检索到相关文献,请更换关键词。");
      $("#progressWrap").classList.add("hidden");
      $("#runBtn").disabled = false;
      return;
    }

    state.merged = data.docs;
    state.wordFreqRaw = data.wordFreq;
    $("#totalHits").textContent = data.totalHits.toLocaleString();

    renderOverview(data);
    renderCharts(data);
    renderWordCloud(data.wordFreq);
    renderTop100(data.top100);

    setStatus("正在生成综述报告(RAG 检索 + 可选大模型生成)...");
    setProgress(80);

    const topKeywords = data.wordFreq.slice(0, 15).map(([w]) => w);
    const summaryRes = await fetch(`${API_BASE}/api/summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword,
        docs: data.top100.length >= 10 ? data.top100 : data.docs.slice(0, 30),
        word_freq: topKeywords,
        llm_base_url: state.llmConfig.baseUrl || null,
        llm_api_key: state.llmConfig.apiKey || null,
        llm_model: state.llmConfig.model || null,
      }),
    });
    const summaryData = await summaryRes.json();
    renderReport(summaryData);

    setProgress(100);
    setStatus(`完成: 共获取 ${data.fetchedCount} 篇文献(PubMed 命中 ${data.totalHits.toLocaleString()} 篇)`);
    $("#resultsArea").classList.remove("hidden");
  } catch (err) {
    console.error(err);
    setStatus("出错: " + err.message + "(请确认后端服务已启动:uvicorn main:app --reload)");
  } finally {
    $("#runBtn").disabled = false;
    setTimeout(() => $("#progressWrap").classList.add("hidden"), 800);
  }
}

// ---------------- 渲染 ----------------

let yearChart, quartileChart, ifChart;

function renderOverview(data) {
  const withIF = data.docs.filter(r => r.if != null).length;
  const years = data.yearCounts.years;
  $("#statTotal").textContent = data.docs.length;
  $("#statYearRange").textContent = years.length ? `${years[0]} - ${years[years.length - 1]}` : "-";
  $("#statMatched").textContent = `${withIF} / ${data.docs.length}`;
  $("#statQ1").textContent = data.quartileCounts.Q1 || 0;
}

function renderCharts(data) {
  const { years, values } = data.yearCounts;
  const q = data.quartileCounts;
  const ifTrend = data.avgIfByYear;

  if (yearChart) yearChart.destroy();
  if (quartileChart) quartileChart.destroy();
  if (ifChart) ifChart.destroy();

  yearChart = new Chart($("#yearChart"), {
    type: "bar",
    data: { labels: years, datasets: [{ label: "发表数量", data: values, backgroundColor: "#4f7cff" }] },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });

  quartileChart = new Chart($("#quartileChart"), {
    type: "doughnut",
    data: {
      labels: Object.keys(q),
      datasets: [{ data: Object.values(q), backgroundColor: ["#4f7cff", "#5fd08a", "#f5b942", "#f2634f", "#c9ccd6"] }],
    },
    options: { responsive: true },
  });

  ifChart = new Chart($("#ifChart"), {
    type: "line",
    data: {
      labels: ifTrend.years,
      datasets: [{
        label: "平均影响因子", data: ifTrend.values,
        borderColor: "#f2634f", backgroundColor: "rgba(242,99,79,0.15)", fill: true, tension: 0.3,
      }],
    },
    options: { responsive: true },
  });
}

function renderWordCloud(wordFreq) {
  const wc = $("#wordCloud");
  wc.innerHTML = "";
  if (!wordFreq || wordFreq.length === 0) {
    wc.appendChild(el("div", "muted", "暂无足够文本用于生成词云"));
    return;
  }
  const max = wordFreq[0][1];
  const min = wordFreq[wordFreq.length - 1][1];
  const palette = ["#4f7cff", "#5fd08a", "#f5b942", "#f2634f", "#8a6fd1", "#2fb6c4"];
  wordFreq.forEach(([w, c], i) => {
    const scale = max === min ? 0.5 : (c - min) / (max - min);
    const size = 13 + scale * 30;
    const span = el("span", "wc-word", w);
    span.style.fontSize = size.toFixed(1) + "px";
    span.style.color = palette[i % palette.length];
    span.title = `${w}: ${c} 次`;
    wc.appendChild(span);
  });
}

function renderTop100(top) {
  const tbody = $("#top100Body");
  tbody.innerHTML = "";
  top.forEach((r, i) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, String(i + 1)));
    const titleTd = el("td");
    const a = el("a", "title-link", r.title);
    a.href = r.url; a.target = "_blank"; a.rel = "noopener";
    titleTd.appendChild(a);
    tr.appendChild(titleTd);
    tr.appendChild(el("td", null, r.journal));
    tr.appendChild(el("td", null, String(r.year ?? "-")));
    tr.appendChild(el("td", null, r.if != null ? r.if.toFixed(1) : "-"));
    tr.appendChild(el("td", "quartile-" + r.quartile, r.quartile));
    tbody.appendChild(tr);
  });
  $("#top100Count").textContent = top.length;
  state._top100 = top;
}

function renderReport(summaryData) {
  $("#reportContent").textContent = summaryData.text;
  const badge = $("#reportSourceBadge");
  if (summaryData.source === "ai") {
    badge.textContent = "AI 生成(RAG 检索 + 大模型生成)";
    badge.className = "badge badge-ai";
  } else {
    const extra = summaryData.llm_error ? `(LLM调用失败已回退: ${summaryData.llm_error})` : "";
    badge.textContent = "规则统计版(未接入大模型 " + extra + ")";
    badge.className = "badge badge-rule";
  }
}

function exportCSV() {
  const top = state._top100 || [];
  const header = ["排名", "标题", "期刊", "年份", "影响因子", "分区", "PMID", "链接"];
  const rows = top.map((r, i) => [i + 1, (r.title || "").replace(/"/g, '""'), r.journal, r.year, r.if ?? "", r.quartile, r.pmid, r.url]);
  const csv = [header, ...rows].map(row => row.map(v => `"${v}"`).join(",")).join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `pubmed_top100_${state.keyword}.csv`;
  link.click();
}

window.addEventListener("DOMContentLoaded", () => {
  $("#runBtn").addEventListener("click", runPipeline);
  $("#keywordInput").addEventListener("keydown", e => { if (e.key === "Enter") runPipeline(); });
  $("#exportCsvBtn").addEventListener("click", exportCSV);
  $("#advToggle").addEventListener("click", () => $("#advPanel").classList.toggle("hidden"));
});
