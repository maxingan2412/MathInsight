"""题库答案的机械核对。"""
import json
import re
from pathlib import Path

BANK = Path(__file__).resolve().parents[1] / "bank" / "questions.jsonl"


def _text(html):
    return re.sub(r"<[^>]+>", "", html or "")


def test_equation_blanks_keep_equals_sign():
    """题干以「…方程为____」收尾的填空题，答案必须是带等号的完整方程。"""
    bad = []
    for line in BANK.read_text(encoding="utf-8").splitlines():
        q = json.loads(line)
        if q["type"] != "填空":
            continue
        if re.search(r"方程为\s*_+\s*[．.。]?\s*$", _text(q["stem_html"])) and "=" not in _text(q["answer_html"]):
            bad.append(q["id"])
    assert not bad, bad
