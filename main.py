"""Расчёт лабораторной работы по заряду со звездообразным каналом.

Скрипт реализует последовательность из методического пособия:

1. перебор геометрических параметров;
2. расчёт характеристик заряда;
3. построение тепловых диаграмм и графиков периметра;
4. выбор рационального варианта;
5. построение поперечного сечения в характерных точках горения.

Для запуска не требуются сторонние библиотеки: таблицы сохраняются в CSV и
Markdown, а графики формируются в формате SVG. SVG является векторным
форматом и может быть вставлен в Microsoft Word без потери качества.
"""

from __future__ import annotations

import colorsys
import csv
import html
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


# ---------------------------------------------------------------------------
# Исходные данные и служебные структуры
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = ROOT_DIR / "Results"
TABLES_DIR = RESULTS_DIR / "Tables"
GRAPHS_DIR = RESULTS_DIR / "Graphs"

# В методическом пособии для группы 3 заданы шесть сочетаний параметров.
GROUP_NAME = "Группа 3"
INDIVIDUAL_NAME = "Переверзев А.В."
NUMBER_OF_RAYS = 8
E_BAR_VALUES = tuple(round(0.30 + 0.03 * index, 2) for index in range(11))
DRAWING_DIAMETER_MM = 100.0
PNG_DPI = 400
PNG_FONT_FAMILY = "Times New Roman"

# Критерий выбора из опорного отчёта: площадь должна быть близка к средней
# (отклонение порядка 5 %), а заполнение при этом следует увеличить.
NEUTRALITY_TOLERANCE = 0.055

# Варианты, для которых требуется отдельный индивидуальный расчёт.
BARYSHEV_VARIANT_NAMES = ("Барышев А.А.", "Барышев С.А.")


@dataclass(frozen=True)
class VariantSpec:
    """Набор неизменяемых параметров одного варианта студента."""

    name: str
    r_bar: float
    beta_multiplier: float


@dataclass
class Geometry:
    """Геометрические параметры одного расчётного варианта.

    Расчёт ведётся при D=1. Это допустимо, поскольку все основные показатели
    методики безразмерны. Для графика сечения параметры затем масштабируются
    до D=100 мм, как в опорном отчёте.
    """

    n: int
    d: float
    e_bar_0: float
    r_bar: float
    beta: float
    alpha: float
    e_0: float
    r: float
    radius_r: float
    gamma_1: float
    e_1: float
    e_max: float


@dataclass
class CalculationResult:
    """Расчётные показатели и геометрия одного значения ē0."""

    variant: VariantSpec
    geometry: Geometry
    epsilon_f: float
    kappa_max: float
    kappa_0: float
    xi_degr: float
    sigma_e0: float
    mean_perimeter_bar: float
    perimeter_0_bar: float
    perimeter_e0_bar: float
    f_channel_0: float
    f_channel_e0: float


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    """Ограничивает аргумент обратной тригонометрической функции."""

    return max(lower, min(upper, value))


def fmt(value: float, digits: int = 6) -> str:
    """Форматирует число для русскоязычных таблиц с десятичной запятой."""

    return f"{value:.{digits}f}".replace(".", ",")


def fmt_short(value: float, digits: int = 3) -> str:
    """Форматирует число для подписей на графиках."""

    return f"{value:.{digits}f}".replace(".", ",")


def safe_name(value: str) -> str:
    """Создаёт безопасную часть имени файла из названия варианта."""

    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    translit = {
        "А": "A",
        "В": "V",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "N",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "П": "P",
        "У": "U",
        "р": "r",
        "е": "e",
        "в": "v",
        "з": "z",
        "о": "o",
        "а": "a",
        "р": "r",
        "ы": "y",
        "ш": "sh",
        "е": "e",
        "в": "v",
        "н": "n",
        "ю": "yu",
        "к": "k",
        "и": "i",
        "й": "j",
        "л": "l",
        "ь": "",
        "д": "d",
        "г": "g",
        "я": "ya",
        "с": "s",
        "а": "a",
        ".": "_",
        " ": "_",
    }
    result = []
    for character in value:
        replacement = translit.get(character, character)
        result.extend(symbol for symbol in replacement if symbol in allowed)
    return "".join(result) or "variant"


def individual_stem(name: str) -> str:
    """Возвращает стабильный идентификатор индивидуального варианта."""

    identifiers = {
        "Барышев А.А.": "baryshev_AA",
        "Барышев С.А.": "baryshev_SA",
        "Переверзев А.В.": "pereverzev_AV",
    }
    return identifiers.get(name, safe_name(name))


# ---------------------------------------------------------------------------
# Математическая модель из методического пособия
# ---------------------------------------------------------------------------


def beta_star_for_n(n: int) -> float:
    """Находит β*, обеспечивающий постоянство площади на первой стадии.

    Используется уравнение из пособия:
        π/2 + π/n − β − cot(β) = 0.
    Для поиска применяется метод половинного деления на [α, π/2].
    """

    alpha = math.pi / n

    def equation(beta: float) -> float:
        return math.pi / 2.0 + alpha - beta - 1.0 / math.tan(beta)

    left = alpha
    right = math.pi / 2.0 - 1.0e-10
    f_left = equation(left)
    f_right = equation(right)
    if f_left * f_right > 0.0:
        raise ValueError("Не удалось локализовать β* на отрезке [α, π/2].")

    for _ in range(100):
        middle = 0.5 * (left + right)
        f_middle = equation(middle)
        if abs(f_middle) < 1.0e-13:
            return middle
        if f_left * f_middle <= 0.0:
            right = middle
            f_right = f_middle
        else:
            left = middle
            f_left = f_middle
    return 0.5 * (left + right)


def make_geometry(spec: VariantSpec, e_bar_0: float, n: int) -> Geometry:
    """Вычисляет геометрические параметры по заданным безразмерным данным."""

    d = 1.0
    alpha = math.pi / n
    beta_star = beta_star_for_n(n)
    beta = spec.beta_multiplier * beta_star
    e_0 = e_bar_0 * d / 2.0

    # Из пособия: R = D/2 − e0 − r, r̄ = r/R.
    radius_r = (d / 2.0 - e_0) / (1.0 + spec.r_bar)
    r = spec.r_bar * radius_r
    gamma_1 = math.pi / 2.0 + alpha - beta

    # Границы стадий горения из пособия.
    e_1 = radius_r * math.sin(alpha) / math.cos(beta) - r
    e_max = math.sqrt(
        radius_r * radius_r
        + (d / 2.0) * (d / 2.0)
        - radius_r * d * math.cos(alpha)
    ) - r

    if e_0 <= 0.0 or radius_r <= 0.0 or r <= 0.0:
        raise ValueError("Получены недопустимые геометрические размеры заряда.")
    if e_max <= 0.0:
        raise ValueError("Максимальная толщина свода должна быть положительной.")

    return Geometry(
        n=n,
        d=d,
        e_bar_0=e_bar_0,
        r_bar=spec.r_bar,
        beta=beta,
        alpha=alpha,
        e_0=e_0,
        r=r,
        radius_r=radius_r,
        gamma_1=gamma_1,
        e_1=e_1,
        e_max=e_max,
    )


def gamma_function(geometry: Geometry, e: float) -> float:
    """Вычисляет γ(e) для второй и третьей стадий."""

    q = geometry.r + e
    argument = geometry.radius_r * math.sin(geometry.alpha) / q
    return geometry.alpha + math.asin(clamp(argument))


