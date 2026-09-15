# -*- coding: utf-8 -*-
"""HTML-дашборд: автономный файл, открывается двойным кликом, без интернета.

Основной режим просмотра — раскрывающееся дерево по иерархии: клик по треугольнику
разворачивает уровень, поиск сам раскрывает ветки с совпадениями.
"""
from __future__ import annotations
import os, json
import numpy as np
import pandas as pd
from reports import млн, цел, пц

# деревья: (ключ, [(свёртка, [колонки пути])...])
ДЕРЕВЬЯ = {
    "hier": [("L1_Группа планирования", ["Группа планирования"]),
             ("L2_Направление",         ["Группа планирования", "Товарное направление"]),
             ("L3_Группа 1",            ["Группа планирования", "Товарное направление", "Группа 1"]),
             ("L4_Группа 2",            ["Группа планирования", "Товарное направление", "Группа 1", "Группа 2"]),
             ("L5_Группа 3",            ["Группа планирования", "Товарное направление", "Группа 1", "Группа 2", "Группа 3"])],
    "wh":   [("W1_Филиал",   ["Филиал"]),
             ("W1b_Офис",    ["Филиал", "Офис"]),
             ("W3_Склад",    ["Филиал", "Офис", "Склад"])],
    "brand": [("B1_Бренд",              ["Бренд"]),
              ("B2_Бренд x Направление", ["Бренд", "Товарное направление"])],
}
ПЛОСКИЕ = [("seg_xyz", "S1_Сегмент XYZ", ["XYZ"]),
           ("seg_abc", "S4_ABC", ["ABC"]),
           ("seg_liq", "S2_Ликвидность", ["Признак ликвидности"]),
           ("seg_st",  "S5_Статус позиции", ["Статус позиции"]),
           ("wtype",   "W2_Тип склада", ["Тип склада"]),
           ("w4",      "W4_Направление x Склад", ["Товарное направление", "Склад"])]


def _окр(v, зн=0):
    if v is None or pd.isna(v) or (isinstance(v, float) and not np.isfinite(v)):
        return None
    v = round(float(v), зн)
    return int(v) if зн == 0 else v


def _ряд(r, мк):
    """Помесячная выручка для спарклайна, в тысячах."""
    if not мк:
        return None
    з = [_окр((r.get(c) or 0) / 1000) for c in мк]
    return з if any(з) else None


def _узел(r, путь, мк):
    м = r.get("Маржа_%")
    м = None if (м is None or pd.isna(м) or abs(м) > 1e4) else _окр(м, 1)
    return {"p": путь, "sku": int(r.SKU), "dead": int(r["SKU_мёртвых"]),
            "rev": _окр(r.Оборот), "mar": м, "st": _окр(r.Запас),
            "d": _окр(r.get("Дней_запаса")), "g": _окр(r.get("GMROI"), 2),
            "ep": _окр(r.Эконом_прибыль), "oos": _окр(r.get("OOS_%"), 1),
            "z": _окр(r.get("Засол_%"), 1), "m": _ряд(r, мк)}


def _собрать_дерево(св, слои):
    узлы, мк = [], None
    for имя, ключи in слои:
        if имя not in св:
            continue
        df = св[имя]
        if мк is None:
            мк = sorted([c for c in df.columns
                         if len(str(c)) == 3 and str(c).startswith("М") and str(c)[1:].isdigit()])
        ключи = [k for k in ключи if k in df.columns]
        for _, r in df.iterrows():
            путь = [str(r[k]) for k in ключи if pd.notna(r[k])]
            if путь:
                узлы.append(_узел(r, путь, мк))
    return узлы


def _собрать_плоский(df, ключи):
    мк = sorted([c for c in df.columns
                 if len(str(c)) == 3 and str(c).startswith("М") and str(c)[1:].isdigit()])
    ключи = [k for k in ключи if k in df.columns]
    return sorted((_узел(r, [" · ".join(str(r[k]) for k in ключи)], мк) for _, r in df.iterrows()),
                  key=lambda x: -(x["rev"] or 0))


