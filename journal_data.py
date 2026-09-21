"""
journal_data.py
参考期刊影响因子(IF)与JCR分区(示例数据库,非官方实时数据)。
数据仅用于demo演示,基于公开可查的近年JCR大致区间整理,覆盖常见高被引/
综合性及各专科代表期刊,未覆盖期刊将标记为"未收录"。
"""
import re

# (期刊名/常见缩写, 影响因子, 分区)
JOURNAL_DB = [
    # ---- 综合顶刊 ----
    ("nature", 64.8, "Q1"),
    ("science", 56.9, "Q1"),
    ("cell", 64.5, "Q1"),
    ("the new england journal of medicine", 158.5, "Q1"),
    ("new england journal of medicine", 158.5, "Q1"),
    ("lancet", 168.9, "Q1"),
    ("the lancet", 168.9, "Q1"),
    ("jama", 120.7, "Q1"),
    ("jama : the journal of the american medical association", 120.7, "Q1"),
    ("bmj (clinical research ed.)", 105.7, "Q1"),
    ("bmj", 105.7, "Q1"),
    ("nature medicine", 82.9, "Q1"),
    ("nature genetics", 31.7, "Q1"),
    ("nature biotechnology", 46.9, "Q1"),
    ("nature methods", 36.1, "Q1"),
    ("nature communications", 14.7, "Q1"),
    ("nature reviews. cancer", 78.5, "Q1"),
    ("nature reviews cancer", 78.5, "Q1"),
    ("nature reviews. immunology", 61.7, "Q1"),
    ("nature reviews. drug discovery", 122.9, "Q1"),
    ("nature reviews. molecular cell biology", 81.3, "Q1"),
    ("nature immunology", 27.7, "Q1"),
    ("nature neuroscience", 21.2, "Q1"),
    ("nature cell biology", 21.3, "Q1"),
    ("proceedings of the national academy of sciences of the united states of america", 11.1, "Q1"),
    ("pnas", 11.1, "Q1"),
    ("science translational medicine", 17.1, "Q1"),
    ("science advances", 13.6, "Q1"),
    ("science immunology", 24.2, "Q1"),
    ("plos medicine", 15.8, "Q1"),
    ("plos biology", 9.8, "Q1"),
    ("plos one", 3.7, "Q2"),
    ("scientific reports", 4.6, "Q2"),
    ("annual review of immunology", 22.9, "Q1"),
    # ---- 肿瘤 ----
    ("ca: a cancer journal for clinicians", 254.7, "Q1"),
    ("cancer cell", 48.8, "Q1"),
    ("cancer discovery", 28.2, "Q1"),
    ("journal of clinical oncology", 42.1, "Q1"),
    ("lancet oncology", 41.6, "Q1"),
    ("the lancet oncology", 41.6, "Q1"),
    ("nature reviews clinical oncology", 62.1, "Q1"),
    ("clinical cancer research", 11.5, "Q1"),
    ("cancer research", 12.5, "Q1"),
    ("annals of oncology", 32.9, "Q1"),
    ("jama oncology", 22.5, "Q1"),
    ("leukemia", 12.8, "Q1"),
    ("blood", 20.3, "Q1"),
    ("journal of the national cancer institute", 11.5, "Q1"),
    ("international journal of cancer", 6.4, "Q2"),
    ("cancer letters", 9.1, "Q1"),
    ("oncogene", 6.9, "Q2"),
    # ---- 心血管 ----
    ("circulation", 35.5, "Q1"),
    ("european heart journal", 39.3, "Q1"),
    ("journal of the american college of cardiology", 24.0, "Q1"),
    ("jacc", 24.0, "Q1"),
    ("circulation research", 20.1, "Q1"),
    ("hypertension", 8.2, "Q1"),
    ("stroke", 8.0, "Q1"),
    ("american heart journal", 4.9, "Q2"),
    ("international journal of cardiology", 3.9, "Q2"),
    ("jama cardiology", 12.6, "Q1"),
    # ---- 内分泌/代谢 ----
    ("diabetes care", 16.2, "Q1"),
    ("diabetologia", 8.9, "Q1"),
    ("cell metabolism", 27.7, "Q1"),
    ("lancet diabetes & endocrinology", 44.5, "Q1"),
    ("the lancet diabetes & endocrinology", 44.5, "Q1"),
    ("diabetes", 7.7, "Q1"),
    ("journal of clinical endocrinology and metabolism", 5.8, "Q1"),
    ("endocrine reviews", 19.3, "Q1"),
    ("obesity", 3.7, "Q2"),
    # ---- 消化 ----
    ("gastroenterology", 25.7, "Q1"),
    ("gut", 24.5, "Q1"),
    ("hepatology", 12.9, "Q1"),
    ("journal of hepatology", 25.7, "Q1"),
    ("clinical gastroenterology and hepatology", 11.6, "Q1"),
    ("american journal of gastroenterology", 8.5, "Q1"),
    # ---- 呼吸/危重症 ----
    ("american journal of respiratory and critical care medicine", 19.3, "Q1"),
    ("european respiratory journal", 24.3, "Q1"),
    ("chest", 9.5, "Q1"),
    ("thorax", 10.0, "Q1"),
    ("intensive care medicine", 38.2, "Q1"),
    ("critical care medicine", 9.3, "Q1"),
    ("lancet respiratory medicine", 30.7, "Q1"),
    ("the lancet respiratory medicine", 30.7, "Q1"),
    # ---- 肾脏 ----
    ("kidney international", 14.8, "Q1"),
    ("journal of the american society of nephrology", 10.3, "Q1"),
    ("clinical journal of the american society of nephrology", 8.5, "Q1"),
    ("american journal of kidney diseases", 8.5, "Q1"),
    ("nephrology dialysis transplantation", 4.8, "Q2"),
    # ---- 神经 ----
    ("neuron", 14.4, "Q1"),
    ("brain", 14.5, "Q1"),
    ("lancet neurology", 46.5, "Q1"),
    ("the lancet neurology", 46.5, "Q1"),
    ("jama neurology", 20.4, "Q1"),
    ("annals of neurology", 9.4, "Q1"),
    ("neurology", 9.9, "Q1"),
    ("molecular psychiatry", 11.0, "Q1"),
    ("alzheimer's & dementia", 13.0, "Q1"),
    ("acta neuropathologica", 15.9, "Q1"),
    # ---- 免疫 ----
    ("immunity", 32.4, "Q1"),
    ("journal of experimental medicine", 15.3, "Q1"),
    ("journal of immunology", 4.4, "Q2"),
    ("frontiers in immunology", 5.7, "Q2"),
    # ---- 分子细胞生物学 ----
    ("molecular cell", 19.3, "Q1"),
    ("genes & development", 8.5, "Q1"),
    ("developmental cell", 12.4, "Q1"),
    ("embo journal", 11.0, "Q1"),
    ("genome biology", 13.6, "Q1"),
    ("genome research", 7.1, "Q1"),
    ("nucleic acids research", 16.6, "Q1"),
    ("plos genetics", 4.5, "Q2"),
    ("american journal of human genetics", 9.8, "Q1"),
    # ---- 外科/骨科/其他专科 ----
    ("annals of surgery", 8.9, "Q1"),
    ("jama surgery", 12.0, "Q1"),
    ("british journal of surgery", 8.6, "Q1"),
    ("journal of bone and joint surgery. american volume", 5.3, "Q1"),
    ("ophthalmology", 13.7, "Q1"),
    ("radiology", 12.1, "Q1"),
    ("european urology", 21.4, "Q1"),
    ("american journal of psychiatry", 17.7, "Q1"),
    ("lancet psychiatry", 30.8, "Q1"),
    ("the lancet psychiatry", 30.8, "Q1"),
    ("pain", 6.2, "Q1"),
    ("arthritis & rheumatology", 11.4, "Q1"),
    ("annals of the rheumatic diseases", 20.3, "Q1"),
    ("allergy", 12.6, "Q1"),
    ("journal of allergy and clinical immunology", 11.4, "Q1"),
    # ---- 综合内科/公卫/流行病 ----
    ("annals of internal medicine", 19.6, "Q1"),
    ("lancet global health", 25.7, "Q1"),
    ("the lancet global health", 25.7, "Q1"),
    ("lancet public health", 27.1, "Q1"),
    ("the lancet public health", 27.1, "Q1"),
    ("american journal of epidemiology", 4.7, "Q2"),
    ("international journal of epidemiology", 6.7, "Q1"),
    ("bmc medicine", 9.3, "Q1"),
    ("bmc public health", 3.5, "Q2"),
    ("value in health", 4.9, "Q2"),
    # ---- 传染病/微生物 ----
    ("lancet infectious diseases", 36.4, "Q1"),
    ("the lancet infectious diseases", 36.4, "Q1"),
    ("clinical infectious diseases", 8.2, "Q1"),
    ("journal of infectious diseases", 5.0, "Q2"),
    ("emerging infectious diseases", 8.9, "Q1"),
    ("nature microbiology", 20.5, "Q1"),
    ("cell host & microbe", 20.6, "Q1"),
    # ---- 计算机/AI/交叉 ----
    ("nature machine intelligence", 23.9, "Q1"),
    ("ieee transactions on pattern analysis and machine intelligence", 20.8, "Q1"),
    ("bioinformatics", 4.4, "Q2"),
    ("journal of medical internet research", 5.8, "Q1"),
    ("npj digital medicine", 12.4, "Q1"),
    # ---- 中国常见综合期刊(部分) ----
    ("chinese medical journal", 6.4, "Q2"),
    ("signal transduction and targeted therapy", 39.3, "Q1"),
    ("cell research", 28.1, "Q1"),
    ("national science review", 20.6, "Q1"),
    ("science bulletin", 18.9, "Q1"),
]


