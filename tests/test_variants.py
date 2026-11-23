"""变式题提示词按 docs/变式题标准.md 拼装(不调用模型)。"""
from mathinsight import variants
from mathinsight.bank import QuestionBank


def test_prompt_carries_standard_and_materials():
    bank = QuestionBank.load()
    q = bank["I-2024-06"]
    for d, desc in variants.DISTANCES.items():
        p = variants.build_prompt(q, "巩固", 2, distance=d, bank=bank)
        assert "保留第 ③ 层，更换第 ② 层" in p and "照抄会失败" in p
        assert desc in p and "接口条件" in p            # 相似度档位与原题题眼都在
        assert q["id"] not in p                          # 范例里不含原题自己
    c = variants.build_check_prompt(q, {"stem": "S", "answer": "A"})
    assert "copy_ok" in c and "tiyan_ok" in c


def test_exemplars_share_topic_and_exclude_same_paper():
    bank = QuestionBank.load()
    q = bank["I-2024-06"]
    ex = variants.exemplars(q, bank)
    assert ex and all(x["paper"] != q["paper"] for x in ex)
