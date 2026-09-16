# -*- coding: utf-8 -*-
"""Распознавание и чтение исходных выгрузок.

Файлы опознаются ПО СОСТАВУ ЛИСТОВ, а не по имени: имя меняется с датой,
состав листов — нет. Если структура файла изменилась, модуль говорит об этом
по-русски и останавливает расчёт, вместо того чтобы молча посчитать неверно.
"""
from __future__ import annotations
import os, re, datetime as dt
import pandas as pd

NL = chr(10)

# ---------------------------------------------------------------- сигнатуры
SIGNATURES = {
    # ВАЖНО: «Сквозная» и «Динамика» имеют одинаковый набор из семи основных
    # листов, поэтому различаются по уникальным для каждой: у сквозной есть
    # планы и закупки, у динамики — недельный срез и лист «Динамика стока».
    "сквозная": {
        "имя": "Сквозная аналитика",
        "обязательные_листы": ["Каталог", "Матрица РТГ 2026", "Продажи 2026",
                               "Продажи текущий", "Сток 2026", "Сток текущий", "Матрицы",
                               "План ИТАН 2026", "Закупки 2026"],
        "исключающие_листы": ["Динамика стока", "Сток 2026 (нед)"],
        "вес": 10,
    },
    "динамика": {
        "имя": "Динамика стоков",
        "обязательные_листы": ["Динамика стока", "Сток 2026 (нед)", "Каталог", "Сток текущий"],
        "исключающие_листы": ["План ИТАН 2026", "Закупки 2026"],
        "вес": 8,
    },
    "матрица": {
        "имя": "Рабочая матрица пополнения",
        "обязательные_листы": ["Рабочая таблица", "Поставщики", "Куб_продаж"],
        "вес": 6,
    },
    # Список позиций, выведенных в ликвидацию. Ведётся ОТДЕЛЬНО от рабочей
    # матрицы: из матрицы позиция к этому моменту уже удалена, а решение
    # о выводе есть только здесь. Файл может содержать чужие направления —
    # лишнее отсекается периметром, отдельный фильтр не нужен.
    "ликвидация": {
        "имя": "Список ликвидации",
        "обязательные_листы": ["нсиМТР.Категории"],
        "вес": 2,
    },
    "юнит_позиции": {
        "имя": "Юнит-экономика (по позициям)",
        "обязательные_листы": ["Что выгружено", "Данные"],
        "признак_строки": "позиция",
        "вес": 4,
    },
    "юнит_склады": {
        "имя": "Юнит-экономика (по складам)",
        "обязательные_листы": ["Что выгружено", "Данные"],
        "признак_строки": "позиция × склад",
        "вес": 4,
    },
}

# ожидаемые колонки ключевых листов: если колонка пропала — расчёт остановится
EXPECTED = {
    ("сквозная", "Каталог"): (2, ["НС-Код", "Группа планирования", "Товарное направление", "Группа 1",
                                  "Группа 2", "Группа 3", "Бренд", "Название номенклатуры",
                                  "Статус засола NEW", "Стратегия SKU"]),
    ("сквозная", "Сток текущий"): (0, ["Филиал", "Склад", "НС-Код", "Дата поступления",
                                       "Общее кол-во запасов", "Общая себ-ть запасов"]),
    ("сквозная", "Сток 2026"): (0, ["Склад", "НС-Код", "Месяц", "Общее кол-во запасов",
                                    "Общая себ-ть запасов", "Статус засола NEW"]),
    ("сквозная", "Продажи 2026"): (0, ["Офис", "Склад", "НС-Код", "Месяц", "Оборот",
                                       "Продажи кол", "Продажи себ", "Продажи профит"]),
    ("сквозная", "Продажи текущий"): (0, ["Офис", "Склад", "НС-Код", "Месяц", "Оборот",
                                          "Продажи кол", "Продажи себ", "Продажи профит"]),
    ("сквозная", "Матрица РТГ 2026"): (0, ["НС-Код", "Стратегия SKU", "Офис", "Месяц",
                                           "min, ед.изм.", "max, ед.изм."]),
    ("динамика", "Каталог"): (2, ["НС-Код", "Цена за ед.изм"]),
    ("матрица", "Рабочая таблица"): (9, ["НС-Код", "Стратегия матрицы SKU", "Бренд", "Поставщик"]),
    ("ликвидация", "нсиМТР.Категории"): (0, ["Код", "Наименование", "Категория"]),
}


