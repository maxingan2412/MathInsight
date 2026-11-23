"""推荐练习的提示阶梯里不得带出填空题的最终答案。"""
import json
from pathlib import Path

from mathinsight.recommend import answer_leaks

WEB = Path(__file__).resolve().parents[1] / "web" / "data"


def _load(name):
    s = (WEB / name).read_text(encoding="utf-8")
    return json.loads(s[s.index("{"): s.rindex("}") + 1])


def test_fill_in_hints_do_not_contain_answer():
    bank = {q["id"]: q for q in _load("bank.js")["questions"]}
    cls = _load("class.js")
    bad, n = [], 0
    for s in cls["students"]:
        for g in cls["profiles"][s["id"]]["practice"]["groups"]:
            for it in g["items"]:
                q = bank[it["qid"]]
                if q["type"] != "填空":
                    continue
                n += 1
                bad += [(q["id"], h[:40]) for h in it["hints"] if answer_leaks(q, h)]
    assert n > 0
    assert not bad, bad[:10]
