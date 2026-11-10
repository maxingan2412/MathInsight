"""班级数据读写。老师用 Excel 就能维护的四个文件：

    students.csv   id,name,class
    exams.json     [{"id","title","date","stage","items":[{"qid","score"}]}]
    scores.csv     student,exam,qid,score,error      (error 可空：计算失误/审题错误/思路缺失/表述不完整/知识遗忘)
    comments.csv   student,date,text                 (教师主观评价，可多条)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .model import Responses


def load_class(d: Path, bank) -> dict:
    d = Path(d)
    students = list(csv.DictReader((d / "students.csv").open(encoding="utf-8")))
    exams = json.loads((d / "exams.json").read_text(encoding="utf-8"))
    full = {(e["id"], it["qid"]): it["score"] for e in exams for it in e["items"]}
    resp = Responses()
    for r in csv.DictReader((d / "scores.csv").open(encoding="utf-8")):
        if r["qid"] not in bank.by_id:
            raise KeyError(f"scores.csv 中的题号 {r['qid']} 不在题库里")
        resp.add(r["student"], r["exam"], r["qid"], float(r["score"]), full[(r["exam"], r["qid"])], r.get("error", ""))
    comments = []
    p = d / "comments.csv"
    if p.exists():
        comments = list(csv.DictReader(p.open(encoding="utf-8")))
    return {"students": students, "exams": exams, "responses": resp, "comments": comments}


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