class ОшибкаДанных(Exception):
    """Понятная человеку ошибка во входных данных."""


def _sheets(path: str) -> list[str]:
    if path.lower().endswith(".xlsb"):
        from pyxlsb import open_workbook
        with open_workbook(path) as wb:
            return list(wb.sheets)
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def листы_файла(path: str) -> list[str]:
    """Имена листов книги — нужен движку, чтобы читать лист по порядку."""
    return _sheets(path)


ЛИКВ_КОЛОНКИ = {"код", "наименование", "категория"}


def _похоже_на_список_ликвидации(path: str, sheets: list[str]) -> bool:
    """Запасное опознавание: файл ликвидации — простой список из трёх
    колонок, и имя листа при перевыгрузке может смениться. Тогда узнаём
    его по шапке, а не по имени листа."""
    if len(sheets) != 1 or path.lower().endswith(".xlsb"):
        return False
    try:
        h = pd.read_excel(path, sheet_name=sheets[0], header=0, nrows=1)
    except Exception:
        return False
    return ЛИКВ_КОЛОНКИ <= {str(c).strip().lower() for c in h.columns}


def _строка_юнита(path: str) -> str:
    try:
        df = pd.read_excel(path, sheet_name="Что выгружено", header=None)
        for _, r in df.iterrows():
            if str(r.iloc[0]).strip() == "Строка":
                return str(r.iloc[1]).strip()
    except Exception:
        pass
    return ""


def опознать(path: str) -> tuple[str | None, str]:
    """Возвращает (код_типа, пояснение)."""
    try:
        листы = _sheets(path)
        sheets = set(листы)
    except Exception as e:
        return None, "не удалось открыть файл: %s" % e
    кандидаты = []
    for код, s in SIGNATURES.items():
        нужные = set(s["обязательные_листы"])
        запрет = set(s.get("исключающие_листы", []))
        if запрет & sheets:
            continue
        if нужные <= sheets:
            if код.startswith("юнит"):
                стр = _строка_юнита(path)
                ожид = s.get("признак_строки", "")
                if ожид and not стр.startswith(ожид):
                    continue
            кандидаты.append((s["вес"], код))
    if not кандидаты:
        if _похоже_на_список_ликвидации(path, листы):
            return "ликвидация", SIGNATURES["ликвидация"]["имя"]
        близкие = []
        for код, s in SIGNATURES.items():
            нужные = set(s["обязательные_листы"])
            есть = нужные & sheets
            if есть:
                близкие.append("%s - не хватает листов: %s"
                               % (s["имя"], ", ".join(sorted(нужные - есть))))
        note = ("похоже на: " + "; ".join(близкие)) if близкие else "состав листов не совпал ни с одним известным типом"
        return None, note
    кандидаты.sort(reverse=True)
    код = кандидаты[0][1]
    return код, SIGNATURES[код]["имя"]