def delta_function(geometry: Geometry, e: float) -> float:
    """Вычисляет δ(e) для третьей стадии."""

    q = geometry.r + e
    numerator = (
        geometry.radius_r * geometry.radius_r
        + q * q
        - (geometry.d / 2.0) * (geometry.d / 2.0)
    )
    denominator = 2.0 * geometry.radius_r * q
    return math.pi - math.acos(clamp(numerator / denominator))


def phi_function(geometry: Geometry, e: float) -> float:
    """Вычисляет φ(e), используемую в площади канала третьей стадии."""

    q = geometry.r + e
    numerator = (
        geometry.radius_r * geometry.radius_r
        + (geometry.d / 2.0) * (geometry.d / 2.0)
        - q * q
    )
    denominator = geometry.radius_r * geometry.d
    return math.acos(clamp(numerator / denominator))


def stage_for(geometry: Geometry, e: float) -> int:
    """Определяет стадию горения для заданной толщины сгоревшего свода."""

    if e <= geometry.e_1 and e <= geometry.e_0:
        return 1
    if e <= geometry.e_0:
        return 2
    if e <= geometry.e_max:
        return 3
    return 4


def perimeter(geometry: Geometry, e: float) -> float:
    """Возвращает периметр профиля Π(e) по кусочной формуле пособия."""

    if e < 0.0:
        raise ValueError("Толщина сгоревшего свода не может быть отрицательной.")
    stage = stage_for(geometry, e)
    if stage == 4:
        return 0.0

    n = geometry.n
    q = geometry.r + e
    if stage == 1:
        beta = geometry.beta
        b = (
            geometry.radius_r * math.sin(geometry.alpha) / math.sin(beta)
            - q / math.tan(beta)
        )
        return 2.0 * n * (geometry.gamma_1 * q + b)
    if stage == 2:
        return 2.0 * n * gamma_function(geometry, e) * q

    gamma = gamma_function(geometry, e)
    delta = delta_function(geometry, e)
    return 2.0 * n * (gamma - delta) * q


def channel_area(geometry: Geometry, e: float) -> float:
    """Возвращает площадь свободного прохода Fкан(e)."""

    if e < 0.0:
        raise ValueError("Толщина сгоревшего свода не может быть отрицательной.")
    stage = stage_for(geometry, e)
    if stage == 4:
        return math.pi * geometry.d * geometry.d / 4.0

    n = geometry.n
    q = geometry.r + e
    if stage == 1:
        beta = geometry.beta
        b = (
            geometry.radius_r * math.sin(geometry.alpha) / math.sin(beta)
            - q / math.tan(beta)
        )
        value = n * (
            geometry.gamma_1 * q * q
            + b * (q + geometry.radius_r * math.cos(geometry.gamma_1))
            + geometry.radius_r * q * math.sin(geometry.gamma_1)
        )
    elif stage == 2:
        gamma = gamma_function(geometry, e)
        value = n * (
            gamma * q * q + geometry.radius_r * q * math.sin(gamma)
        )
    else:
        gamma = gamma_function(geometry, e)
        delta = delta_function(geometry, e)
        phi = phi_function(geometry, e)
        value = n * (
            (gamma - delta) * q * q
            + geometry.radius_r * q * math.sin(gamma)
            + phi * geometry.d * geometry.d / 4.0
            - geometry.radius_r * math.sin(phi) * geometry.d / 2.0
        )

    # Небольшое отрицательное значение может появиться только из-за округления
    # на границе стадии; физически площадь свободного прохода неотрицательна.
    return max(0.0, value)


def trapezoid_integral(values: Sequence[float], step: float) -> float:
    """Вычисляет интеграл методом трапеций по равномерной сетке."""

    if len(values) < 2:
        return 0.0
    return step * (0.5 * values[0] + sum(values[1:-1]) + 0.5 * values[-1])


def integrate_perimeter(geometry: Geometry, start: float, finish: float) -> float:
    """Интегрирует Π(e), разбивая сетку по границам стадий."""

    if finish <= start:
        return 0.0
    borders = [start]
    for border in (geometry.e_1, geometry.e_0):
        if start < border < finish:
            borders.append(border)
    borders.append(finish)
    total = 0.0
    for left, right in zip(borders[:-1], borders[1:]):
        count = 1000
        step = (right - left) / count
        values = [perimeter(geometry, left + step * i) for i in range(count + 1)]
        total += trapezoid_integral(values, step)
    return total


def calculate_result(spec: VariantSpec, e_bar_0: float, n: int) -> CalculationResult:
    """Рассчитывает все показатели для одной комбинации параметров."""

    geometry = make_geometry(spec, e_bar_0, n)
    f_channel_0 = channel_area(geometry, 0.0)
    f_channel_e0 = channel_area(geometry, geometry.e_0)
    f_case = math.pi * geometry.d * geometry.d / 4.0
    epsilon_f = 1.0 - f_channel_0 / f_case

    if not 0.0 < epsilon_f < 1.0:
        raise ValueError("Коэффициент заполнения εf вышел за физический диапазон.")

    integral = integrate_perimeter(geometry, 0.0, geometry.e_0)
    mean_perimeter = integral / geometry.e_0
    perimeter_0 = perimeter(geometry, 0.0)
    perimeter_e0 = perimeter(geometry, geometry.e_0)
    denominator = epsilon_f * (1.0 - epsilon_f)

    # В соответствии с опорным отчётом максимум κ̄ ищется на основной стадии
    # работы заряда 0 ≤ e ≤ e0, а не на затяжной стадии догорания остатков.
    sample_count = 4000
    kappa_values = [
        perimeter(geometry, geometry.e_0 * index / sample_count)
        / geometry.d
        / denominator
        for index in range(sample_count + 1)
    ]
    kappa_max = max(kappa_values)
    kappa_0 = perimeter_0 / geometry.d / denominator

    mass_denominator = f_case - f_channel_0
    xi_degr = (f_case - f_channel_e0) / mass_denominator
    sigma_e0 = perimeter_e0 / mean_perimeter

    return CalculationResult(
        variant=spec,
        geometry=geometry,
        epsilon_f=epsilon_f,
        kappa_max=kappa_max,
        kappa_0=kappa_0,
        xi_degr=xi_degr,
        sigma_e0=sigma_e0,
        mean_perimeter_bar=mean_perimeter / geometry.d,
        perimeter_0_bar=perimeter_0 / geometry.d,
        perimeter_e0_bar=perimeter_e0 / geometry.d,
        f_channel_0=f_channel_0,
        f_channel_e0=f_channel_e0,
    )


def build_results(specs: Sequence[VariantSpec]) -> List[CalculationResult]:
    """Выполняет перебор всех вариантов группы и значений ē0."""

    results: List[CalculationResult] = []
    for spec in specs:
        for e_bar_0 in E_BAR_VALUES:
            results.append(calculate_result(spec, e_bar_0, NUMBER_OF_RAYS))
    return results


# ---------------------------------------------------------------------------
# Таблицы и выбор рационального варианта
# ---------------------------------------------------------------------------


def result_row(result: CalculationResult) -> Dict[str, str]:
    """Преобразует расчёт в строку таблицы."""

    geometry = result.geometry
    return {
        "Вариант": result.variant.name,
        "ē0": fmt(geometry.e_bar_0, 2),
        "εf": fmt(result.epsilon_f, 6),
        "κ̄max": fmt(result.kappa_max, 6),
        "κ̄0": fmt(result.kappa_0, 6),
        "ξдегр": fmt(result.xi_degr, 6),
        "σe0": fmt(result.sigma_e0, 6),
        "Π̄ср": fmt(result.mean_perimeter_bar, 6),
        "ē1": fmt(2.0 * geometry.e_1 / geometry.d, 6),
        "ēmax": fmt(2.0 * geometry.e_max / geometry.d, 6),
    }


