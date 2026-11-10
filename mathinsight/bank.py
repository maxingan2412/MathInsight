"""题库：加载、检索、统计。"""
from __future__ import annotations

import json
from pathlib import Path

BANK = Path(__file__).resolve().parents[1] / "bank"


def logit_from_prior(d: float) -> float:
    """把 0~1 难度先验映射到 Rasch 难度(logit)。0.5 ↔ 0。"""
    d = min(max(d, 0.03), 0.97)
    return round(4.0 * (d - 0.5), 3)


class QuestionBank:
    def __init__(self, questions: list[dict], papers: list[dict]):
        self.questions = questions
        self.by_id = {q["id"]: q for q in questions}
        self.papers = {p["id"]: p for p in papers}
        for q in questions:
            q.setdefault("b", logit_from_prior(q.get("difficulty", 0.5)))

    @classmethod
    def load(cls, root: Path | None = None) -> "QuestionBank":
        root = root or BANK
        qs = [json.loads(line) for line in (root / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        papers = json.loads((root / "papers.json").read_text(encoding="utf-8"))
        return cls(qs, papers)

    def __len__(self) -> int:
        return len(self.questions)

    def __getitem__(self, qid: str) -> dict:
        return self.by_id[qid]

    def filter(self, *, units=None, types=None, regions=None, kinds=None, years=None,
               b_range=None, exclude=None, verified_only=False) -> list[dict]:
        out = []
        for q in self.questions:
            if units and not set(units) & set(q["units"]):
                continue
            if types and q["type"] not in types:
                continue
            if regions and q["region"] not in regions:
                continue
            if kinds and q["kind"] not in kinds:
                continue
            if years and q["year"] not in years:
                continue
            if b_range and not (b_range[0] <= q["b"] <= b_range[1]):
                continue
            if exclude and q["id"] in exclude:
                continue
            if verified_only and not q.get("verified", True):
                continue
            out.append(q)
        return out

    def stats(self) -> dict:
        from collections import Counter
        return {
            "papers": len(self.papers),
            "questions": len(self.questions),
            "by_region": dict(Counter(q["region"] for q in self.questions)),
            "by_kind": dict(Counter(q["kind"] for q in self.questions)),
            "by_type": dict(Counter(q["type"] for q in self.questions)),
            "by_unit": dict(Counter(q["units"][0] for q in self.questions)),
            "years": sorted({q["year"] for q in self.questions}),
        }
