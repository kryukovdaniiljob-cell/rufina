# -*- coding: utf-8 -*-
"""Графики для аналитической записки. Рисуются в PNG и вставляются в Word."""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

СИНИЙ, ЗЕЛЁНЫЙ, КРАСНЫЙ, СЕРЫЙ, ОРАНЖ = "#2E5FA3", "#2F7D32", "#C0392B", "#8A94A0", "#D97706"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": "#C9CFD6", "axes.linewidth": .8,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.dpi": 200,
})
_мln = FuncFormatter(lambda v, _: ("%.0f" % v).replace("-", "−"))


def _сохранить(fig, папка, имя):
    os.makedirs(папка, exist_ok=True)
    p = os.path.join(папка, имя)
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def запас_и_оборот(ряды: dict, папка: str) -> str | None:
    мес = ряды.get("месяцы") or []
    if len(мес) < 2:
        return None
    x = np.arange(len(мес))
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    ax.bar(x - .2, ряды["оборот"], .4, label="Оборот за месяц", color=ЗЕЛЁНЫЙ)
    ax.bar(x + .2, ряды["запас"], .4, label="Запас на конец месяца", color=СИНИЙ)
    ax.set_xticks(x); ax.set_xticklabels([m[:3] for m in мес])
    ax.set_ylabel("млн ₽"); ax.yaxis.set_major_formatter(_мln)
    ax.grid(axis="y", color="#E8EBEF", lw=.8); ax.set_axisbelow(True)
    ax.legend(frameon=False, ncol=2, loc="upper left", fontsize=8)
    # подпись тренда запаса
    if ряды["запас"][0] > 0:
        рост = 100 * (ряды["запас"][-1] / ряды["запас"][0] - 1)
        ax.annotate("запас %+.0f %%" % рост, xy=(len(мес) - 1 + .2, ряды["запас"][-1]),
                    xytext=(0, 6), textcoords="offset points", ha="center",
                    fontsize=8, color=СИНИЙ, fontweight="bold")
    return _сохранить(fig, папка, "01_запас_оборот.png")


def gmroi_по_направлениям(l2: pd.DataFrame, порог: float, папка: str) -> str | None:
    d = l2[l2["GMROI"].notna()].copy()
    if not len(d):
        return None
    d = d.sort_values("GMROI")
    имена = [str(r["Товарное направление"])[:34] for _, r in d.iterrows()]
    знач = d["GMROI"].tolist()
    цвета = [КРАСНЫЙ if v < порог else (ЗЕЛЁНЫЙ if v >= 1.5 else СИНИЙ) for v in знач]
    fig, ax = plt.subplots(figsize=(7.2, max(2.2, .32 * len(d))))
    ax.barh(имена, знач, color=цвета, height=.62)
    ax.axvline(порог, color=ОРАНЖ, lw=1.4, ls="--")
    ax.annotate("порог окупаемости хранения %.2f" % порог, xy=(порог, len(d) - .4),
                xytext=(4, 0), textcoords="offset points", fontsize=8, color=ОРАНЖ)
    for i, v in enumerate(знач):
        ax.text(v + max(знач) * .012, i, ("%.2f" % v).replace(".", ","),
                va="center", fontsize=8, color="#333")
    ax.set_xlabel("GMROI — валовая прибыль за год на рубль запаса")
    ax.grid(axis="x", color="#E8EBEF", lw=.8); ax.set_axisbelow(True)
    ax.set_xlim(min(0, min(знач) * 1.15), max(знач) * 1.16)
    return _сохранить(fig, папка, "02_gmroi.png")