def _bars(labels, series, colors, height=170):
    n = len(labels) or 1; ns = len(series); W, H = 860, height
    pl, pb, pt = 54, 26, 12; iw = W - pl - 12; ih = H - pb - pt
    mx = max((max(s) if s else 0) for s in series) or 1
    gw = iw / n; bw = min(26, (gw - 8) / max(ns, 1))
    o = ['<svg viewBox="0 0 %d %d" class="chart">' % (W, H)]
    for t in range(5):
        y = pt + ih - ih * t / 4
        o.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (pl, y, W - 12, y))
        o.append('<text class="ax" x="%d" y="%.1f" text-anchor="end">%s</text>'
                 % (pl - 6, y + 3, ("%.0f" % (mx * t / 4)).replace(".", ",")))
    for i, lab in enumerate(labels):
        x0 = pl + i * gw
        for j, s in enumerate(series):
            if i >= len(s):
                continue
            h = ih * (s[i] / mx)
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2">'
                     '<title>%s · %s</title></rect>'
                     % (x0 + (gw - bw * ns) / 2 + j * bw, pt + ih - h, bw - 2, max(h, .5),
                        colors[j], lab, ("%.2f" % s[i]).replace(".", ",")))
        o.append('<text class="ax" x="%.1f" y="%d" text-anchor="middle">%s</text>'
                 % (x0 + gw / 2, H - 8, lab[:3]))
    return "".join(o) + "</svg>"


ДЕНЬГИ_К = ("Оборот","Запас","ВП","Владение","Эконом_прибыль","План","Факт","Разница","Упущено",
            "Содержание_год","Цель_ВП","Потолок_ВП","Излишек_запаса","Оборот 2025","Оборот 2026")
ПРОЦ_К = ("Маржа_%","Выполнение_%","Рост_%","Доля_оборота_%","Доля_запаса_%","Доля 2025, %",
          "Доля 2026, %","Сдвиг доли, п.п.","Доля_упущенного_%","Профит 2025, %","Профит 2026, %")