TABLE_FIELDS = ["Вариант", "ē0", "εf", "κ̄max", "κ̄0", "ξдегр", "σe0", "Π̄ср", "ē1", "ēmax"]


def write_csv(path: Path, rows: Sequence[Dict[str, str]], fields: Sequence[str]) -> None:
    """Сохраняет таблицу с разделителем ';', удобным для русской локали."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(fields), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_table(path: Path, rows: Sequence[Dict[str, str]], fields: Sequence[str]) -> None:
    """Сохраняет дублирующую таблицу в читаемом Markdown-виде."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["| " + " | ".join(fields) + " |", "|" + "---|" * len(fields)]
    for row in rows:
        lines.append("| " + " | ".join(row[field] for field in fields) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pareto_front(results: Sequence[CalculationResult]) -> List[CalculationResult]:
    """Определяет фронт Парето: κ̄ меньше, εf больше."""

    ordered = sorted(results, key=lambda item: item.kappa_max)
    front: List[CalculationResult] = []
    best_epsilon = -math.inf
    for result in ordered:
        if result.epsilon_f > best_epsilon + 1.0e-12:
            front.append(result)
            best_epsilon = result.epsilon_f
    return front


def select_rational(results: Sequence[CalculationResult]) -> CalculationResult:
    """Выбирает рациональный индивидуальный вариант.

    В опорном отчёте сначала контролируется близость σe0 к единице, затем
    среди приемлемых вариантов выбирается большее заполнение. При совпадении
    заполнения предпочтение отдаётся меньшему κ̄max.
    """

    neutral = [
        result
        for result in results
        if abs(result.sigma_e0 - 1.0) <= NEUTRALITY_TOLERANCE
    ]
    candidates = neutral or list(results)
    return max(candidates, key=lambda item: (item.epsilon_f, -item.kappa_max))


def geometry_rows(result: CalculationResult) -> List[Dict[str, str]]:
    """Формирует таблицу размеров выбранного заряда в миллиметрах."""

    geometry = result.geometry
    scale = DRAWING_DIAMETER_MM / geometry.d
    beta_star = beta_star_for_n(geometry.n)
    rows = [
        {"Параметр": "D", "Значение": fmt(DRAWING_DIAMETER_MM, 3), "Единица": "мм"},
        {"Параметр": "n", "Значение": str(geometry.n), "Единица": "шт."},
        {"Параметр": "ē0", "Значение": fmt(geometry.e_bar_0, 3), "Единица": "–"},
        {"Параметр": "r̄", "Значение": fmt(geometry.r_bar, 3), "Единица": "–"},
        {"Параметр": "α", "Значение": fmt(math.degrees(geometry.alpha), 3), "Единица": "град."},
        {"Параметр": "β*", "Значение": fmt(math.degrees(beta_star), 3), "Единица": "град."},
        {"Параметр": "β", "Значение": fmt(math.degrees(geometry.beta), 3), "Единица": "град."},
        {"Параметр": "R", "Значение": fmt(geometry.radius_r * scale, 3), "Единица": "мм"},
        {"Параметр": "r", "Значение": fmt(geometry.r * scale, 3), "Единица": "мм"},
        {"Параметр": "e0", "Значение": fmt(geometry.e_0 * scale, 3), "Единица": "мм"},
        {"Параметр": "e1", "Значение": fmt(geometry.e_1 * scale, 3), "Единица": "мм"},
        {"Параметр": "emax", "Значение": fmt(geometry.e_max * scale, 3), "Единица": "мм"},
    ]
    return rows


def characteristic_rows(result: CalculationResult) -> List[Dict[str, str]]:
    """Формирует точки, для которых строятся сечения заряда."""

    geometry = result.geometry
    points = [
        ("Начальный момент", 0.0),
        ("Конец первой стадии e1", max(0.0, min(geometry.e_1, geometry.e_max))),
        ("Конец основной части e0", geometry.e_0),
        ("Конец горения emax", geometry.e_max),
    ]
    scale = DRAWING_DIAMETER_MM / geometry.d
    rows = []
    for label, e in points:
        rows.append(
            {
                "Точка": label,
                "ē": fmt(2.0 * e / geometry.d, 6),
                "e, мм": fmt(e * scale, 3),
                "Стадия": str(stage_for(geometry, e)),
                "Π̄": fmt(perimeter(geometry, e) / geometry.d, 6),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Минимальный SVG-движок для графиков без сторонних библиотек
# ---------------------------------------------------------------------------


def esc(value: object) -> str:
    """Экранирует текст для вставки в SVG."""

    return html.escape(str(value), quote=True)


def svg_start(width: int, height: int, title: str) -> List[str]:
    """Создаёт начало SVG-документа."""

    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Arial,sans-serif;fill:#222} .grid{stroke:#d9d9d9;stroke-width:1} .axis{stroke:#333;stroke-width:1.5} .small{font-size:13px} .label{font-size:16px} .title{font-size:21px;font-weight:bold}</style>',
        f'<title>{esc(title)}</title>',
    ]


def svg_finish(parts: List[str], path: Path) -> None:
    """Завершает и сохраняет SVG-документ."""

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_text(parts: List[str], x: float, y: float, text: str, class_name: str = "small", anchor: str = "start") -> None:
    """Добавляет текстовую подпись."""

    parts.append(f'<text x="{x:.2f}" y="{y:.2f}" class="{class_name}" text-anchor="{anchor}">{esc(text)}</text>')


def svg_line(parts: List[str], x1: float, y1: float, x2: float, y2: float, stroke: str = "#333", width: float = 1.0, dash: str = "") -> None:
    """Добавляет отрезок."""

    dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{width}"{dash_attribute}/>')


def svg_polyline(parts: List[str], points: Sequence[Tuple[float, float]], stroke: str, width: float = 1.5, fill: str = "none", dash: str = "") -> None:
    """Добавляет ломаную линию или контур."""

    coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<polyline points="{coordinates}" stroke="{stroke}" stroke-width="{width}" fill="{fill}"{dash_attribute}/>')


def svg_polygon(parts: List[str], points: Sequence[Tuple[float, float]], stroke: str, width: float = 1.0, fill: str = "none") -> None:
    """Добавляет многоугольник."""

    coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    parts.append(f'<polygon points="{coordinates}" stroke="{stroke}" stroke-width="{width}" fill="{fill}"/>')


def svg_circle(parts: List[str], x: float, y: float, radius: float, stroke: str, width: float = 1.0, fill: str = "none", dash: str = "") -> None:
    """Добавляет окружность."""

    dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" stroke="{stroke}" stroke-width="{width}" fill="{fill}"{dash_attribute}/>')


def svg_rect(parts: List[str], x: float, y: float, width: float, height: float, fill: str, stroke: str = "none", opacity: float = 1.0) -> None:
    """Добавляет прямоугольник."""

    parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" fill="{fill}" stroke="{stroke}" opacity="{opacity:.3f}"/>')


def color_for(value: float, lower: float, upper: float) -> str:
    """Преобразует число в цвет от синего к жёлтому."""

    if upper <= lower:
        fraction = 0.5
    else:
        fraction = clamp((value - lower) / (upper - lower), 0.0, 1.0)
    red, green, blue = colorsys.hsv_to_rgb(0.67 - 0.53 * fraction, 0.90, 0.88)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def nice_range(values: Iterable[float], padding: float = 0.08) -> Tuple[float, float]:
    """Возвращает диапазон с небольшим запасом для осей."""

    values_list = list(values)
    lower = min(values_list)
    upper = max(values_list)
    if abs(upper - lower) < 1.0e-12:
        lower -= 1.0
        upper += 1.0
    extra = (upper - lower) * padding
    return lower - extra, upper + extra


def draw_axes(parts: List[str], x: float, y: float, width: float, height: float, x_min: float, x_max: float, y_min: float, y_max: float, x_label: str, y_label: str, title: str, ticks: int = 5) -> Tuple:
    """Рисует область графика, сетку и возвращает функции масштабирования."""

    def px(value: float) -> float:
        return x + (value - x_min) / (x_max - x_min) * width

    def py(value: float) -> float:
        return y + height - (value - y_min) / (y_max - y_min) * height

    for index in range(ticks + 1):
        fraction = index / ticks
        x_value = x_min + fraction * (x_max - x_min)
        y_value = y_min + fraction * (y_max - y_min)
        x_pixel = px(x_value)
        y_pixel = py(y_value)
        svg_line(parts, x_pixel, y, x_pixel, y + height, "#d9d9d9", 1.0)
        svg_line(parts, x, y_pixel, x + width, y_pixel, "#d9d9d9", 1.0)
        svg_text(parts, x_pixel, y + height + 23, fmt_short(x_value), "small", "middle")
        svg_text(parts, x - 12, y_pixel + 5, fmt_short(y_value), "small", "end")

    svg_line(parts, x, y, x, y + height, "#333", 1.5)
    svg_line(parts, x, y + height, x + width, y + height, "#333", 1.5)
    svg_text(parts, x + width / 2, y + height + 52, x_label, "label", "middle")
    svg_text(parts, x - 65, y + height / 2, y_label, "label", "middle")
    svg_text(parts, x + width / 2, y - 28, title, "title", "middle")
    return px, py


def marker_svg(parts: List[str], x: float, y: float, marker: str, color: str, size: float = 7.0, stroke: str = "#222") -> None:
    """Рисует маркер точки на тепловой диаграмме."""

    if marker == "square":
        svg_rect(parts, x - size, y - size, 2 * size, 2 * size, color, stroke)
    elif marker == "triangle":
        svg_polygon(parts, [(x, y - size), (x + size, y + size), (x - size, y + size)], stroke, 1.0, color)
    elif marker == "diamond":
        svg_polygon(parts, [(x, y - size), (x + size, y), (x, y + size), (x - size, y)], stroke, 1.0, color)
    elif marker == "plus":
        svg_line(parts, x - size, y, x + size, y, color, 2.0)
        svg_line(parts, x, y - size, x, y + size, color, 2.0)
    elif marker == "x":
        svg_line(parts, x - size, y - size, x + size, y + size, color, 2.0)
        svg_line(parts, x - size, y + size, x + size, y - size, color, 2.0)
    elif marker == "star":
        points = []
        for index in range(10):
            angle = -math.pi / 2.0 + index * math.pi / 5.0
            radius = size if index % 2 == 0 else size * 0.45
            points.append((x + radius * math.cos(angle), y + radius * math.sin(angle)))
        svg_polygon(parts, points, stroke, 1.2, color)
    else:
        svg_circle(parts, x, y, size, stroke, 1.0, color)


# ---------------------------------------------------------------------------
# Графики
# ---------------------------------------------------------------------------


def draw_colorbar(parts: List[str], x: float, y: float, width: float, height: float, lower: float, upper: float, label: str) -> None:
    """Рисует цветовую шкалу σe0."""

    steps = 30
    for index in range(steps):
        fraction = index / (steps - 1)
        color = color_for(lower + fraction * (upper - lower), lower, upper)
        rect_y = y + height - (index + 1) * height / steps
        svg_rect(parts, x, rect_y, width, height / steps + 1, color)
    svg_line(parts, x, y, x, y + height, "#333", 1.0)
    svg_line(parts, x + width, y, x + width, y + height, "#333", 1.0)
    svg_text(parts, x + width + 8, y + 5, fmt_short(upper), "small")
    svg_text(parts, x + width + 8, y + height, fmt_short(lower), "small")
    svg_text(parts, x + width + 42, y + height / 2, label, "label", "middle")


def draw_thermal_diagram(results: Sequence[CalculationResult], path: Path, title: str, individual: bool = False) -> None:
    """Строит тепловую диаграмму εf–κ̄ с цветом по σe0."""

    width, height = (1100, 760) if not individual else (900, 650)
    parts = svg_start(width, height, title)
    x_values = [result.kappa_max for result in results]
    y_values = [result.epsilon_f for result in results]
    color_values = [result.sigma_e0 for result in results]
    x_min, x_max = nice_range(x_values)
    y_min, y_max = nice_range(y_values)
    px, py = draw_axes(
        parts,
        95,
        90,
        width - 285,
        height - 205,
        x_min,
        x_max,
        y_min,
        y_max,
        "Максимальный безразмерный параметр Победоносцева κ̄max",
        "Коэффициент заполнения εf",
        title,
    )

    lower = min(color_values)
    upper = max(color_values)
    if individual:
        marker_types = ["circle"]
    else:
        marker_types = ["circle", "square", "triangle", "diamond", "plus", "x"]
    variant_markers: Dict[str, str] = {}
    for index, result in enumerate(results):
        marker = variant_markers.setdefault(result.variant.name, marker_types[len(variant_markers) % len(marker_types)])
        marker_svg(parts, px(result.kappa_max), py(result.epsilon_f), marker, color_for(result.sigma_e0, lower, upper), 7.0)
        if individual:
            svg_text(parts, px(result.kappa_max) + 9, py(result.epsilon_f) - 7, f"ē0={fmt_short(result.geometry.e_bar_0, 2)}", "small")

    if not individual:
        front = pareto_front(results)
        svg_polyline(parts, [(px(item.kappa_max), py(item.epsilon_f)) for item in front], "#222", 1.5, "none", "7,5")
        svg_text(parts, width - 275, height - 42, "Фронт Парето: κ̄↓, εf↑", "small")
        legend_y = 120
        svg_text(parts, width - 260, legend_y - 20, "Варианты", "label")
        for index, (name, marker) in enumerate(variant_markers.items()):
            marker_svg(parts, width - 245, legend_y + index * 28, marker, "#6387a8", 6.0)
            svg_text(parts, width - 230, legend_y + 5 + index * 28, name, "small")
    else:
        svg_text(parts, width - 270, height - 42, "Цвет: σe0", "small")

    draw_colorbar(parts, width - 150, 120, 22, height - 260, lower, upper, "σe0")
    svg_finish(parts, path)


def curve_points(result: CalculationResult, count: int = 300) -> List[Tuple[float, float]]:
    """Формирует точки кривой Π̄(ē) для графика."""

    geometry = result.geometry
    points = []
    for index in range(count + 1):
        e = geometry.e_max * index / count
        points.append((2.0 * e / geometry.d, perimeter(geometry, e) / geometry.d))
    return points


def draw_perimeter_curves(results: Sequence[CalculationResult], path: Path, title: str, panels: bool = True) -> None:
    """Строит графики изменения безразмерного периметра при разных ē0."""

    if panels:
        columns, rows_count = 2, math.ceil(len({item.variant.name for item in results}) / 2)
        panel_width, panel_height = 520, 400
        width, height = columns * panel_width, rows_count * panel_height + 40
    else:
        columns, rows_count = 1, 1
        panel_width, panel_height = 980, 630
        width, height = panel_width, panel_height

    parts = svg_start(width, height, title)
    all_ebars = [item.geometry.e_bar_0 for item in results]
    lower_ebar, upper_ebar = min(all_ebars), max(all_ebars)
    colors = lambda value: color_for(value, lower_ebar, upper_ebar)
    grouped: Dict[str, List[CalculationResult]] = {}
    for result in results:
        grouped.setdefault(result.variant.name, []).append(result)

    for panel_index, (name, variant_results) in enumerate(grouped.items()):
        row = panel_index // columns
        column = panel_index % columns
        x_offset = column * panel_width
        y_offset = row * panel_height
        x_min = 0.0
        x_max = max(2.0 * item.geometry.e_max / item.geometry.d for item in variant_results) * 1.03
        y_max = max(perimeter(item.geometry, 0.0) / item.geometry.d for item in variant_results) * 1.10
        px, py = draw_axes(
            parts,
            x_offset + 70,
            y_offset + 70,
            panel_width - 125,
            panel_height - 145,
            x_min,
            x_max,
            0.0,
            y_max,
            "Сгоревший свод ē",
            "Безразмерный периметр Π̄",
            name,
            ticks=4,
        )
        for result in sorted(variant_results, key=lambda item: item.geometry.e_bar_0):
            points = [(px(x_value), py(y_value)) for x_value, y_value in curve_points(result)]
            svg_polyline(parts, points, colors(result.geometry.e_bar_0), 1.4)
            boundary_x = px(result.geometry.e_bar_0)
            svg_line(parts, boundary_x, y_offset + 70, boundary_x, y_offset + panel_height - 75, "#555", 0.8, "4,4")

    if panels:
        draw_colorbar(parts, width - 78, 100, 20, height - 210, lower_ebar, upper_ebar, "ē0")
    else:
        draw_colorbar(parts, width - 90, 110, 20, height - 250, lower_ebar, upper_ebar, "ē0")
    svg_finish(parts, path)


def draw_individual_metrics(results: Sequence[CalculationResult], path: Path) -> None:
    """Строит вспомогательные графики показателей индивидуального варианта."""

    width, height = 1000, 760
    parts = svg_start(width, height, "Изменение показателей индивидуального варианта")
    metrics = [
        ("εf", lambda item: item.epsilon_f),
        ("κ̄max", lambda item: item.kappa_max),
        ("ξдегр", lambda item: item.xi_degr),
        ("σe0", lambda item: item.sigma_e0),
    ]
    for index, (label, getter) in enumerate(metrics):
        row, column = index // 2, index % 2
        x_offset, y_offset = column * 500, row * 380
        values = [getter(item) for item in results]
        y_min, y_max = nice_range(values, 0.12)
        px, py = draw_axes(
            parts,
            x_offset + 70,
            y_offset + 65,
            370,
            250,
            min(E_BAR_VALUES),
            max(E_BAR_VALUES),
            y_min,
            y_max,
            "ē0",
            label,
            label,
            ticks=4,
        )
        points = [(px(item.geometry.e_bar_0), py(getter(item))) for item in results]
        svg_polyline(parts, points, "#2878b5", 2.0)
        for item in results:
            marker_svg(parts, px(item.geometry.e_bar_0), py(getter(item)), "circle", "#2878b5", 4.0, "#2878b5")
    svg_finish(parts, path)


# ---------------------------------------------------------------------------
# Графики PNG для индивидуальных вариантов
# ---------------------------------------------------------------------------


def get_matplotlib():
    """Загружает Matplotlib и настраивает оформление графиков.

    Matplotlib используется только для PNG-вывода, поскольку параметр dpi
    является свойством растрового файла. Шрифт Times New Roman подключается
    из системного каталога Windows, если он доступен.
    """

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.font_manager as font_manager
        import matplotlib.pyplot as pyplot
    except ImportError as error:
        raise RuntimeError(
            "Для PNG-графиков требуется пакет matplotlib. "
            "Установите его командой: python -m pip install matplotlib"
        ) from error

    # Подключение системного файла Times New Roman устраняет зависимость от
    # текущих настроек шрифтов Matplotlib на Windows.
    font_candidates = [
        Path("C:/Windows/Fonts/times.ttf"),
        Path("C:/Windows/Fonts/times new roman.ttf"),
    ]
    for font_path in font_candidates:
        if font_path.exists():
            try:
                font_manager.fontManager.addfont(str(font_path))
            except OSError:
                pass

    pyplot.rcParams.update(
        {
            "font.family": PNG_FONT_FAMILY,
            "font.serif": [PNG_FONT_FAMILY],
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 9,
            "axes.unicode_minus": False,
            "figure.dpi": PNG_DPI,
            "savefig.dpi": PNG_DPI,
        }
    )
    return pyplot


def save_png_figure(figure, path: Path) -> None:
    """Сохраняет Matplotlib-фигуру с требуемым разрешением 400 dpi."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=PNG_DPI, bbox_inches="tight", facecolor="white")
    figure.clear()


def draw_thermal_png(results: Sequence[CalculationResult], path: Path, title: str, individual: bool = False) -> None:
    """Строит тепловую диаграмму и сохраняет её в PNG."""

    pyplot = get_matplotlib()
    figure, axis = pyplot.subplots(figsize=(9.5, 6.5) if not individual else (8.5, 6.0))
    x_values = [item.kappa_max for item in results]
    y_values = [item.epsilon_f for item in results]
    color_values = [item.sigma_e0 for item in results]
    scatter = axis.scatter(
        x_values,
        y_values,
        c=color_values,
        cmap="plasma",
        edgecolors="black",
        linewidths=0.7,
        s=62,
        zorder=3,
    )
    if individual:
        for item in results:
            axis.annotate(
                f"ē0={item.geometry.e_bar_0:.2f}",
                (item.kappa_max, item.epsilon_f),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=9,
            )
    else:
        front = pareto_front(results)
        axis.plot(
            [item.kappa_max for item in front],
            [item.epsilon_f for item in front],
            "k--",
            linewidth=1.1,
            label="Фронт Парето: κ̄max↓, εf↑",
        )
        axis.legend(loc="lower right")

    colorbar = figure.colorbar(scatter, ax=axis)
    colorbar.set_label("σe0")
    axis.set_title(title)
    axis.set_xlabel("Максимальный безразмерный параметр Победоносцева κ̄max")
    axis.set_ylabel("Коэффициент заполнения εf")
    axis.grid(True, alpha=0.35)
    save_png_figure(figure, path)
    pyplot.close(figure)


def draw_perimeter_png(results: Sequence[CalculationResult], path: Path, title: str, panels: bool = False) -> None:
    """Строит график Π̄(ē) в PNG с линиями для всех значений ē0."""

    pyplot = get_matplotlib()
    grouped: Dict[str, List[CalculationResult]] = {}
    for result in results:
        grouped.setdefault(result.variant.name, []).append(result)

    if panels:
        names = list(grouped)
        figure, axes = pyplot.subplots(3, 2, figsize=(12.0, 12.0), sharex=False, sharey=False, constrained_layout=True)
        axes_list = list(axes.flat)
    else:
        figure, axis = pyplot.subplots(figsize=(9.5, 6.5), constrained_layout=True)
        axes_list = [axis]

    lower_e_bar = min(item.geometry.e_bar_0 for item in results)
    upper_e_bar = max(item.geometry.e_bar_0 for item in results)
    normalizer = pyplot.Normalize(lower_e_bar, upper_e_bar)
    colormap = pyplot.get_cmap("viridis")

    for axis, (name, variant_results) in zip(axes_list, grouped.items()):
        for item in sorted(variant_results, key=lambda value: value.geometry.e_bar_0):
            curve = curve_points(item)
            axis.plot(
                [point[0] for point in curve],
                [point[1] for point in curve],
                color=colormap(normalizer(item.geometry.e_bar_0)),
                linewidth=1.2,
            )
            axis.axvline(item.geometry.e_bar_0, color="gray", linewidth=0.5, linestyle="--", alpha=0.5)
        axis.set_title(name)
        axis.set_xlabel("Сгоревший свод ē")
        axis.set_ylabel("Безразмерный периметр Π̄")
        axis.grid(True, alpha=0.30)

    if panels and len(axes_list) > len(grouped):
        for axis in axes_list[len(grouped):]:
            axis.set_visible(False)
    scalar_map = pyplot.cm.ScalarMappable(norm=normalizer, cmap=colormap)
    scalar_map.set_array([])
    colorbar = figure.colorbar(scalar_map, ax=axes_list, shrink=0.72)
    colorbar.set_label("Вариант минимальной толщины свода ē0")
    figure.suptitle(title, fontsize=16)
    save_png_figure(figure, path)
    pyplot.close(figure)


def draw_individual_metrics_png(results: Sequence[CalculationResult], path: Path, title: str) -> None:
    """Строит четыре графика показателей индивидуального варианта в PNG."""

    pyplot = get_matplotlib()
    figure, axes = pyplot.subplots(2, 2, figsize=(10.0, 7.5))
    metrics = [
        ("εf", lambda item: item.epsilon_f),
        ("κ̄max", lambda item: item.kappa_max),
        ("ξдегр", lambda item: item.xi_degr),
        ("σe0", lambda item: item.sigma_e0),
    ]
    for axis, (label, getter) in zip(axes.flat, metrics):
        axis.plot(
            [item.geometry.e_bar_0 for item in results],
            [getter(item) for item in results],
            marker="o",
            linewidth=1.4,
        )
        axis.set_xlabel("ē0")
        axis.set_ylabel(label)
        axis.grid(True, alpha=0.30)
    figure.suptitle(title, fontsize=16)
    figure.tight_layout()
    save_png_figure(figure, path)
    pyplot.close(figure)


# ---------------------------------------------------------------------------
# Поперечные сечения в характерных точках
# ---------------------------------------------------------------------------


def local_point(geometry: Geometry, e: float, angle_from_axis: float, sign: float = 1.0) -> Tuple[float, float]:
    """Возвращает точку окружности скругления в локальных координатах.

    Локальная ось y направлена по оси луча звезды, а угол отсчитывается от
    этой оси. Знак отражает правую и левую половины сектора.
    """

    q = geometry.r + e
    gamma = gamma_function(geometry, e) if e > geometry.e_1 else geometry.gamma_1
    x = sign * q * math.sin(angle_from_axis)
    y = geometry.radius_r + q * math.cos(angle_from_axis)
    return x, y


def rotate_local(point: Tuple[float, float], axis_angle: float) -> Tuple[float, float]:
    """Поворачивает локальную точку вокруг центра заряда."""

    x_local, y_local = point
    # Для axis_angle=0 ось луча совпадает с положительным направлением Y.
    unit_x = (math.cos(axis_angle), -math.sin(axis_angle))
    unit_y = (math.sin(axis_angle), math.cos(axis_angle))
    return (
        x_local * unit_x[0] + y_local * unit_y[0],
        x_local * unit_x[1] + y_local * unit_y[1],
    )


def half_profile_points(geometry: Geometry, e: float, sign: float, count: int = 32) -> List[Tuple[float, float]]:
    """Строит половину профиля одного луча до конца основной части."""

    q = geometry.r + e
    stage = stage_for(geometry, e)
    gamma = geometry.gamma_1 if stage == 1 else gamma_function(geometry, e)
    if stage == 1:
        beta = geometry.beta
        b = (
            geometry.radius_r * math.sin(geometry.alpha) / math.sin(beta)
            - q / math.tan(beta)
        )
        b = max(0.0, b)
    else:
        b = 0.0

    points: List[Tuple[float, float]] = []
    # Точка на оси луча, затем дуга скругления до касательной.
    for index in range(count + 1):
        angle = gamma * index / count
        x = sign * q * math.sin(angle)
        y = geometry.radius_r + q * math.cos(angle)
        points.append((x, y))

    if stage == 1:
        # Направление касательной по методике: от точки дуги к вершине плоской
        # поверхности. При e=e1 её длина b(e) становится нулевой.
        tangent_x = math.cos(geometry.gamma_1)
        tangent_y = -math.sin(geometry.gamma_1)
        last_x, last_y = points[-1]
        points.append((last_x + sign * b * tangent_x, last_y + b * tangent_y))
    return points


def cross_section_points(geometry: Geometry, e: float) -> List[Tuple[float, float]]:
    """Строит замкнутый контур звездообразного канала.

    На стадиях 1–2 используются непосредственно геометрические дуги и
    плоские участки из пособия. На третьей стадии остаются дегрессивные
    остатки; для их наглядного изображения используются дуги с угловым
    диапазоном γ−δ, который задан формулой пособия.
    """

    if e >= geometry.e_max:
        return []

    result: List[Tuple[float, float]] = []
    if e <= geometry.e_0:
        # Последовательно соединяем половины соседних лучей. Общие точки на
        # границах секторов совпадают, поэтому контур замыкается естественно.
        for ray in range(geometry.n):
            axis_angle = ray * 2.0 * math.pi / geometry.n
            plus = half_profile_points(geometry, e, 1.0)
            minus = list(reversed(half_profile_points(geometry, e, -1.0)))
            lobe = minus + plus
            result.extend(rotate_local(point, axis_angle) for point in lobe)
    else:
        # Для третьей стадии рисуем две дуги дегрессивного остатка каждого
        # луча. Их длина уменьшается пропорционально γ(e)−δ(e).
        gamma = gamma_function(geometry, e)
        delta = delta_function(geometry, e)
        span = max(0.0, gamma - delta)
        for ray in range(geometry.n):
            axis_angle = ray * 2.0 * math.pi / geometry.n
            for sign in (-1.0, 1.0):
                half = []
                for index in range(25):
                    angle = delta + span * index / 24.0
                    half.append((sign * (geometry.r + e) * math.sin(angle), geometry.radius_r + (geometry.r + e) * math.cos(angle)))
                result.extend(rotate_local(point, axis_angle) for point in half)
    return result


def draw_cross_section(result: CalculationResult, e: float, path: Path, label: str) -> None:
    """Сохраняет отдельный SVG-чертёж сечения в заданной точке."""

    geometry = result.geometry
    width, height = 820, 820
    parts = svg_start(width, height, f"Поперечное сечение: {label}")
    scale = 580.0 / geometry.d
    center_x, center_y = width / 2.0, height / 2.0

    def to_svg(point: Tuple[float, float]) -> Tuple[float, float]:
        x_value, y_value = point
        return center_x + x_value * scale, center_y - y_value * scale

    outer_radius = geometry.d / 2.0
    svg_circle(parts, center_x, center_y, outer_radius * scale, "#333", 2.0, "#f0d1a1")
    points = cross_section_points(geometry, e)
    if points:
        svg_points = [to_svg(point) for point in points]
        # Белая область обозначает свободный канал, а красный контур — фронт
        # горения/границу оставшегося топлива.
        svg_polygon(parts, svg_points, "#b43c35", 2.0, "#ffffff")
    else:
        svg_circle(parts, center_x, center_y, outer_radius * scale, "#b43c35", 2.0, "none", "7,5")

    # Координатные оси и подписи основных размеров помогают использовать
    # рисунок как опорный при переносе сечения на миллиметровую бумагу.
    svg_line(parts, center_x - outer_radius * scale, center_y, center_x + outer_radius * scale, center_y, "#777", 0.8, "5,5")
    svg_line(parts, center_x, center_y - outer_radius * scale, center_x, center_y + outer_radius * scale, "#777", 0.8, "5,5")
    svg_text(parts, center_x, 42, f"{label}: e={fmt(2.0 * e / geometry.d, 3)}·D", "title", "middle")
    svg_text(parts, center_x, 72, f"Стадия {stage_for(geometry, e)}; Π̄={fmt(perimeter(geometry, e) / geometry.d, 4)}", "label", "middle")
    svg_text(parts, center_x, height - 32, f"D={fmt(DRAWING_DIAMETER_MM, 1)} мм; n={geometry.n}; β={fmt(math.degrees(geometry.beta), 2)}°", "label", "middle")
    svg_finish(parts, path)


def draw_cross_section_png(result: CalculationResult, e: float, path: Path, label: str) -> None:
    """Сохраняет поперечное сечение в PNG с разрешением 400 dpi."""

    pyplot = get_matplotlib()
    from matplotlib.patches import Circle, Polygon

    geometry = result.geometry
    figure, axis = pyplot.subplots(figsize=(7.0, 7.0))
    outer_radius = geometry.d / 2.0
    axis.add_patch(
        Circle(
            (0.0, 0.0),
            outer_radius,
            facecolor="#f0d1a1",
            edgecolor="#333333",
            linewidth=1.6,
        )
    )
    points = cross_section_points(geometry, e)
    if points:
        axis.add_patch(
            Polygon(
                points,
                closed=True,
                facecolor="white",
                edgecolor="#b43c35",
                linewidth=1.4,
            )
        )
    else:
        circle = Circle((0.0, 0.0), outer_radius, fill=False, edgecolor="#b43c35", linewidth=1.4, linestyle="--")
        axis.add_patch(circle)

    axis.axhline(0.0, color="gray", linewidth=0.7, linestyle="--")
    axis.axvline(0.0, color="gray", linewidth=0.7, linestyle="--")
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlim(-0.56, 0.56)
    axis.set_ylim(-0.56, 0.56)
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_title(f"{label}: ē={2.0 * e / geometry.d:.3f}; стадия {stage_for(geometry, e)}")
    axis.text(
        0.5,
        -0.08,
        f"D={DRAWING_DIAMETER_MM:.1f} мм; n={geometry.n}; β={math.degrees(geometry.beta):.2f}°",
        transform=axis.transAxes,
        ha="center",
        va="top",
    )
    save_png_figure(figure, path)
    pyplot.close(figure)


# ---------------------------------------------------------------------------
# Запуск полного алгоритма
# ---------------------------------------------------------------------------


def create_output_directories() -> None:
    """Создаёт каталоги для таблиц и графиков."""

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)


def write_project_readme(selected: CalculationResult) -> None:
    """Сохраняет описание сформированных результатов."""

    text = f"""# Результаты расчёта

Расчёт выполнен по формулам из файла `Sources/Методическое пособие Лабораторной работы.pdf`.

- группа: {GROUP_NAME};
- число лучей: {selected.geometry.n};
- индивидуальный вариант: {selected.variant.name};
- выбранное значение ē0: {fmt(selected.geometry.e_bar_0, 2)};
- выбранное значение εf: {fmt(selected.epsilon_f, 6)};
- выбранное значение κ̄max: {fmt(selected.kappa_max, 6)};
- доля дегрессивных остатков ξдегр: {fmt(selected.xi_degr, 6)};
- относительная площадь σe0: {fmt(selected.sigma_e0, 6)}.

## Каталоги

- `Tables` — CSV- и Markdown-таблицы;
- `Graphs` — векторные графики SVG.

Для построения сечений использованы четыре характерные точки: начальный
момент, конец первой стадии `e1`, конец основной части `e0` и конец горения
`emax`. Это соответствует трём стадиям, описанным в методическом пособии.
"""
    (RESULTS_DIR / "README.md").write_text(text, encoding="utf-8")


def write_individual_readme(results: Sequence[CalculationResult], selected: CalculationResult) -> None:
    """Сохраняет описание результатов индивидуального варианта."""

    name = selected.variant.name
    stem = individual_stem(name)
    text = f"""# Индивидуальный расчёт: {name}

Расчёт выполнен по задачам 1–5 из файла `Sources/Методическое пособие Лабораторной работы.pdf`.

- вариант: {name};
- число лучей: {selected.geometry.n};
- относительное скругление: {fmt(selected.geometry.r_bar, 3)};
- β/β*: {fmt(selected.variant.beta_multiplier, 3)};
- диапазон варьирования ē0: {fmt(min(item.geometry.e_bar_0 for item in results), 2)}–{fmt(max(item.geometry.e_bar_0 for item in results), 2)};
- выбранное значение ē0: {fmt(selected.geometry.e_bar_0, 2)};
- εf: {fmt(selected.epsilon_f, 6)};
- κ̄max: {fmt(selected.kappa_max, 6)};
- ξдегр: {fmt(selected.xi_degr, 6)};
- σe0: {fmt(selected.sigma_e0, 6)}.

Графики для этого варианта находятся в `Results/Graphs` и сохранены в PNG
с разрешением {PNG_DPI} dpi. Оформление графиков настроено на Times New Roman.
Имена файлов начинаются с `{stem}`.
"""
    (RESULTS_DIR / f"{stem}_README.md").write_text(text, encoding="utf-8")


def run() -> None:
    """Выполняет все задачи лабораторной работы последовательно."""

    create_output_directories()

    specs = [
        VariantSpec("Барышев А.А.", 0.10, 0.9),
        VariantSpec("Барышев С.А.", 0.10, 1.0),
        VariantSpec("Вильданов А.Р.", 0.10, 1.1),
        VariantSpec("Переверзев А.В.", 0.15, 0.9),
        VariantSpec("Петренюк М.А.", 0.15, 1.0),
        VariantSpec("Петунин А.П.", 0.15, 1.1),
    ]
    all_results = build_results(specs)
    individual_results = [item for item in all_results if item.variant.name == INDIVIDUAL_NAME]
    selected = select_rational(individual_results)

    # Таблицы задачи 1–2 и исходные данные выбранного варианта.
    all_rows = [result_row(item) for item in all_results]
    individual_rows = [result_row(item) for item in individual_results]
    write_csv(TABLES_DIR / "group_3_results.csv", all_rows, TABLE_FIELDS)
    write_markdown_table(TABLES_DIR / "group_3_results.md", all_rows, TABLE_FIELDS)
    write_csv(TABLES_DIR / "individual_results.csv", individual_rows, TABLE_FIELDS)
    write_markdown_table(TABLES_DIR / "individual_results.md", individual_rows, TABLE_FIELDS)

    geometry_table = geometry_rows(selected)
    write_csv(TABLES_DIR / "selected_geometry.csv", geometry_table, ["Параметр", "Значение", "Единица"])
    write_markdown_table(TABLES_DIR / "selected_geometry.md", geometry_table, ["Параметр", "Значение", "Единица"])

    characteristic_table = characteristic_rows(selected)
    characteristic_fields = ["Точка", "ē", "e, мм", "Стадия", "Π̄"]
    write_csv(TABLES_DIR / "characteristic_points.csv", characteristic_table, characteristic_fields)
    write_markdown_table(TABLES_DIR / "characteristic_points.md", characteristic_table, characteristic_fields)

    selected_table = [
        {
            "Критерий выбора": "модуль отклонения σe0 от 1 в допуске; затем εf↑ и κ̄max↓",
            "Вариант": selected.variant.name,
            "ē0": fmt(selected.geometry.e_bar_0, 2),
            "εf": fmt(selected.epsilon_f, 6),
            "κ̄max": fmt(selected.kappa_max, 6),
            "ξдегр": fmt(selected.xi_degr, 6),
            "σe0": fmt(selected.sigma_e0, 6),
        }
    ]
    selected_fields = ["Критерий выбора", "Вариант", "ē0", "εf", "κ̄max", "ξдегр", "σe0"]
    write_csv(TABLES_DIR / "selected_variant.csv", selected_table, selected_fields)
    write_markdown_table(TABLES_DIR / "selected_variant.md", selected_table, selected_fields)

    front_rows = [result_row(item) for item in pareto_front(all_results)]
    write_csv(TABLES_DIR / "pareto_front_group_3.csv", front_rows, TABLE_FIELDS)
    write_markdown_table(TABLES_DIR / "pareto_front_group_3.md", front_rows, TABLE_FIELDS)

    # Графики задач 3–4.
    draw_thermal_diagram(
        all_results,
        GRAPHS_DIR / "thermal_diagram_group_3.svg",
        "Тепловая диаграмма: группа 3",
        individual=False,
    )
    draw_thermal_diagram(
        individual_results,
        GRAPHS_DIR / "thermal_diagram_individual.svg",
        "Тепловая диаграмма индивидуального варианта",
        individual=True,
    )
    draw_perimeter_curves(
        all_results,
        GRAPHS_DIR / "perimeter_curves_group_3.svg",
        "Зависимости безразмерного периметра: группа 3",
        panels=True,
    )
    draw_perimeter_curves(
        individual_results,
        GRAPHS_DIR / "perimeter_curves_individual.svg",
        "Зависимости безразмерного периметра: индивидуальный вариант",
        panels=False,
    )
    draw_individual_metrics(individual_results, GRAPHS_DIR / "individual_metrics.svg")

    # Индивидуальные расчёты вариантов Барышева А.А. и Барышева С.А.
    # PNG-вывод выполняется отдельно от ранее созданных SVG-файлов задачи №2.
    draw_thermal_png(
        all_results,
        GRAPHS_DIR / "thermal_diagram_group_3.png",
        "Тепловая диаграмма: группа 3",
        individual=False,
    )
    draw_perimeter_png(
        all_results,
        GRAPHS_DIR / "perimeter_curves_group_3.png",
        "Зависимости безразмерного периметра: группа 3",
        panels=True,
    )

    for target_name in BARYSHEV_VARIANT_NAMES:
        target_results = [item for item in all_results if item.variant.name == target_name]
        target_selected = select_rational(target_results)
        target_stem = individual_stem(target_name)

        target_rows = [result_row(item) for item in target_results]
        write_csv(TABLES_DIR / f"{target_stem}_results.csv", target_rows, TABLE_FIELDS)
        write_markdown_table(TABLES_DIR / f"{target_stem}_results.md", target_rows, TABLE_FIELDS)

        target_geometry_rows = geometry_rows(target_selected)
        geometry_fields = ["Параметр", "Значение", "Единица"]
        write_csv(TABLES_DIR / f"{target_stem}_geometry.csv", target_geometry_rows, geometry_fields)
        write_markdown_table(TABLES_DIR / f"{target_stem}_geometry.md", target_geometry_rows, geometry_fields)

        target_characteristic_rows = characteristic_rows(target_selected)
        characteristic_fields = ["Точка", "ē", "e, мм", "Стадия", "Π̄"]
        write_csv(TABLES_DIR / f"{target_stem}_characteristic_points.csv", target_characteristic_rows, characteristic_fields)
        write_markdown_table(TABLES_DIR / f"{target_stem}_characteristic_points.md", target_characteristic_rows, characteristic_fields)

        target_selected_row = [
            {
                "Критерий выбора": "модуль отклонения σe0 от 1 в допуске; затем εf↑ и κ̄max↓",
                "Вариант": target_selected.variant.name,
                "ē0": fmt(target_selected.geometry.e_bar_0, 2),
                "εf": fmt(target_selected.epsilon_f, 6),
                "κ̄max": fmt(target_selected.kappa_max, 6),
                "ξдегр": fmt(target_selected.xi_degr, 6),
                "σe0": fmt(target_selected.sigma_e0, 6),
            }
        ]
        selected_fields = ["Критерий выбора", "Вариант", "ē0", "εf", "κ̄max", "ξдегр", "σe0"]
        write_csv(TABLES_DIR / f"{target_stem}_selected_variant.csv", target_selected_row, selected_fields)
        write_markdown_table(TABLES_DIR / f"{target_stem}_selected_variant.md", target_selected_row, selected_fields)

        # PNG-графики задач 3–4 для каждого индивидуального варианта.
        draw_thermal_png(
            target_results,
            GRAPHS_DIR / f"thermal_diagram_{target_stem}.png",
            f"Тепловая диаграмма: {target_name}",
            individual=True,
        )
        draw_perimeter_png(
            target_results,
            GRAPHS_DIR / f"perimeter_curves_{target_stem}.png",
            f"Зависимости безразмерного периметра: {target_name}",
            panels=False,
        )
        draw_individual_metrics_png(
            target_results,
            GRAPHS_DIR / f"individual_metrics_{target_stem}.png",
            f"Изменение показателей: {target_name}",
        )

        # Четыре PNG-сечения задачи 5: начальный момент, e1, e0 и emax.
        target_characteristic_points = [
            ("01_initial", 0.0, "Начальный момент"),
            ("02_end_stage_1", target_selected.geometry.e_1, "Конец первой стадии e1"),
            ("03_end_main", target_selected.geometry.e_0, "Конец основной части e0"),
            ("04_end_burning", target_selected.geometry.e_max, "Конец горения emax"),
        ]
        for file_stem, e, label in target_characteristic_points:
            draw_cross_section_png(
                target_selected,
                e,
                GRAPHS_DIR / f"cross_section_{target_stem}_{file_stem}.png",
                label,
            )

        write_individual_readme(target_results, target_selected)

    # Графики задачи 5: четыре характерные точки, заданные стадиями горения.
    characteristic_points = [
        ("01_initial", 0.0, "Начальный момент"),
        ("02_end_stage_1", selected.geometry.e_1, "Конец первой стадии e1"),
        ("03_end_main", selected.geometry.e_0, "Конец основной части e0"),
        ("04_end_burning", selected.geometry.e_max, "Конец горения emax"),
    ]
    for file_stem, e, label in characteristic_points:
        draw_cross_section(selected, e, GRAPHS_DIR / f"cross_section_{file_stem}.svg", label)

    write_project_readme(selected)

    print("Расчёт завершён.")
    print(f"Таблицы: {TABLES_DIR}")
    print(f"Графики: {GRAPHS_DIR}")
    print(
        "Выбранный вариант: "
        f"ē0={fmt(selected.geometry.e_bar_0, 2)}, "
        f"εf={fmt(selected.epsilon_f, 4)}, "
        f"κ̄max={fmt(selected.kappa_max, 4)}, "
        f"σe0={fmt(selected.sigma_e0, 4)}"
    )


if __name__ == "__main__":
    run()
