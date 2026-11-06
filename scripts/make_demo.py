#!/usr/bin/env python3
"""生成虚构示例班级(仅用于演示，学生姓名、成绩、评语全部为程序随机生成)。

四次考试由组卷模块按「基础 → 提高 → 拔高 → 冲刺」自动组卷；作答由带潜在能力的
生成模型模拟，并埋入几条可被系统识别的「故事」，用来检验诊断是否找得出来：
  * 全班解析几何偏弱，根因是数学运算；
  * 一名学生运算强、逻辑推理弱；一名学生整体好但概率弱；一名学生持续进步；一名学生考试紧张。
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathinsight import paper  # noqa: E402
from mathinsight.bank import QuestionBank  # noqa: E402
from mathinsight.io import write_csv  # noqa: E402
from mathinsight.taxonomy import COMPETENCIES, UNITS  # noqa: E402

OUT = ROOT / "examples" / "demo_class"
SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗高郑梁谢宋唐许韩冯邓曹彭曾萧田董潘袁蔡蒋余于杜叶程")
GIVEN = list("子浩宇轩晨欣怡涵思雨佳琪俊杰博文梓萱一诺嘉懿明哲若溪雅静天佑沐阳书瑶安然知远清越语桐亦舟星辰")

STAGE_PLAN = [("M1", "高三一模（基础）", "2026-01-08", "基础"),
              ("M2", "高三二模（提高）", "2026-03-12", "提高"),
              ("M3", "高三三模（拔高）", "2026-04-16", "拔高"),
              ("M4", "高三四模（冲刺）", "2026-05-14", "冲刺")]


def sig(x):
    return 1 / (1 + math.exp(-x))


def main(n_students: int = 42, seed: int = 2026):
    rng = random.Random(seed)
    bank = QuestionBank.load()
    OUT.mkdir(parents=True, exist_ok=True)

    names = set()
    while len(names) < n_students:
        names.add(rng.choice(SURNAMES) + "".join(rng.sample(GIVEN, rng.choice([1, 2]))))
    names = sorted(names, key=lambda _: rng.random())
    students = [{"id": f"S{k + 1:02d}", "name": nm, "class": "高三（3）班（虚构示例）"} for k, nm in enumerate(names)]

    units = list(UNITS)
    lat = {}
    for s in students:
        lat[s["id"]] = {
            "theta": rng.gauss(1.0, 0.8),
            "growth": rng.gauss(0.06, 0.06),
            "delta": {u: rng.gauss(0, 0.4) for u in units},
            "gamma": {c: rng.gauss(0, 0.3) for c in COMPETENCIES},
            "nerves": 0.0,
            "story": "",
        }
        lat[s["id"]]["delta"]["解析几何"] -= 0.55          # 全班解析几何偏弱
        lat[s["id"]]["gamma"]["数学运算"] -= 0.35          # 根因：运算
    stories = {
        "S03": ("运算强、推理弱", lambda L: (L["gamma"].__setitem__("数学运算", 1.6), L["gamma"].__setitem__("逻辑推理", -1.8))),
        "S08": ("整体好、概率弱", lambda L: (L.__setitem__("theta", 1.7), L["delta"].__setitem__("概率", -2.2))),
        "S15": ("持续进步", lambda L: (L.__setitem__("theta", 0.0), L.__setitem__("growth", 0.35))),
        "S21": ("考试紧张", lambda L: (L.__setitem__("theta", 1.6), L.__setitem__("nerves", 0.9))),
    }
    for sid, (story, f) in stories.items():
        f(lat[sid])
        lat[sid]["story"] = story

    exams, used = [], set()
    for k, (eid, title, date, stage) in enumerate(STAGE_PLAN):
        ex = paper.build(bank, template="上海卷", stage=stage, exclude=used, seed=seed + k, exam_id=eid, title=title)
        ex["date"] = date
        used |= {it["qid"] for it in ex["items"]}
        exams.append(ex)

    b_true = {q["id"]: q["b"] + rng.gauss(0, 0.3) for q in bank.questions}
    rows = []
    for e_idx, ex in enumerate(exams):
        for s in students:
            L = lat[s["id"]]
            th = L["theta"] + L["growth"] * e_idx - (L["nerves"] if e_idx in (1, 3) else 0)
            for it in ex["items"]:
                q = bank[it["qid"]]
                w = {u: (1.0 if i == 0 else 0.5) for i, u in enumerate(q["units"])}
                t = sum(w.values())
                eta = th + sum(L["delta"][u] * v / t for u, v in w.items()) \
                    + sum(L["gamma"][c] * v for c, v in q["competencies"].items()) * 1.5 - b_true[q["id"]]
                p = sig(eta)
                full = it["score"]
                if q["type"] in ("填空", "单选"):
                    sc = full if rng.random() < p else 0
                elif q["type"] == "多选":
                    sc = full if rng.random() < p else (round(full * 0.4) if rng.random() < 0.5 else 0)
                else:
                    frac = min(max(p + rng.gauss(0, 0.15), 0), 1)
                    sc = round(frac * full)
                err = ""
                if sc < full and rng.random() < 0.65:
                    comp = max(q["competencies"], key=q["competencies"].get)
                    pool = {"数学运算": ["计算失误"] * 6 + ["思路缺失"] * 2 + ["审题错误"],
                            "逻辑推理": ["思路缺失"] * 4 + ["表述不完整"] * 3 + ["计算失误"],
                            "数学抽象": ["审题错误"] * 4 + ["思路缺失"] * 2 + ["知识遗忘"],
                            "直观想象": ["思路缺失"] * 3 + ["知识遗忘"] * 2 + ["计算失误"],
                            }.get(comp, ["知识遗忘", "思路缺失", "计算失误"])
                    if L["story"] == "运算强、推理弱" and q["type"] == "解答":
                        pool = ["表述不完整", "思路缺失"]
                    err = rng.choice(pool)
                rows.append({"student": s["id"], "exam": ex["id"], "qid": q["id"], "score": sc, "error": err})

    comments = []
    tpl = {
        "运算强、推理弱": "计算又快又准，但证明题步骤跳跃，逻辑表达弱，解答题常丢过程分。",
        "整体好、概率弱": "基础扎实，思维活跃，上课爱提问；概率题审题不细，事件关系常理解错。",
        "持续进步": "开学时基础薄弱，近两个月学习主动，坚持整理错题本，订正及时，进步明显。",
        "考试紧张": "平时作业质量高，但大考容易紧张，时间分配不当，后面的题常做不完。",
    }
    generic = ["上课认真，作业按时完成。", "计算比较粗心，常在最后一步算错。", "综合题畏难，压轴题经常空着。",
               "善于画图，数形结合用得好。", "审题不够仔细，漏看条件。", "学习主动，基础扎实。",
               "解题方法单一，题型一变就不会变通。", "书写不规范，步骤不全。"]
    for s in students:
        L = lat[s["id"]]
        if L["story"]:
            comments.append({"student": s["id"], "date": "2026-04-20", "text": tpl[L["story"]]})
        for t in rng.sample(generic, rng.choice([1, 1, 2])):
            comments.append({"student": s["id"], "date": "2026-03-20", "text": t})

    write_csv(OUT / "students.csv", students, ["id", "name", "class"])
    write_csv(OUT / "scores.csv", rows, ["student", "exam", "qid", "score", "error"])
    write_csv(OUT / "comments.csv", comments, ["student", "date", "text"])
    (OUT / "exams.json").write_text(json.dumps(exams, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "README.md").write_text(
        "# 虚构示例班级\n\n本目录所有学生姓名、成绩与评语均由 `scripts/make_demo.py` 随机生成，"
        "与任何真实个人无关，仅用于演示系统功能。\n\n埋入的故事（用于检验诊断）：\n\n"
        + "\n".join(f"- {sid}：{st}" for sid, (st, _) in stories.items())
        + "\n- 全班：解析几何偏弱，根因是数学运算\n", encoding="utf-8")
    print(f"示例班级：{len(students)} 人、{len(exams)} 次考试、{len(rows)} 条作答 → {OUT}")


if __name__ == "__main__":
    main()
