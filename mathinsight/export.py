"""运行完整分析流水线，导出给网页端的数据文件(web/data/*.js)。

网页端是纯静态页面：数据以 JS 文件形式随页面加载，双击 index.html 即可离线打开。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import analytics, model, paper
from .bank import QuestionBank
from .comments import tag_comment
from .io import load_class
from .recommend import recommend
from .taxonomy import COMPETENCIES, THEMES, UNITS

WEB = Path(__file__).resolve().parents[1] / "web"


def run(class_dir: Path, bank: QuestionBank | None = None) -> dict:
    bank = bank or QuestionBank.load()
    cls = load_class(class_dir, bank)
    resp, exams = cls["responses"], cls["exams"]
    fit = model.fit(resp, bank)
    table = analytics.exam_table(resp, exams, bank)
    names = {s["id"]: s["name"] for s in cls["students"]}
    done_by = {}
    for s, q in zip(resp.student, resp.qid):
        done_by.setdefault(s, set()).add(q)

    profiles = {}
    for k, sid in enumerate(fit.students):
        p = analytics.student_profile(fit, k, resp, exams, table, bank, cls["comments"])
        p["name"] = names.get(sid, sid)
        p["practice"] = recommend(fit, k, bank, done=done_by.get(sid, set()))
        profiles[sid] = p

    overview = analytics.class_overview(fit, resp, bank, exams, table)
    analyses = [paper.analyze(bank, ex) for ex in exams]
    cmp_ = paper.compare(bank, exams)
    used = {it["qid"] for ex in exams for it in ex["items"]}
    nxt = paper.build(bank, template=exams[-1].get("template", "上海卷"), stage="冲刺", exclude=used,
                      seed=99, exam_id="NEXT", title="下一轮冲刺卷（系统自动组卷）")
    item_stats = {}
    for q, sc, fu in zip(resp.qid, resp.score, resp.full):
        a = item_stats.setdefault(q, [0.0, 0.0])
        a[0] += sc
        a[1] += fu
    return {
        "meta": {"class": cls["students"][0]["class"] if cls["students"] else "", "n_students": len(fit.students),
                 "units": list(UNITS), "unit_theme": {u: UNITS[u][0] for u in UNITS}, "themes": THEMES,
                 "competencies": COMPETENCIES, "synthetic": True},
        "students": [{"id": s["id"], "name": s["name"]} for s in cls["students"]],
        "exams": exams, "exam_table": table, "overview": overview, "profiles": profiles,
        "paper_analysis": analyses, "paper_compare": cmp_,
        "next_paper": {"exam": nxt, "analysis": paper.analyze(bank, nxt)},
        "item_rate": {q: round(v[0] / v[1], 3) for q, v in item_stats.items()},
        "comment_tags": {sid: tag_comment(" ".join(c["text"] for c in cls["comments"] if c["student"] == sid))
                         for sid in names},
    }


def bank_payload(bank: QuestionBank) -> dict:
    keep = ["id", "paper", "no", "type", "score", "region", "year", "kind", "stem_html", "answer_html",
            "solution_html", "sections", "units", "theme", "competencies", "tiyan_tag", "tiyan", "difficulty",
            "verified", "optional", "note", "answer_num"]
    return {"papers": list(bank.papers.values()), "stats": bank.stats(),
            "questions": [{k: q.get(k) for k in keep} for q in bank.questions]}


def write_web(data: dict, bank: QuestionBank, web: Path = WEB):
    d = web / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "class.js").write_text("window.MI_CLASS = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    (d / "bank.js").write_text("window.MI_BANK = " + json.dumps(bank_payload(bank), ensure_ascii=False) + ";\n",
                               encoding="utf-8")