# ---------------------------------------------------------------- чтение
def читать_лист(path: str, sheet: str, header_row: int = 0, first_data: int | None = None) -> pd.DataFrame:
    if path.lower().endswith(".xlsb"):
        from pyxlsb import open_workbook
        rows = []
        with open_workbook(path) as wb:
            with wb.get_sheet(sheet) as sh:
                for row in sh.rows():
                    rows.append({c.c: c.v for c in row})
        if header_row >= len(rows):
            raise ОшибкаДанных("лист «%s»: в файле всего %d строк, а заголовок ожидается в строке %d"
                               % (sheet, len(rows), header_row + 1))
        hdr = rows[header_row]
        cols = {k: str(v).replace(NL, " ").strip()
                for k, v in hdr.items() if v is not None and str(v).strip() != ""}
        fd = first_data if first_data is not None else header_row + 1
        return pd.DataFrame([{n: d.get(i) for i, n in cols.items()} for d in rows[fd:]])
    df = pd.read_excel(path, sheet_name=sheet, header=header_row)
    if first_data is not None and first_data > header_row + 1:
        df = df.iloc[first_data - header_row - 1:]
    df.columns = [str(c).replace(NL, " ").strip() for c in df.columns]
    return df


def читать_лист_позиционно(path: str, sheet: str) -> pd.DataFrame:
    """Лист как есть: колонки по номерам, без заголовка.

    Нужен для листов, где шапки нет или она заполнена не по всей ширине:
    обычный читатель оставляет только те колонки, у которых в строке
    заголовка что-то написано, и молча теряет остальные."""
    if path.lower().endswith(".xlsb"):
        from pyxlsb import open_workbook
        rows = []
        with open_workbook(path) as wb:
            with wb.get_sheet(sheet) as sh:
                for row in sh.rows():
                    rows.append({c.c: c.v for c in row})
        if not rows:
            return pd.DataFrame()
        ширина = max(max(r) for r in rows if r) + 1
        return pd.DataFrame([[d.get(j) for j in range(ширина)] for d in rows])
    return pd.read_excel(path, sheet_name=sheet, header=None)


def проверить_колонки(тип: str, лист: str, df: pd.DataFrame) -> list[str]:
    """Возвращает список отсутствующих обязательных колонок."""
    spec = EXPECTED.get((тип, лист))
    if not spec:
        return []
    _, нужные = spec
    есть = set(df.columns)
    return [c for c in нужные if c not in есть]


def очистить(df: pd.DataFrame) -> pd.DataFrame:
    df = df.loc[:, ~pd.Index([str(c) for c in df.columns]).duplicated()]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v))
                              else str(v).strip())
    return df


def в_число(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def из_серийной_даты(s):
    return pd.to_datetime(s, unit="D", origin="1899-12-30", errors="coerce")


def дата_из_имени(path: str):
    """Достаёт дату из имени файла вида '... 11.09.26.xlsb'."""
    m = re.search(r"(\d{2})[.\-_](\d{2})[.\-_](\d{2,4})", os.path.basename(path))
    if not m:
        return None
    d, mth, y = m.groups()
    y = int(y)
    y = y + 2000 if y < 100 else y
    try:
        return dt.date(y, int(mth), int(d))
    except ValueError:
        return None


def сканировать(папка: str) -> tuple[dict, list[str]]:
    """Находит и опознаёт все выгрузки в папке. Возвращает ({тип: путь}, замечания)."""
    найдено, замечания = {}, []
    if not os.path.isdir(папка):
        return найдено, ["папка «%s» не найдена" % папка]
    файлы = [f for f in sorted(os.listdir(папка))
             if f.lower().endswith((".xlsb", ".xlsx", ".xlsm")) and not f.startswith("~$")]
    if not файлы:
        return найдено, ["в папке «%s» нет файлов Excel" % папка]
    for f in файлы:
        p = os.path.join(папка, f)
        код, пояснение = опознать(p)
        if код is None:
            замечания.append("НЕ ОПОЗНАН: «%s» - %s" % (f, пояснение))
            continue
        if код in найдено:
            стар, нов = дата_из_имени(найдено[код]), дата_из_имени(p)
            if нов and стар and нов <= стар:
                замечания.append("пропущен «%s»: уже есть более свежий файл того же типа" % f)
                continue
            замечания.append("заменён более свежим: «%s»" % os.path.basename(найдено[код]))
        найдено[код] = p
    return найдено, замечания