def _таблица(df, порог=None, макс=60):
    """Простая HTML-таблица из готового DataFrame."""
    if df is None or not len(df):
        return ""
    d = df.head(макс)
    шапка = "".join('<th class="%s">%s</th>' % ("num" if c in ДЕНЬГИ_К or c in ПРОЦ_К
                                                or c in ("SKU","GMROI") else "", c)
                    for c in d.columns)
    строки = []
    for _, r in d.iterrows():
        яч = []
        for c in d.columns:
            v = r[c]
            if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v):
                яч.append('<td class="num mut">—</td>'); continue
            if c in ДЕНЬГИ_К:
                яч.append('<td class="num%s">%s</td>' % (" neg" if v < 0 else "", млн(v)))
            elif c in ПРОЦ_К:
                яч.append('<td class="num">%s %%</td>' % пц(v))
            elif c == "GMROI":
                кл = "bad" if (порог and v < порог) else ""
                яч.append('<td class="num %s">%s</td>' % (кл, пц(v, 2)))
            elif isinstance(v, (int, float, np.integer, np.floating)):
                яч.append('<td class="num">%s</td>' % цел(v))
            else:
                яч.append("<td>%s</td>" % str(v)[:90])
        строки.append("<tr>" + "".join(яч) + "</tr>")
    return ('<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (шапка, "".join(строки)))


def dashboard(путь, св, списки, S, cfg, ряды, лог=print):
    порог = S["порог"]; хор = float(cfg["экономика"]["порог_gmroi_хороший"])
    лимит_sku = int(cfg["отчёты"]["sku_в_дашборде"])

    D = {}
    for ключ, слои in ДЕРЕВЬЯ.items():
        D[ключ] = _собрать_дерево(св, слои)
    # SKU подвешиваем в дерево иерархии как самый глубокий уровень
    if "L6_SKU" in св:
        df = св["L6_SKU"].head(лимит_sku)
        мк = sorted([c for c in df.columns
                     if len(str(c)) == 3 and str(c).startswith("М") and str(c)[1:].isdigit()])
        путьк = ["Группа планирования", "Товарное направление", "Группа 1", "Группа 2", "Группа 3",
                 "Название номенклатуры"]
        путьк = [k for k in путьк if k in df.columns]
        D["sku"] = [_узел(r, [str(r[k]) for k in путьк if pd.notna(r[k])], мк) for _, r in df.iterrows()]
    for ключ, имя, keys in ПЛОСКИЕ:
        if имя in св:
            D[ключ] = _собрать_плоский(св[имя], keys)

    мес = ряды.get("месяцы", [])
    KPI = [
     ("Запас периметра", млн(S["запас"]) + " млн ₽", "средний %s млн ₽" % млн(S["запас_средний"]), "blue"),
     ("Оборот за %d дней" % S["дней"], млн(S["оборот"]) + " млн ₽", "валовая %s млн ₽" % млн(S["вп"]), "blue"),
     ("Маржа", пц(S["маржа"]) + " %", "по обороту", "green"),
     ("GMROI", пц(S["gmroi"], 2), "порог владения %s" % пц(порог, 2),
      "green" if S["gmroi"] >= порог else "red"),
     ("Прибыль за вычетом содержания", млн(S["эконом_прибыль"]) + " млн ₽/год", "валовая ЗА ГОД минус владение",
      "green" if S["эконом_прибыль"] > 0 else "red"),
     ("OOS", пц(S["oos"]) + " %", "Fill Rate %s %%" % пц(S["fill_rate"]), "red"),
     ("Упущенные продажи", млн(S["упущено"]) + " млн ₽", "DNS %s ед." % цел(S["dns"]), "red"),
     ("Не отрабатывают владение", "%d напр." % S["плохих_направлений"],
      "запас %s млн ₽" % млн(S["плохих_запас"]), "orange"),
    ]
    kpi = "".join('<div class="kpi %s"><div class="kl">%s</div><div class="kv">%s</div>'
                  '<div class="ks">%s</div></div>' % (c, t, v, s) for t, v, s, c in KPI)

    # ---- часть 3: план-факт, LFL и новые разрезы
    ч3 = S.get("часть3") or {}
    пф = ч3.get("план_факт") or {}
    лф = ч3.get("lfl") or {}
    куски = []
    осн = (пф.get("планы") or {}).get("ИТАН") or next(iter((пф.get("планы") or {}).values()), None)
    if осн and осн.get("выполнение") is not None:
        пл = [осн["по_месяцам"].get(m, 0) / 1e6 for m in мес]
        фк = [пф["факт_по_месяцам"].get(m, 0) / 1e6 for m in мес]
        цвет = "#C0392B" if осн["выполнение"] < 90 else "#2F7D32"
        куски.append(
            '<h2>План и факт по месяцам, млн ₽</h2><div class="card">'
            '<div class="lg"><span><i style="background:#8A94A0"></i>План</span>'
            '<span><i style="background:#5BA85A"></i>Факт</span></div>' +
            _bars(мес, [пл, фк], ["#8A94A0", "#5BA85A"]) +
            '<div class="note" style="border-left-color:%s">План выполнен на <b>%s %%</b> '
            'за %d завершённых месяцев: %s из %s млн ₽. Текущий месяц не в счёт — он неполный.'
            '</div></div>' % (цвет, пц(осн["выполнение"]), len(пф.get("полные") or []),
                              млн(осн["факт_полные"]), млн(осн["план_полные"])))
    if лф.get("рост_%") is not None:
        пред = ('<div class="note">Сравнение по направлениям невозможно: между годами товар '
                'переразнесли, доля отдельных направлений сдвинулась до %s п.п.</div>'
                % пц(лф.get("макс_сдвиг_доли", 0), 0)) if not лф.get("сопоставимо_по_направлениям", True) else ""
        куски.append('<h2>Сравнение с прошлым годом</h2><div class="card">'
                     '<p>За %d завершённых месяцев: <b>%s</b> млн ₽ в прошлом году против '
                     '<b>%s</b> млн ₽ в этом — <b>%s %%</b>.</p>%s%s</div>'
                     % (len(лф.get("полные") or []), млн(лф["оборот25"]), млн(лф["оборот26"]),
                        ("%+.1f" % лф["рост_%"]).replace(".", ","), пред,
                        _таблица(pd.DataFrame(лф["по_месяцам"]).rename(columns={
                            "месяц": "Месяц", "оборот25": "Оборот 2025", "оборот26": "Оборот 2026",
                            "рост_%": "Рост_%", "профит25_%": "Профит 2025, %",
                            "профит26_%": "Профит 2026, %"}))))
    for заг, ключ, подпись in (
            ("Матрица ABC × XYZ", "abc_xyz", "Готовая политика для каждого сочетания"),
            ("Поставщики", "поставщики", "Основа для переговоров об условиях поставки"),
            ("Коды проблем из рабочей матрицы", "коды", "Уже размеченная диагностика"),
            ("Почему товара не было", "причины", "У каждой причины свой адресат"),
            ("Бенчмарк офисов", "бенчмарк", "Цель — уровень медианы, потолок — уровень лучшего")):
        т = _таблица(списки.get(ключ), порог)
        if т:
            куски.append('<h2>%s</h2><div class="card"><div class="hint">%s</div>%s</div>'
                         % (заг, подпись, т))

    HTML = ШАБЛОН
    for k, v in {
        "__ДАТА__": S["дата"], "__SKU__": цел(S["sku"]), "__KPI__": kpi,
        "__ПОСЧИТАНО__": S.get("посчитано", S["дата"]),
        "__РАЗРЫВ__": ("<br><span style=\"color:var(--orange)\">Выгрузка от %s, но последние данные в ней — за %s. Отчёт построен по фактическим данным.</span>"
                       % (S["даты"]["дата_файла"], S["дата"]))
                      if S.get("даты", {}).get("дата_файла") and S["даты"]["дата_файла"] != S["дата"] else "",
        "__ПОРОГ__": пц(порог, 2), "__ДНЕЙ__": str(S["дней"]),
        "__CH1__": _bars(мес, [ряды.get("запас", []), ряды.get("оборот", [])], ["#2E5FA3", "#5BA85A"]),
        "__CH2__": _bars(мес, [ряды.get("oos", [])], ["#C0504D"], 150),
        "__ДАННЫЕ__": json.dumps(D, ensure_ascii=False, separators=(",", ":")),
        "__МЕСЯЦЫ__": json.dumps([m[:3] for m in мес], ensure_ascii=False),
        "__OWN__": str(порог), "__GOOD__": str(хор),
        "__ЛИМИТ__": str(int(cfg["отчёты"]["строк_в_дашборде"])),
        "__ЧАСТЬ3__": "".join(куски),
    }.items():
        HTML = HTML.replace(k, v)
    open(путь, "w", encoding="utf-8").write(HTML)
    лог("   Дашборд: %.0f КБ, узлов дерева %d, срезов %d"
        % (os.path.getsize(путь) / 1024, sum(len(v) for k, v in D.items() if k in ДЕРЕВЬЯ or k == "sku"), len(D)))
    return путь


ШАБЛОН = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Категорийный дашборд РТГ</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d21;--mut:#6b7280;--line:#e3e6ea;--blue:#2E5FA3;
--green:#2F7D32;--red:#C0392B;--orange:#D97706;--hi:#1F3864;--hover:rgba(46,95,163,.07)}
@media(prefers-color-scheme:dark){:root{--bg:#15181c;--card:#1d2126;--ink:#e8eaed;--mut:#9aa3ad;
--line:#2c3238;--hi:#22304d;--hover:rgba(90,150,230,.12)}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:20px}
.wrap{max-width:1340px;margin:0 auto}
h1{font-size:23px;margin:0 0 3px}.sub{color:var(--mut);margin-bottom:18px;font-size:13px}
h2{font-size:16px;margin:26px 0 9px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--blue);border-radius:7px;padding:11px 13px}
.kpi.green{border-left-color:var(--green)}.kpi.red{border-left-color:var(--red)}.kpi.orange{border-left-color:var(--orange)}
.kl{font-size:10.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}
.kv{font-size:20px;font-weight:650;margin:3px 0 1px}.ks{font-size:11px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:13px 15px;margin-top:10px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th{background:var(--hi);color:#fff;text-align:left;padding:7px 9px;font-weight:600;font-size:11.5px;
cursor:pointer;white-space:nowrap;position:sticky;top:0;z-index:2}
th.num,td.num{text-align:right}td{padding:4px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
td.num{font-variant-numeric:tabular-nums}
tr:hover td{background:var(--hover)}
td.bad{color:var(--red);font-weight:650}td.good{color:var(--green);font-weight:650}
td.mut{color:var(--mut)}.neg{color:var(--red);font-weight:600}
.nm{white-space:nowrap;max-width:520px;overflow:hidden;text-overflow:ellipsis}
.tw{display:inline-block;width:16px;color:var(--mut);cursor:pointer;user-select:none;font-size:11px}
.tw.empty{cursor:default;opacity:.25}
.lbl{cursor:pointer}.lbl:hover{text-decoration:underline}
mark{background:#FFE58F;color:#1a1d21;padding:0 1px;border-radius:2px}
.tabs{display:flex;gap:5px;margin-top:11px;flex-wrap:wrap}
.tab{padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);
cursor:pointer;font-size:12.5px;color:var(--ink)}
.tab[aria-selected="true"]{background:var(--hi);color:#fff;border-color:var(--hi)}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:9px}
input.f,select.s{padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);
color:var(--ink);font-size:12.5px}
input.f{width:250px}
.btn{padding:6px 11px;border:1px solid var(--line);border-radius:6px;background:var(--card);
color:var(--ink);cursor:pointer;font-size:12.5px}
.btn:hover{background:var(--hover)}
.chk{display:flex;gap:5px;align-items:center;font-size:12.5px;cursor:pointer;user-select:none}
.crumb{font-size:12.5px;color:var(--mut);margin-bottom:8px}
.crumb a{color:var(--blue);cursor:pointer;text-decoration:none}.crumb a:hover{text-decoration:underline}
.chart{width:100%;height:auto}line.grid{stroke:var(--line);stroke-width:1}text.ax{fill:var(--mut);font-size:10px}
.spark{vertical-align:middle}
.lg{display:flex;gap:16px;font-size:12px;color:var(--mut);margin:6px 0 2px}
.lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
.note{background:rgba(217,119,6,.09);border-left:3px solid var(--orange);padding:10px 13px;
border-radius:5px;margin-top:10px;font-size:13px}
.hint{color:var(--mut);font-size:11.5px;margin-top:5px}
footer{color:var(--mut);font-size:11.5px;margin-top:24px;padding-top:12px;border-top:1px solid var(--line)}
</style></head><body><div class="wrap">
<h1>Категорийный дашборд · дивизион РТГ</h1>
<div class="sub">Данные по <b>__ДАТА__</b> · расчёт от __ПОСЧИТАНО__ · период __ДНЕЙ__ дней · __SKU__ SKU__РАЗРЫВ__</div>
<div class="grid">__KPI__</div>
<div class="note"><b>Как читать:</b> GMROI — валовая прибыль за год на рубль среднего запаса.
Порог __ПОРОГ__ — стоимость владения запасом. Ниже порога категория не окупает собственное хранение;
<span class="neg">красное — убыточно</span>, зелёное — заметно выше порога.</div>

<h2>Запас и оборот по месяцам, млн ₽</h2>
<div class="card"><div class="lg"><span><i style="background:#2E5FA3"></i>Запас</span>
<span><i style="background:#5BA85A"></i>Оборот</span></div>__CH1__</div>

<h2>Дефицит (OOS) по месяцам, %</h2><div class="card">__CH2__</div>
__ЧАСТЬ3__

<h2>Дерево: товарная иерархия</h2>
<div class="card">
  <div class="bar">
    <input class="f" id="q_hier" placeholder="Поиск по всем уровням…">
    <select class="s" id="lv_hier"><option value="1">развернуть: 1 уровень</option>
      <option value="2">2 уровня</option><option value="3">3 уровня</option>
      <option value="4">4 уровня</option><option value="9">всё</option></select>
    <label class="chk"><input type="checkbox" id="pb_hier"> только проблемные</label>
    <button class="btn" id="cl_hier">свернуть всё</button>
    <button class="btn" id="cs_hier">выгрузить вид в CSV</button>
  </div>
  <div class="crumb" id="cr_hier"></div>
  <div id="t_hier"></div>
  <div class="hint">Треугольник — раскрыть уровень. Клик по названию — перейти внутрь.
  Клик по заголовку столбца — сортировка внутри каждой ветки.</div>
</div>

<h2>Дерево: склады</h2>
<div class="card">
  <div class="bar">
    <input class="f" id="q_wh" placeholder="Поиск по складам…">
    <select class="s" id="lv_wh"><option value="1">развернуть: 1 уровень</option>
      <option value="2">2 уровня</option><option value="9">всё</option></select>
    <label class="chk"><input type="checkbox" id="pb_wh"> только проблемные</label>
    <button class="btn" id="cl_wh">свернуть всё</button>
    <button class="btn" id="cs_wh">выгрузить вид в CSV</button>
  </div>
  <div class="crumb" id="cr_wh"></div><div id="t_wh"></div>
</div>

<h2>Дерево: бренды</h2>
<div class="card">
  <div class="bar">
    <input class="f" id="q_brand" placeholder="Поиск по брендам…">
    <select class="s" id="lv_brand"><option value="1">развернуть: 1 уровень</option>
      <option value="2">2 уровня</option><option value="9">всё</option></select>
    <label class="chk"><input type="checkbox" id="pb_brand"> только проблемные</label>
    <button class="btn" id="cl_brand">свернуть всё</button>
    <button class="btn" id="cs_brand">выгрузить вид в CSV</button>
  </div>
  <div class="crumb" id="cr_brand"></div><div id="t_brand"></div>
  <div class="hint">Брендов много — дерево свёрнуто. Разверните нужный треугольником или включите «только проблемные».</div>
</div>

<h2>Прочие срезы</h2>
<div class="tabs" id="tabsF">
<button class="tab" aria-selected="true" data-k="seg_xyz">XYZ — стабильность спроса</button>
<button class="tab" data-k="seg_abc">ABC по обороту</button>
<button class="tab" data-k="seg_liq">Ликвидность</button>
<button class="tab" data-k="seg_st">Статус позиции</button>
<button class="tab" data-k="wtype">Типы складов</button>
<button class="tab" data-k="w4">Направление × склад</button></div>
<div class="card"><input class="f" id="q_flat" placeholder="Фильтр…"><div id="t_flat"></div></div>

<footer>GMROI = валовая прибыль за год / средний запас по себестоимости. Отчёт сформирован автоматически.
Полные списки и план работ — в файле Excel рядом с этим дашбордом.</footer>
</div>
<script>
var D=__ДАННЫЕ__, OWN=__OWN__, GOOD=__GOOD__, LIM=__ЛИМИТ__, MM=__МЕСЯЦЫ__;
var COLS=[{k:'n',t:'Наименование',f:'t'},{k:'m',t:'Динамика',f:'sp'},
{k:'sku',t:'SKU',f:'i'},{k:'dead',t:'Без продаж',f:'i'},
{k:'rev',t:'Оборот, млн ₽',f:'mn'},{k:'mar',t:'Маржа',f:'p'},{k:'st',t:'Запас, млн ₽',f:'mn'},
{k:'d',t:'Дней запаса',f:'d'},{k:'g',t:'GMROI',f:'g'},{k:'ep',t:'Прибыль − содержание, млн ₽/год',f:'mn'},
{k:'z',t:'Засолы',f:'p'},{k:'oos',t:'OOS',f:'p'}];
function nf(v,d){return v==null?'—':v.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});}
function esc(s){return String(s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function spark(a){
 if(!a||!a.length)return '<td class="num mut">—</td>';
 var mx=Math.max.apply(null,a)||1,w=58,h=16,n=a.length,bw=w/n;
 var s='<svg class="spark" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'">';
 for(var i=0;i<n;i++){var bh=Math.max(1,(a[i]/mx)*(h-2));
  s+='<rect x="'+(i*bw+.5).toFixed(1)+'" y="'+(h-bh).toFixed(1)+'" width="'+(bw-1.2).toFixed(1)+
     '" height="'+bh.toFixed(1)+'" fill="#5BA85A" opacity="'+(i===n-1?1:.55)+'"><title>'+
     (MM[i]||'')+': '+nf(a[i],0)+' тыс ₽</title></rect>';}
 return '<td>'+s+'</svg></td>';}
function cell(node,c,имя,q){
 if(c.k==='n'){
   var t=esc(имя);
   if(q){var re=new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');t=t.replace(re,'<mark>$1</mark>');}
   return t;}
 var v=node?node[c.k]:null;
 if(c.f==='sp')return spark(v);
 if(v==null)return '<td class="num mut">—</td>';
 if(c.f==='i')return '<td class="num">'+nf(v,0)+'</td>';
 if(c.f==='mn')return '<td class="num'+(v<0?' neg':'')+'">'+nf(v/1e6,2)+'</td>';
 if(c.f==='p')return '<td class="num">'+nf(v,1)+' %</td>';
 if(c.f==='d')return '<td class="num">'+nf(v,0)+'</td>';
 if(c.f==='g'){var cl=v<OWN?'bad':(v>=GOOD?'good':'');return '<td class="num '+cl+'">'+nf(v,2)+'</td>';}
 return '<td class="num">'+v+'</td>';}

/* ---------- построение дерева из плоских строк с путями ---------- */
function build(rows){
 var root={ch:new Map(),node:null,name:'',key:''};
 (rows||[]).forEach(function(r){
   var cur=root;
   for(var i=0;i<r.p.length;i++){
     var k=r.p[i];
     if(!cur.ch.has(k))cur.ch.set(k,{ch:new Map(),node:null,name:k,key:(cur.key?cur.key+'\u0001':'')+k,depth:i});
     cur=cur.ch.get(k);}
   if(!cur.node)cur.node=r;});
 return root;}
function merge(a,b){ /* подвешиваем SKU в дерево иерархии */
 (b||[]).forEach(function(r){
   var cur=a;
   for(var i=0;i<r.p.length;i++){
     var k=r.p[i];
     if(!cur.ch.has(k))cur.ch.set(k,{ch:new Map(),node:null,name:k,key:(cur.key?cur.key+'\u0001':'')+k,depth:i});
     cur=cur.ch.get(k);}
   if(!cur.node)cur.node=r;});
 return a;}

var ST={};
function совпало(n,q){
 if(!q)return true;
 if(n.name&&n.name.toLowerCase().indexOf(q)>-1)return true;
 var есть=false; n.ch.forEach(function(c){if(!есть&&совпало(c,q))есть=true;});
 return есть;}
function проблемный(n,only){
 if(!only)return true;
 if(n.node&&n.node.g!=null&&n.node.g<OWN)return true;
 var есть=false; n.ch.forEach(function(c){if(!есть&&проблемный(c,only))есть=true;});
 return есть;}

function rows(n,st,out,q,depth){
 var дети=Array.from(n.ch.values()).filter(function(c){
   return совпало(c,q)&&проблемный(c,st.only);});
 if(st.sortk){
   дети.sort(function(a,b){
     var x=a.node?a.node[st.sortk]:null,y=b.node?b.node[st.sortk]:null;
     if(x==null)return 1; if(y==null)return -1;
     return st.asc?x-y:y-x;});
 } else {дети.sort(function(a,b){return (b.node?b.node.rev||0:0)-(a.node?a.node.rev||0:0);});}
 дети.forEach(function(c){
   if(out.length>=LIM)return;
   var откр=st.open.has(c.key)||(q&&c.ch.size&&совпало(c,q)&&q.length>=2);
   out.push({n:c,depth:depth,open:откр});
   if(откр)rows(c,st,out,q,depth+1);});
 return out;}

function render(id){
 var st=ST[id],q=(st.q||'').toLowerCase();
 var корень=st.root;
 st.path.forEach(function(k){if(корень.ch.has(k))корень=корень.ch.get(k);});
 var список=rows(корень,st,[],q,0);
 var h='<table><thead><tr>'+COLS.map(function(c,i){
   return '<th class="'+(c.f==='t'?'':'num')+'" data-i="'+i+'">'+c.t+'</th>';}).join('')+'</tr></thead><tbody>';
 список.forEach(function(x){
   var c=x.n,есть=c.ch.size>0;
   var tw='<span class="tw'+(есть?'':' empty')+'" data-k="'+esc(c.key)+'">'+(есть?(x.open?'▾':'▸'):'·')+'</span>';
   var имя='<td class="nm" style="padding-left:'+(6+x.depth*15)+'px">'+tw+
     '<span class="lbl" data-go="'+esc(c.key)+'">'+cell(c.node,COLS[0],c.name,q)+'</span></td>';
   h+='<tr>'+имя+COLS.slice(1).map(function(col){return cell(c.node,col,c.name,q);}).join('')+'</tr>';});
 h+='</tbody></table>';
 if(список.length>=LIM)h+='<div class="hint">Показано '+LIM+' строк. Уточните поиск или сверните ветки.</div>';
 var el=document.getElementById('t_'+id); el.innerHTML=h;
 el.querySelectorAll('.tw').forEach(function(t){t.onclick=function(){
   var k=t.dataset.k; if(st.open.has(k))st.open.delete(k); else st.open.add(k);
   save(id); render(id);};});
 el.querySelectorAll('.lbl').forEach(function(t){t.onclick=function(){
   var k=t.dataset.go; if(!k)return;
   st.path=k.split('\u0001'); st.open.add(k); save(id); render(id);};});
 el.querySelectorAll('th').forEach(function(th){th.onclick=function(){
   var i=+th.dataset.i,k=COLS[i].k; if(k==='n'||k==='m')return;
   st.asc=(st.sortk===k)?!st.asc:false; st.sortk=k; save(id); render(id);};});
 var cr=document.getElementById('cr_'+id);
 if(cr){
   if(!st.path.length){cr.innerHTML='';}
   else{
     var ч=['<a data-i="-1">всё</a>'];
     st.path.forEach(function(p,i){ч.push('<a data-i="'+i+'">'+esc(p)+'</a>');});
     cr.innerHTML='Вы здесь: '+ч.join(' › ');
     cr.querySelectorAll('a').forEach(function(a){a.onclick=function(){
       st.path=st.path.slice(0,+a.dataset.i+1); save(id); render(id);};});}}
}
function раскрыть(id,до){
 var st=ST[id]; st.open.clear();
 (function walk(n,d){ if(d>=до)return;
   n.ch.forEach(function(c){ if(c.ch.size){st.open.add(c.key); walk(c,d+1);} });})(st.root,0);
 save(id); render(id);}
function csv(id){
 var st=ST[id],q=(st.q||'').toLowerCase(),корень=st.root;
 st.path.forEach(function(k){if(корень.ch.has(k))корень=корень.ch.get(k);});
 var список=rows(корень,st,[],q,0);
 var шапка=['Уровень','Наименование'].concat(COLS.slice(2).map(function(c){return c.t;}));
 var строки=[шапка.join(';')];
 список.forEach(function(x){
   var n=x.n.node||{};
   строки.push([x.depth+1,'"'+String(x.n.name).replace(/"/g,'""')+'"'].concat(
     COLS.slice(2).map(function(c){var v=n[c.k];return v==null?'':String(v).replace('.',',');})).join(';'));});
 var blob=new Blob(['\ufeff'+строки.join('\n')],{type:'text/csv;charset=utf-8'});
 var a=document.createElement('a'); a.href=URL.createObjectURL(blob);
 a.download='срез_'+id+'.csv'; a.click(); URL.revokeObjectURL(a.href);}
function save(id){try{var st=ST[id];
 localStorage.setItem('rtg_'+id,JSON.stringify({o:Array.from(st.open),p:st.path,
   s:st.sortk,a:st.asc,only:st.only}));}catch(e){}}
function load(id){try{var j=JSON.parse(localStorage.getItem('rtg_'+id)||'null');
 if(!j)return null;return j;}catch(e){return null;}}

function дерево(id,данные,доп){
 var root=build(данные); if(доп)merge(root,доп);
 var сост=load(id)||{};
 ST[id]={root:root,open:new Set(сост.o||[]),path:сост.p||[],sortk:сост.s||null,
         asc:!!сост.a,only:!!сост.only,q:''};
 if(!(сост.o||[]).length)раскрыть(id,root.ch.size>30?0:1);
 var q=document.getElementById('q_'+id);
 if(q)q.oninput=function(){ST[id].q=q.value;render(id);};
 var lv=document.getElementById('lv_'+id);
 if(lv)lv.onchange=function(){раскрыть(id,+lv.value);};
 var pb=document.getElementById('pb_'+id);
 if(pb){pb.checked=ST[id].only;pb.onchange=function(){ST[id].only=pb.checked;save(id);render(id);};}
 var cl=document.getElementById('cl_'+id);
 if(cl)cl.onclick=function(){ST[id].open.clear();ST[id].path=[];save(id);render(id);};
 var cs=document.getElementById('cs_'+id);
 if(cs)cs.onclick=function(){csv(id);};
 render(id);}

/* плоские срезы */
var FS={k:'seg_xyz',q:'',sortk:null,asc:false};
function flat(){
 var rows=(D[FS.k]||[]).slice();
 if(FS.q){var q=FS.q.toLowerCase();rows=rows.filter(function(r){return r.p[0].toLowerCase().indexOf(q)>-1;});}
 if(FS.sortk)rows.sort(function(a,b){var x=a[FS.sortk],y=b[FS.sortk];
   if(x==null)return 1;if(y==null)return -1;return FS.asc?x-y:y-x;});
 var h='<table><thead><tr>'+COLS.map(function(c,i){
   return '<th class="'+(c.f==='t'?'':'num')+'" data-i="'+i+'">'+c.t+'</th>';}).join('')+'</tr></thead><tbody>';
 rows.slice(0,LIM).forEach(function(r){
   h+='<tr><td class="nm">'+esc(r.p[0])+'</td>'+COLS.slice(1).map(function(c){
     return cell(r,c,r.p[0],'');}).join('')+'</tr>';});
 h+='</tbody></table>';
 var el=document.getElementById('t_flat'); el.innerHTML=h;
 el.querySelectorAll('th').forEach(function(th){th.onclick=function(){
   var i=+th.dataset.i,k=COLS[i].k; if(k==='n'||k==='m')return;
   FS.asc=(FS.sortk===k)?!FS.asc:false;FS.sortk=k;flat();};});}
document.getElementById('tabsF').addEventListener('click',function(e){
 var b=e.target.closest('.tab'); if(!b)return;
 this.querySelectorAll('.tab').forEach(function(x){x.setAttribute('aria-selected',x===b?'true':'false');});
 FS.k=b.dataset.k;FS.sortk=null;flat();});
document.getElementById('q_flat').oninput=function(){FS.q=this.value;flat();};

дерево('hier',D.hier,D.sku);
дерево('wh',D.wh);
дерево('brand',D.brand);
flat();
</script></body></html>"""
