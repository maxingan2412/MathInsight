"""学情模型：Rasch 能力 / 题目难度联合校准 + 板块与素养掌握度估计。

模型
----
对学生 s 在题目 i 上的得分率 x_si ∈ [0, 1]：

    P(x_si) = σ(θ_s + Σ_u a_iu·δ_su − b_i)

* θ_s：学生总体能力；b_i：题目难度(先验来自题位, 由作答数据校准)；
* a_iu：题目 i 在板块 u 上的权重(主板块 1、关联板块 0.5, 归一化)；
* δ_su：学生 s 在板块 u 上相对自身总体水平的偏移，>0 为相对强项，<0 为相对弱项。

所有参数带高斯先验(L2 正则)，用批量梯度下降求 MAP 估计；解答题按分值加权。
同一套写法换成素养权重矩阵，就得到六大核心素养上的偏移 γ_sc。

掌握度 = σ(θ_s + δ_su − b̄_u)：该生做本板块「典型高考题」(难度取题库中该板块高考题的平均)
的预计得分率，便于老师直观理解。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .taxonomy import COMPETENCIES, UNITS

UNIT_NAMES = list(UNITS)


@dataclass
class Responses:
    """作答记录(长表)。"""
    student: list[str] = field(default_factory=list)
    exam: list[str] = field(default_factory=list)
    qid: list[str] = field(default_factory=list)
    score: list[float] = field(default_factory=list)
    full: list[float] = field(default_factory=list)
    error: list[str] = field(default_factory=list)

    def add(self, student, exam, qid, score, full, error=""):
        self.student.append(student)
        self.exam.append(exam)
        self.qid.append(qid)
        self.score.append(float(score))
        self.full.append(float(full))
        self.error.append(error or "")

    def __len__(self):
        return len(self.qid)


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class FitResult:
    students: list[str]
    items: list[str]
    theta: np.ndarray
    b: np.ndarray
    delta_unit: np.ndarray      # [S, U]
    gamma_comp: np.ndarray      # [S, C]
    evid_unit: np.ndarray       # [S, U] 有效题量
    evid_comp: np.ndarray       # [S, C]
    unit_b: np.ndarray          # [U] 题库中各板块高考题的平均难度

    def mastery_unit(self) -> np.ndarray:
        """在该板块「典型高考题」(难度取题库该板块平均)上的预计得分率。"""
        return _sig(self.theta[:, None] + self.delta_unit - self.unit_b[None, :])

    def mastery_comp(self) -> np.ndarray:
        return _sig(self.theta[:, None] + self.gamma_comp)

    def predict(self, s_idx: int, q: dict) -> float:
        """预测学生做某题(可以是没做过的题)的得分率。"""
        a = unit_weights(q)
        d = sum(w * self.delta_unit[s_idx, UNIT_NAMES.index(u)] for u, w in a.items())
        b = self.b[self.items.index(q["id"])] if q["id"] in self.items else q["b"]
        return float(_sig(self.theta[s_idx] + d - b))


def unit_weights(q: dict) -> dict[str, float]:
    w = {u: (1.0 if i == 0 else 0.5) for i, u in enumerate(q["units"])}
    t = sum(w.values())
    return {u: v / t for u, v in w.items()}


def fit(resp: Responses, bank, *, iters: int = 600, lr: float = 0.5,
        l2_theta: float = 0.05, l2_b: float = 3.0, l2_delta: float = 1.0) -> FitResult:
    students = sorted(set(resp.student))
    items = sorted(set(resp.qid))
    si = {s: k for k, s in enumerate(students)}
    ii = {q: k for k, q in enumerate(items)}
    S, I, U, C = len(students), len(items), len(UNIT_NAMES), len(COMPETENCIES)

    s_idx = np.array([si[s] for s in resp.student])
    i_idx = np.array([ii[q] for q in resp.qid])
    full = np.array(resp.full)
    x = np.clip(np.array(resp.score) / np.maximum(full, 1e-9), 0, 1)
    wt = 1.0 + full / 10.0                       # 分值大的题信息量大
    wt = wt / wt.mean()

    A = np.zeros((I, U))
    Cm = np.zeros((I, C))
    b0 = np.zeros(I)
    for q, k in ii.items():
        qq = bank[q]
        for u, w in unit_weights(qq).items():
            A[k, UNIT_NAMES.index(u)] = w
        for c, w in qq["competencies"].items():
            Cm[k, COMPETENCIES.index(c)] = w
        b0[k] = qq["b"]

    theta = np.zeros(S)
    b = b0.copy()
    delta = np.zeros((S, U))
    n = len(x)

    # 第一阶段：θ、b、δ 联合
    for _ in range(iters):
        eta = theta[s_idx] + (A[i_idx] * delta[s_idx]).sum(1) - b[i_idx]
        g = (x - _sig(eta)) * wt                 # 对 eta 的对数似然梯度
        gt = np.bincount(s_idx, g, S) - l2_theta * theta
        gb = -np.bincount(i_idx, g, I) - l2_b * (b - b0)
        gd = np.zeros((S, U))
        np.add.at(gd, s_idx, g[:, None] * A[i_idx])
        gd -= l2_delta * delta
        cnt_s = np.bincount(s_idx, minlength=S) + 1
        cnt_i = np.bincount(i_idx, minlength=I) + 1
        theta += lr * gt / cnt_s
        b += lr * gb / cnt_i
        delta += lr * gd / (cnt_s[:, None] * 0.25 + 1)
        b -= (b - b0).mean()                     # 固定尺度原点：题目难度以历年高考题位为常模

    # 第二阶段：θ、b 固定，估计素养偏移 γ
    gamma = np.zeros((S, C))
    base = theta[s_idx] - b[i_idx]
    for _ in range(iters):
        eta = base + (Cm[i_idx] * gamma[s_idx]).sum(1)
        g = (x - _sig(eta)) * wt
        gg = np.zeros((S, C))
        np.add.at(gg, s_idx, g[:, None] * Cm[i_idx])
        gg -= l2_delta * gamma
        gamma += lr * gg / (np.bincount(s_idx, minlength=S)[:, None] * 0.25 + 1)

    ev_u = np.zeros((S, U))
    np.add.at(ev_u, s_idx, A[i_idx])
    ev_c = np.zeros((S, C))
    np.add.at(ev_c, s_idx, Cm[i_idx])
    unit_b = np.zeros(U)
    for k, u in enumerate(UNIT_NAMES):
        bs = [q["b"] for q in bank.questions if q["units"][0] == u and q["kind"] == "高考"]
        unit_b[k] = float(np.mean(bs)) if bs else 0.0
    return FitResult(students, items, theta, b, delta, gamma, ev_u, ev_c, unit_b)