def normalize_journal_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    name = name.replace(".", "")
    name = name.replace("&", "and")
    name = re.sub(r"\s+", " ", name).strip()
    return name


_JOURNAL_MAP = {normalize_journal_name(name): {"if": ifv, "quartile": q} for name, ifv, q in JOURNAL_DB}


def lookup_journal(full_name: str = "", abbrev_name: str = ""):
    """只做精确匹配(忽略大小写/标点后完全相等),不做子串/模糊匹配。

    历史上这里有一版"包含匹配"的兜底逻辑(c in key or key in c),
    目的是兼容带副标题、卷期信息的期刊名。但实测发现它极不安全:
    像 "Science"(56.9)这种简短的期刊名会作为子串命中一大批毫不相关的
    期刊,例如 "...Molecular Sciences"、"...Translational Science"、
    "International Journal of Molecular Sciences" 等,导致这些期刊被
    错误地打上顶刊的影响因子和 Q1 分区 —— 这直接污染了"影响力排行"这个
    核心交付物的可信度。因此改为只接受精确匹配:命中的都是可靠的,
    没命中的诚实地标记为"未收录",而不是用一个错误的高分掩盖过去。
    """
    candidates = [normalize_journal_name(c) for c in (full_name, abbrev_name) if c]
    for c in candidates:
        if c in _JOURNAL_MAP:
            return _JOURNAL_MAP[c]
    return None