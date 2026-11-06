#!/usr/bin/env python3
"""把「题目与详解」HTML 知识库导入为结构化题库。

用法:
    python scripts/import_kb.py <知识库根目录> [--out bank]

输出:
    bank/papers.json        试卷元数据(地区、年份、类型、题量、满分)
    (另外合并 bank/source/*.json 中按统一格式整理的试卷)
    bank/questions.jsonl    每行一道题(题干、答案、详解、知识点、题眼、难度先验、素养标签)

知识库目录约定(与作者整理的详解库一致):
    真题详解/上海/上海高考数学YYYY_题目与详解.html
    真题详解/全国/全国一卷数学YYYY_题目与详解.html ...
    模拟题详解/<省>/<名称>_题目与详解.html
    数据/sections_map.json, 数据/全国卷知识点/*.sections.json, 数据/题库来源/*.json, 数据/题眼/*.json
新增试卷时, 在 PAPERS 里加一行即可。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mathinsight.answers import count_blanks, numeric_answer  # noqa: E402
from mathinsight.taxonomy import Taxonomy  # noqa: E402

# (paper_id, 相对路径, 地区, 年份, 类别, 标题, 知识点来源)
PAPERS = [
    *[(f"SH-{y}", f"真题详解/上海/上海高考数学{y}_题目与详解.html", "上海", y, "高考",
       f"{y} 年普通高等学校招生全国统一考试（上海卷）数学", ("shmap", str(y))) for y in range(2020, 2027)],
    ("I-2024", "真题详解/全国/全国一卷数学2024_题目与详解.html", "全国", 2024, "高考", "2024 年新课标全国Ⅰ卷数学", ("nat", "I-2024")),
    ("I-2025", "真题详解/全国/全国一卷数学2025_题目与详解.html", "全国", 2025, "高考", "2025 年新课标全国Ⅰ卷数学", ("nat", "I-2025")),
    ("I-2026", "真题详解/全国/全国一卷数学2026_题目与详解.html", "全国", 2026, "高考", "2026 年新课标全国Ⅰ卷数学", ("nat", "I-2026")),
    ("II-2025", "真题详解/全国/全国二卷数学2025_题目与详解.html", "全国", 2025, "高考", "2025 年新课标全国Ⅱ卷数学", ("nat", "II-2025")),
    ("II-2026", "真题详解/全国/全国二卷数学2026_题目与详解.html", "全国", 2026, "高考", "2026 年新课标全国Ⅱ卷数学", ("nat", "II-2026")),
    ("JIA-2024", "真题详解/全国/全国甲卷理科数学2024_题目与详解.html", "全国", 2024, "高考", "2024 年全国甲卷理科数学", ("nat", "JIA-2024")),
    ("SH-XH-2025-1M", "模拟题详解/上海/徐汇一模2025届_题目与详解.html", "上海", 2025, "模拟", "上海徐汇区 2025 届高三一模数学", ("src", "SH-XH-2025-1M")),
    ("SC-CD-2025-3Z", "模拟题详解/四川/成都三诊2025_题目与详解.html", "四川", 2025, "模拟", "成都市 2025 届高三第三次诊断性检测数学", ("src", "SC-CD-2025-3Z")),
    ("ZJ-NB-2024-YIMO", "模拟题详解/浙江/宁波一模2025届_题目与详解.html", "浙江", 2025, "模拟", "宁波市 2025 届高三一模数学", ("src", "ZJ-NB-2024-YIMO")),
]

TYPE_NORM = {"填空": "填空", "填空题": "填空", "单选": "单选", "选择": "单选", "选择题": "单选",
             "单选题": "单选", "多选": "多选", "多选题": "多选", "解答": "解答", "解答题": "解答", "选做": "解答", "选做题": "解答"}


def load_kp(root: Path, kind: str, key: str) -> dict[str, list[dict]]:
    """返回 {题号: [{book, sec, detail}]}。"""
    data = root / "数据"
    if kind == "shmap":
        m = json.loads((data / "sections_map.json").read_text(encoding="utf-8"))
        return {k.split("-", 1)[1]: v for k, v in m.items() if k.startswith(key + "-")}
    if kind == "nat":
        return json.loads((data / "全国卷知识点" / f"{key}.sections.json").read_text(encoding="utf-8"))
    src = json.loads((data / "题库来源" / f"{key}.json").read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for q, ids in src.get("kp_ids_by_question", {}).items():
        seen = []
        for kid in ids:
            _, book, sec, _ = kid.split("-")
            if (book, sec) not in [(s["book"], s["sec"]) for s in seen]:
                seen.append({"book": book, "sec": sec, "detail": ""})
        out[q] = seen
    return out


def load_tiyan(root: Path, pid: str) -> dict:
    p = root / "数据" / "题眼" / f"{pid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def tiyan_text(entry: dict | None) -> tuple[str, list[str]]:
    if not entry:
        return "", []
    parts = []
    for it in entry.get("items", []):
        head = f"({it['part']}) " if it.get("part") else ""
        parts.append(head + it.get("text", ""))
    return entry.get("tag", ""), parts


H2_RE = re.compile(r"第\s*(\d+)\s*题.*?(填空题?|单选题?|多选题?|选择题?|解答题?|选做题?)[^\d]*(\d+)\s*分")


def strip_blocks(sec):
    for c in sec.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
    for sel in ["div.kp", "p.kp", "div.tiyan", "p.back", "div.qjump", "div.sitenav"]:
        for el in sec.select(sel):
            el.decompose()
    for a in sec.select("a.kp-idx, a.kp-pdf"):
        a.decompose()


# 编者附注(版本比对、来源说明、核对记录)只用于整理过程, 不进入公开题库
EDITORIAL = re.compile(
    "另版|乙版|甲版|版本|原题待核|网传|已更正|回忆版|排印版|转载|人人文库|教习网|zizzs|自主选拔|高考100|良师宝|"
    "eol|51test|DOC985|菁优|博客园|微博|中国教育在线|试卷图|答案版|解析版|原卷扫描|sympy|数值回代|枚举验证|复核|"
    "本页|原文此处|考试院评析")
CAPTION = re.compile("原卷|截自|重画|按原图")


def _drop_rest_of_line(el):
    nxt = el.next_sibling
    while nxt is not None and getattr(nxt, "name", None) != "br":
        cur, nxt = nxt, nxt.next_sibling
        cur.extract()


def clean_editorial(html: str) -> str:
    """去掉题干/详解里的编者附注, 保留「易错」「注意」等教学提示。"""
    if not html or not EDITORIAL.search(html) and not CAPTION.search(html):
        return html
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("span.warn, span.inf, span.note, p.note, div.note"):
        if el.parent is None:
            continue
        t = el.get_text("", strip=True)
        if not EDITORIAL.search(t):
            continue
        if len(t) <= 8:            # 「另版」「原题待核」之类的行内标记: 连同其后的说明一起去掉
            _drop_rest_of_line(el)
        el.decompose()
    for cap in soup.select("figcaption"):
        if CAPTION.search(cap.get_text()):
            cap.decompose()
    for a in soup.select("a[href]"):
        p = a.find_parent("p")
        if a["href"].lower().split("#")[0].endswith(".pdf") and p is not None:
            p.decompose()
    out = str(soup)
    out = re.sub(r"(\s*<br/?>\s*)+$", "", out.strip())
    return out


def answer_of(sec) -> str:
    ans = sec.select_one("div.answer")
    if ans:
        st = ans.find("strong")
        if st:
            st.extract()
        return ans.decode_contents().strip()
    for p in sec.find_all("p"):
        b = p.find("b")
        if b and b.get_text(strip=True).startswith("答案"):
            b.extract()
            html = p.decode_contents().strip()
            return re.sub(r"^[：:]\s*", "", html)
    return ""


def difficulty_prior(idx: int, n: int, qtype: str, last_of_type: bool) -> float:
    """按题位给出 0~1 的难度先验(题号越后越难, 每类题最后一题再加难)。可被作答数据校准。"""
    base = 0.12 + 0.70 * (idx / max(n - 1, 1))
    if last_of_type:
        base += 0.12
    if qtype == "解答":
        base += 0.05
    return round(min(base, 0.97), 3)


def full_score(qs: list[dict]) -> int:
    """选做题(二选一)只计一题分值。"""
    opt = [q["score"] for q in qs if q.get("optional")]
    return sum(q["score"] for q in qs if not q.get("optional")) + (max(opt) if opt else 0)


def parse_paper(root: Path, tax: Taxonomy, meta) -> tuple[dict, list[dict]]:
    pid, rel, region, year, kind, title, kpsrc = meta
    html = (root / rel).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    kp = load_kp(root, *kpsrc)
    ty = load_tiyan(root, pid)
    secs = [s for s in soup.find_all("section") if re.fullmatch(r"q\d+", s.get("id", ""))]
    raw = []
    for s in secs:
        h2 = s.find("h2")
        m = H2_RE.search(h2.get_text(" ", strip=True)) if h2 else None
        if not m:
            continue
        raw.append((s, int(m.group(1)), TYPE_NORM[m.group(2)], int(m.group(3)), m.group(2).startswith("选做")))
    n = len(raw)
    types = [r[2] for r in raw]
    qs = []
    for i, (s, no, qtype, score, optional) in enumerate(raw):
        warn = bool(s.find(string=re.compile("原题待核")))
        strip_blocks(s)
        h2 = s.find("h2")
        h2.decompose()
        stem_el = s.find("div", class_="def")
        stem = stem_el.decode_contents().strip() if stem_el else ""
        if stem_el:
            stem_el.decompose()
        answer = answer_of(BeautifulSoup(str(s), "html.parser"))
        solution = s.decode_contents().strip()
        sections = [{"book": k["book"], "sec": k["sec"], "detail": k.get("detail", "")} for k in kp.get(str(no), [])]
        tag, ty_items = tiyan_text(ty.get(str(no)))
        last_of_type = (i == n - 1) or types[i + 1] != qtype
        q = {
            "id": f"{pid}-{no:02d}",
            "paper": pid,
            "no": no,
            "type": qtype,
            "score": score,
            "region": region,
            "year": year,
            "kind": kind,
            "stem_html": clean_editorial(stem),
            "answer_html": clean_editorial(answer),
            "solution_html": clean_editorial(solution),
            "sections": sections,
            "tiyan_tag": tag,
            "tiyan": ty_items,
            "difficulty": difficulty_prior(i, n, qtype, last_of_type),
            "has_figure": "<svg" in stem or "<img" in stem,
            "verified": not warn,
            "optional": optional,
            "note": "",
        }
        tax.annotate(q)
        qs.append(q)
    paper = {"id": pid, "title": title, "region": region, "year": year, "kind": kind,
             "count": len(qs), "full_score": full_score(qs)}
    return paper, qs


def load_source(path: Path, tax: Taxonomy) -> tuple[dict, list[dict]]:
    """读取单套试卷的结构化 JSON(bank/source/<试卷号>.json), 补难度先验与标注。"""
    d = json.loads(path.read_text(encoding="utf-8"))
    meta = d["paper"]
    raw = sorted(d["questions"], key=lambda q: q["no"])
    n = len(raw)
    types = [q["type"] for q in raw]
    qs = []
    for i, r in enumerate(raw):
        last_of_type = (i == n - 1) or types[i + 1] != r["type"]
        sections = []
        for s in r.get("sections", []):
            s = {"book": s["book"], "sec": s.get("sec", ""), "detail": s.get("detail", "")}
            if s["book"] == "旧教材":
                s["name"] = s["detail"]
            sections.append(s)
        stem = clean_editorial(r["stem_html"])
        q = {
            "id": f"{meta['id']}-{r['no']:02d}", "paper": meta["id"], "no": r["no"],
            "type": r["type"], "score": r["score"], "region": meta["region"], "year": meta["year"],
            "kind": meta["kind"], "stem_html": stem,
            "answer_html": clean_editorial(r["answer_html"]),
            "solution_html": clean_editorial(r.get("solution_html", "")),
            "sections": sections, "tiyan_tag": r.get("tiyan_tag", ""), "tiyan": r.get("tiyan", []),
            "difficulty": r.get("difficulty") or difficulty_prior(i, n, r["type"], last_of_type),
            "has_figure": "<svg" in stem or "<img" in stem, "verified": True,
            "optional": bool(r.get("optional")), "note": "",
        }
        tax.annotate(q)
        qs.append(q)
    paper = {"id": meta["id"], "title": meta["title"], "region": meta["region"], "year": meta["year"],
             "kind": meta["kind"], "count": len(qs), "full_score": full_score(qs)}
    if meta.get("template"):
        paper["template"] = meta["template"]
    return paper, qs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kb_root")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "bank"))
    ap.add_argument("--overrides", help="逐题修订文件 {题号: {字段: 新内容}}, 用于编辑校订")
    a = ap.parse_args()
    root = Path(a.kb_root)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tax = Taxonomy.load()
    papers, allq = [], []
    for meta in PAPERS:
        if not (root / meta[1]).exists():
            print(f"跳过（文件不存在）：{meta[1]}")
            continue
        p, qs = parse_paper(root, tax, meta)
        papers.append(p)
        allq += qs
        print(f"{p['id']:<16} {p['count']:>3} 题  满分 {p['full_score']}")
    for path in sorted((out / "source").glob("*.json")):
        p, qs = load_source(path, tax)
        papers.append(p)
        allq += qs
        print(f"{p['id']:<16} {p['count']:>3} 题  满分 {p['full_score']}")
    if a.overrides:
        fix = json.loads(Path(a.overrides).read_text(encoding="utf-8"))
        for q in allq:
            if q["id"] in fix:
                q.update(fix[q["id"]])
                q["has_figure"] = "<svg" in q["stem_html"] or "<img" in q["stem_html"]
    # 填空题数值答案（供网页自动判分）；拿不准的不写
    n_fill = n_num = 0
    for q in allq:
        q.pop("answer_num", None)
        if q["type"] != "填空":
            continue
        n_fill += 1
        vals = numeric_answer(q["answer_html"], blanks=count_blanks(q["stem_html"]))
        if vals is not None:
            q["answer_num"] = vals
            n_num += 1
    print(f"填空题 {n_fill} 道，其中 {n_num} 道可自动判分（answer_num）")
    order = {"高考": 0, "模拟": 1}
    papers.sort(key=lambda p: (order.get(p["kind"], 2), p["region"] != "上海", p["region"], -p["year"], p["id"]))
    rank = {p["id"]: i for i, p in enumerate(papers)}
    allq.sort(key=lambda q: (rank[q["paper"]], q["no"]))
    (out / "papers.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out / "questions.jsonl").open("w", encoding="utf-8") as f:
        for q in allq:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"共 {len(papers)} 套、{len(allq)} 题 → {out}")


if __name__ == "__main__":
    main()