def куда_вложены_деньги(S: dict, папка: str) -> str | None:
    части = [
        ("Работает нормально", max(S["запас"] - S["вывести"]["запас"]
                                   - S["медленные"]["запас"] - S["новинки"]["запас"], 0), ЗЕЛЁНЫЙ),
        ("Медленный товар", S["медленные"]["запас"], ОРАНЖ),
        ("Нет продаж (неликвид)", S["вывести"]["запас"], КРАСНЫЙ),
        ("Новинки без старта", S["новинки"]["запас"], СЕРЫЙ),
    ]
    части = [(n, v, c) for n, v, c in части if v > 0]
    if not части:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 1.45))
    лево = 0.0
    всего = sum(v for _, v, _ in части)
    for имя, знач, цвет in части:
        ax.barh([0], [знач / 1e6], left=[лево / 1e6], color=цвет, height=.55)
        доля = 100 * знач / всего
        if доля > 4:
            ax.text((лево + знач / 2) / 1e6, 0, "%.1f млн\n%.0f %%" % (знач / 1e6, доля),
                    ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
        лево += знач
    ax.set_yticks([]); ax.set_xlabel("млн ₽ себестоимости запаса")
    ax.set_xlim(0, всего / 1e6)
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in части],
              [n for n, _, _ in части], frameon=False, ncol=len(части),
              loc="upper center", bbox_to_anchor=(.5, -.45), fontsize=8)
    for s in ("left", "bottom"):
        ax.spines[s].set_visible(False)
    return _сохранить(fig, папка, "03_структура_запаса.png")


def дефицит_по_месяцам(ряды: dict, папка: str) -> str | None:
    мес = ряды.get("месяцы") or []
    oos = ряды.get("oos") or []
    if len(мес) < 2 or not any(oos):
        return None
    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    ax.plot(range(len(мес)), oos, marker="o", ms=4, color=КРАСНЫЙ, lw=1.8)
    ax.fill_between(range(len(мес)), oos, color=КРАСНЫЙ, alpha=.10)
    ax.set_xticks(range(len(мес))); ax.set_xticklabels([m[:3] for m in мес])
    ax.set_ylabel("OOS, %"); ax.set_ylim(0, max(oos) * 1.25)
    ax.grid(axis="y", color="#E8EBEF", lw=.8); ax.set_axisbelow(True)
    for i, v in enumerate(oos):
        ax.annotate("%.0f" % v, (i, v), xytext=(0, 6), textcoords="offset points",
                    ha="center", fontsize=7.5, color="#555")
    return _сохранить(fig, папка, "04_oos.png")


def приоритеты_усилие_эффект(P: list, папка: str) -> str | None:
    if not P:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    x = [p["усилие"] for p in P]
    y = [p["эффект_год"] / 1e6 for p in P]
    размер = [max(140, min(1500, (p["деньги"] / 1e6) * 130)) for p in P]
    ax.scatter(x, y, s=размер, c=[ЗЕЛЁНЫЙ if p["отдача"] >= np.median([q["отдача"] for q in P])
                                  else СИНИЙ for p in P], alpha=.75, edgecolors="white", lw=1.5)
    for p, xi, yi in zip(P, x, y):
        ax.annotate(p["имя"], (xi, yi), xytext=(0, 16), textcoords="offset points",
                    ha="center", fontsize=8, color="#222")
    ax.set_xlabel("Усилие: 1 — сделать сразу, 4 — нужны согласования")
    ax.set_ylabel("Эффект, млн ₽/год")
    ax.set_xticks([1, 2, 3, 4]); ax.set_xlim(.4, 4.6)
    ax.set_ylim(min(0, min(y)) - .4, max(y) * 1.45 + .3)
    ax.grid(color="#E8EBEF", lw=.8); ax.set_axisbelow(True)
    ax.annotate("размер круга — сколько денег высвобождается", xy=(.02, .94),
                xycoords="axes fraction", fontsize=7.5, color=СЕРЫЙ)
    return _сохранить(fig, папка, "05_приоритеты.png")


def все(S: dict, св: dict, ряды: dict, папка: str, лог=print) -> dict:
    г = {}
    try:
        г["запас_оборот"] = запас_и_оборот(ряды, папка)
        г["gmroi"] = gmroi_по_направлениям(св["L2_Направление"], S["порог"], папка)
        г["структура"] = куда_вложены_деньги(S, папка)
        г["oos"] = дефицит_по_месяцам(ряды, папка)
        г["приоритеты"] = приоритеты_усилие_эффект(S.get("приоритеты", []), папка)
    except Exception as e:
        лог("   ! Графики построить не удалось: %s" % e)
    г = {k: v for k, v in г.items() if v}
    лог("   Графиков построено: %d" % len(г))
    return г
