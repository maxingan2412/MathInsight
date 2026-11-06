"""命令行入口：python -m mathinsight <命令>

  bank                         题库概况
  analyze <班级目录>            运行完整分析并导出网页数据(web/data/)
  student <班级目录> <学号>      在终端打印一个学生的诊断与练习建议
  paper <班级目录> <考试号>      打印一次考试的试卷分析
  build --stage 冲刺 [--template 上海卷]   按阶段自动组卷
  variants <题号> [--level 拔高]  调用大模型生成变式题(需配置 MI_LLM_*)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bank import QuestionBank


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mathinsight", description="数鉴（MathInsight）：高中数学智能学情分析与个性化辅导系统")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bank")
    a = sub.add_parser("analyze")
    a.add_argument("class_dir")
    s = sub.add_parser("student")
    s.add_argument("class_dir")
    s.add_argument("sid")
    p = sub.add_parser("paper")
    p.add_argument("class_dir")
    p.add_argument("exam")
    b = sub.add_parser("build")
    b.add_argument("--stage", default="基础")
    b.add_argument("--template", default="上海卷")
    b.add_argument("--seed", type=int, default=0)
    v = sub.add_parser("variants")
    v.add_argument("qid")
    v.add_argument("--level", default="巩固")
    v.add_argument("--n", type=int, default=2)
    v.add_argument("--dry", action="store_true", help="只打印提示词，不调用模型")
    args = ap.parse_args(argv)
    bank = QuestionBank.load()

    if args.cmd == "bank":
        print(json.dumps(bank.stats(), ensure_ascii=False, indent=1))
    elif args.cmd == "analyze":
        from .export import run, write_web
        data = run(Path(args.class_dir), bank)
        write_web(data, bank)
        ov = data["overview"]
        print(f"已分析 {data['meta']['n_students']} 名学生、{len(data['exams'])} 次考试；网页数据已写入 web/data/")
        print("班级薄弱板块：", "、".join(ov["weak_units"]))
        for d in ov["diagnoses"]:
            print(" -", d["text"])
    elif args.cmd == "student":
        from .export import run
        data = run(Path(args.class_dir), bank)
        p = data["profiles"][args.sid]
        print(f"{p['name']}（{p['id']}）强项：{'、'.join(p['strong']) or '—'}；弱项：{'、'.join(p['weak']) or '—'}")
        for t in p["trend"]:
            print(f"  {t['title']}: {t['total']}/{t['full']}  第 {t['rank']} 名")
        print("建议：")
        for x in p["advice"]:
            print("  " + x)
        for g in p["practice"]["groups"]:
            print(f"  练习·{g['unit']}：" + "、".join(f"{i['qid']}({i['role']},预计{i['pred']:.0%})" for i in g["items"]))
    elif args.cmd == "paper":
        from .export import run
        data = run(Path(args.class_dir), bank)
        an = next(x for x in data["paper_analysis"] if x["id"] == args.exam)
        print(json.dumps({k: an[k] for k in ("title", "total", "mean_difficulty", "unit_share", "gaps", "over", "under")},
                         ensure_ascii=False, indent=1))
    elif args.cmd == "build":
        from . import paper
        ex = paper.build(bank, template=args.template, stage=args.stage, seed=args.seed)
        print(json.dumps(paper.analyze(bank, ex) | {"items": ex["items"]}, ensure_ascii=False, indent=1))
    elif args.cmd == "variants":
        from . import variants
        q = bank[args.qid]
        if args.dry:
            print(variants.build_prompt(q, args.level, args.n))
        else:
            print(json.dumps(variants.generate(q, args.level, args.n), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
