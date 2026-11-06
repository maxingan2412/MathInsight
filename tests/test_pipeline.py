"""端到端测试：题库完整性、组卷梯度、示例班级中埋入的故事能被诊断出来。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mathinsight import paper  # noqa: E402
from mathinsight.bank import QuestionBank  # noqa: E402
from mathinsight.comments import tag_comment  # noqa: E402
from mathinsight.export import run  # noqa: E402

BANK = QuestionBank.load()


def test_bank_complete():
    assert len(BANK) >= 300
    for q in BANK.questions:
        assert q["stem_html"] and q["answer_html"] and q["units"] and q["competencies"]


def test_paper_templates_and_stages():
    diffs = []
    used = set()
    for k, st in enumerate(paper.STAGES):
        ex = paper.build(BANK, stage=st, exclude=used, seed=k)
        assert sum(it["score"] for it in ex["items"]) == 150
        used |= {it["qid"] for it in ex["items"]}
        diffs.append(paper.analyze(BANK, ex)["mean_difficulty"])
    assert diffs == sorted(diffs), diffs


def test_demo_diagnosis():
    data = run(ROOT / "examples" / "demo_class", BANK)
    ov = data["overview"]
    assert ov["weak_units"][0] == "解析几何"
    assert ov["diagnoses"][0]["main_competency"] == "数学运算"
    assert "概率" in data["profiles"]["S08"]["weak"]
    ranks = [t["rank"] for t in data["profiles"]["S15"]["trend"]]
    assert ranks[-1] < ranks[0]


def test_comment_tags():
    tags = {t["tag"] for t in tag_comment("计算粗心，压轴题经常空着，但善于画图")}
    assert {"计算粗心", "综合题畏难", "善于数形结合"} <= tags
