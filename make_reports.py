"""Формирование двух отчётов по образцу опорного отчёта.

Скрипт использует страницы исходного PDF как фон. Это позволяет сохранить
титульный лист и исходное оформление, заменяя только те фрагменты, которые
относятся к индивидуальному варианту. Итог создаётся одновременно в PDF и
DOCX; DOCX можно открыть и дополнительно редактировать в Microsoft Word.
"""

from __future__ import annotations

import csv
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from docx import Document
from docx.enum.section import WD_SECTION
from docx.shared import Mm

import main


ROOT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = ROOT_DIR / "Sources"
RESULTS_DIR = ROOT_DIR / "Results"
TABLES_DIR = RESULTS_DIR / "Tables"
GRAPHS_DIR = RESULTS_DIR / "Graphs"
REPORTS_DIR = ROOT_DIR / "Reports"
WORK_DIR = REPORTS_DIR / "_pages"
REFERENCE_PDF = SOURCE_DIR / "Отчет опорный.pdf"

PAGE_RENDER_SCALE = 2.0
PAGE_WIDTH, PAGE_HEIGHT = 1191, 1684


@dataclass
class VariantData:
    """Все значения, используемые в одном индивидуальном отчёте."""

    name: str
    stem: str
    beta_description: str
    results: List[Dict[str, str]]
    geometry: Dict[str, str]
    selected: Dict[str, str]
    selected_result: main.CalculationResult
    b0_mm: float
    gamma_1_deg: float


def genitive_name(variant: VariantData) -> str:
    """Возвращает ФИО в форме, подходящей для оборота «варианта ...»."""

    return variant.name.replace("Барышев", "Барышева").rstrip(".") + "."


def font_file(bold: bool = False) -> str:
    """Возвращает путь к Times New Roman, используемому в заменяемом тексте."""

    path = Path("C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf")
    if not path.exists():
        raise FileNotFoundError("Не найден системный шрифт Times New Roman.")
    return str(path)


def pil_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Создаёт шрифт требуемого размера."""

    return ImageFont.truetype(font_file(bold), size=size)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """Читает таблицу результатов с русским разделителем ';'."""

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file, delimiter=";"))


def decimal(value: str) -> float:
    """Преобразует число из таблицы с десятичной запятой."""

    return float(value.replace(",", "."))


def load_variant(name: str, stem: str, beta_description: str) -> VariantData:
    """Загружает индивидуальные данные из каталога Results/Tables."""

    rows = read_csv_rows(TABLES_DIR / f"{stem}_results.csv")
    geometry_rows = read_csv_rows(TABLES_DIR / f"{stem}_geometry.csv")
    selected_rows = read_csv_rows(TABLES_DIR / f"{stem}_selected_variant.csv")
    geometry = {row["Параметр"]: row["Значение"] for row in geometry_rows}
    selected = selected_rows[0]

    spec = next(
        spec
        for spec in (
            main.VariantSpec("Барышев А.А.", 0.10, 0.9),
            main.VariantSpec("Барышев С.А.", 0.10, 1.0),
        )
        if spec.name == name
    )
    selected_e_bar = decimal(selected["ē0"])
    selected_result = main.calculate_result(spec, selected_e_bar, main.NUMBER_OF_RAYS)
    selected_geometry = selected_result.geometry
    b0 = (
        selected_geometry.radius_r * math.sin(selected_geometry.alpha) / math.sin(selected_geometry.beta)
        - selected_geometry.r / math.tan(selected_geometry.beta)
    )
    return VariantData(
        name=name,
        stem=stem,
        beta_description=beta_description,
        results=rows,
        geometry=geometry,
        selected=selected,
        selected_result=selected_result,
        b0_mm=b0 * 100.0,
        gamma_1_deg=math.degrees(selected_geometry.gamma_1),
    )


def render_reference_pages() -> List[Image.Image]:
    """Рендерит страницы опорного PDF в растровые изображения."""

    document = pdfium.PdfDocument(str(REFERENCE_PDF))
    pages = []
    for page_index in range(len(document)):
        page = document[page_index]
        bitmap = page.render(scale=PAGE_RENDER_SCALE)
        pages.append(bitmap.to_pil().convert("RGB"))
    return pages


def scaled_box(box: Tuple[int, int, int, int], image: Image.Image) -> Tuple[int, int, int, int]:
    """Масштабирует координаты, заданные для страницы шириной 1191 пиксель."""

    factor_x = image.width / PAGE_WIDTH
    factor_y = image.height / PAGE_HEIGHT
    return tuple(
        int(value * (factor_x if index % 2 == 0 else factor_y))
        for index, value in enumerate(box)
    )


def clear_area(image: Image.Image, box: Tuple[int, int, int, int]) -> ImageDraw.ImageDraw:
    """Закрывает старый фрагмент страницы белым прямоугольником."""

    draw = ImageDraw.Draw(image)
    draw.rectangle(scaled_box(box, image), fill="white")
    return draw


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: Tuple[int, int],
    width: int,
    font: ImageFont.FreeTypeFont,
    line_gap: int,
    align: str = "left",
) -> int:
    """Рисует абзац с переносом строк и возвращает координату после текста."""

    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    x, y = xy
    line_height = font.size + line_gap
    for line in lines:
        line_width = draw.textlength(line, font=font)
        if align == "center":
            line_x = x + (width - line_width) / 2.0
        elif align == "right":
            line_x = x + width - line_width
        else:
            line_x = x
        draw.text((line_x, y), line, font=font, fill="black")
        y += line_height
    return y


def paste_fit(page: Image.Image, image_path: Path, box: Tuple[int, int, int, int]) -> None:
    """Масштабирует и помещает график в заданную область страницы."""

    x, y, width, height = scaled_box(box, page)
    figure = Image.open(image_path).convert("RGB")
    figure.thumbnail((width, height), Image.Resampling.LANCZOS)
    paste_x = x + (width - figure.width) // 2
    paste_y = y + (height - figure.height) // 2
    page.paste(figure, (paste_x, paste_y))


def draw_title_page(page: Image.Image, variant: VariantData) -> None:
    """Заменяет только ФИО студента на титульном листе."""

    draw = ImageDraw.Draw(page)
    # Белое поле закрывает только старую фамилию, не затрагивая линию подписи.
    draw.rectangle((790, 1230, 1070, 1290), fill="white")
    font = pil_font(27, bold=True)
    text = variant.name
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    draw.text(((935 - text_width / 2), 1235), text, font=font, fill="black")


def draw_table_2(page: Image.Image, variant: VariantData) -> None:
    """Заменяет таблицу 2 индивидуальными значениями варианта."""

    draw = clear_area(page, (0, 492, 1191, 945))
    left, top, right, bottom = scaled_box((412, 503, 863, 930), page)
    columns = [0.0, 0.145, 0.355, 0.575, 0.79, 1.0]
    row_count = len(variant.results) + 1
    row_height = (bottom - top) / row_count
    header_font = pil_font(24)
    cell_font = pil_font(23)
    headers = ["ē0", "εf", "κ̄max", "ξдегр", "σe0"]

    # Сетка таблицы повторяет структуру таблицы 2 опорного отчёта.
    for fraction in columns:
        x = left + fraction * (right - left)
        draw.line((x, top, x, bottom), fill="black", width=2)
    for row_index in range(row_count + 1):
        y = top + row_index * row_height
        draw.line((left, y, right, y), fill="black", width=2)

    def cell_text(row_index: int, column_index: int, text: str, font: ImageFont.FreeTypeFont) -> None:
        x0 = left + columns[column_index] * (right - left)
        x1 = left + columns[column_index + 1] * (right - left)
        y0 = top + row_index * row_height
        y1 = top + (row_index + 1) * row_height
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((x0 + x1 - (bbox[2] - bbox[0])) / 2.0, (y0 + y1 - (bbox[3] - bbox[1])) / 2.0 - bbox[1]),
            text,
            font=font,
            fill="black",
        )

    for column_index, header in enumerate(headers):
        cell_text(0, column_index, header, header_font)
    for row_index, row in enumerate(variant.results, start=1):
        values = [
            row["ē0"],
            f"{decimal(row['εf']):.4f}".replace(".", ","),
            f"{decimal(row['κ̄max']):.3f}".replace(".", ","),
            f"{decimal(row['ξдегр']):.4f}".replace(".", ","),
            f"{decimal(row['σe0']):.4f}".replace(".", ","),
        ]
        for column_index, value in enumerate(values):
            # В отчёте сохраняется точность, использованная в таблицах Results.
            cell_text(row_index, column_index, value, cell_font)


def draw_figure_1_preceding_paragraph(page: Image.Image, variant: VariantData) -> None:
    """Обновляет абзац на странице 8 перед рисунком 1."""

    clear_area(page, (0, 975, 1191, 1410))
    draw = ImageDraw.Draw(page)
    font = pil_font(24)
    name = genitive_name(variant)
    paragraph = (
        f"На рисунке 1 приведена тепловая диаграмма индивидуального варианта {name} "
        "с числом лучей n = 8. Абсцисса характеризует риск эрозионного горения: "
        "меньшие значения κ̄max предпочтительнее. Ордината характеризует заполнение "
        "поперечного сечения: большее εf предпочтительнее. Цвет определяет σe0 и "
        "показывает отклонение площади горения от среднего значения на момент e0."
    )
    draw_wrapped(draw, paragraph, (125, 1000), 945, font, 10, "left")


def draw_inputs_page(page: Image.Image, variant: VariantData) -> None:
    """Обновляет абзац с индивидуальными исходными данными."""

    clear_area(page, (0, 185, 1191, 435))
    draw = ImageDraw.Draw(page)
    font = pil_font(25)
    text = (
        f"Количество лучей по варианту n = 8, поэтому α = 22,500°, β* = 37,307°. "
        f"Параметры вариантов группы 3 приведены в таблице 1. Для индивидуального "
        f"варианта {variant.name} заданы r̄ = 0,10 и β = {variant.beta_description}. "
        "Варьируемый параметр ē0 принят от 0,30 до 0,60 с шагом 0,03; получено 11 расчётных точек."
    )
    draw_wrapped(draw, text, (135, 200), 920, font, 12, "left")


def draw_thermal_page(page: Image.Image, variant: VariantData) -> None:
    """Заменяет рисунок 1 и три связанных с ним абзаца."""

    clear_area(page, (0, 65, 1191, 1540))
    draw = ImageDraw.Draw(page)
    thermal_path = GRAPHS_DIR / f"thermal_diagram_{variant.stem}.png"
    paste_fit(page, thermal_path, (180, 82, 850, 590))
    draw = ImageDraw.Draw(page)
    caption_font = pil_font(23, bold=True)
    body_font = pil_font(24)
    caption = f"Рис. 1 — Тепловая диаграмма индивидуального варианта {genitive_name(variant)}"
    draw_wrapped(draw, caption, (125, 685), 945, caption_font, 6, "center")

    first = (
        f"На рисунке 1 приведена тепловая диаграмма индивидуального варианта {genitive_name(variant)} "
        "Абсцисса характеризует риск эрозионного горения: меньшие значения κ̄max предпочтительнее. "
        "Ордината характеризует заполнение поперечного сечения: большее εf предпочтительнее. "
        "Цвет определяет σe0 и показывает отклонение площади горения от среднего значения на момент e0. "
        "Выбранный вариант отмечен на диаграмме."
    )
    second = (
        "Рост ē0 на рисунке 1 даёт совместное увеличение εf и κ̄max: канал в начальный момент "
        "становится меньше, топливное заполнение повышается, но отношение периметра к площади "
        "свободного прохода возрастает. Следовательно, увеличение εf является компромиссом: оно "
        "сопровождается ростом параметра Победоносцева. При выборе точки необходимо контролировать "
        "также σe0: близость к единице означает малое отклонение площади горения от средней."
    )
    third = (
        f"На рисунке 2 приведена зависимость безразмерного периметра от толщины сгоревшего свода "
        f"для индивидуального варианта {genitive_name(variant)} по 11 значениям ē0 от 0,30 до 0,60. "
        "Тонкие вертикальные линии отмечают соответствующие значения ē0 — границу между второй "
        "и третьей стадиями. После этой границы периметр снижается, что отражает догорание "
        "дегрессивных остатков."
    )
    y = draw_wrapped(draw, first, (120, 785), 950, body_font, 9, "left")
    y = draw_wrapped(draw, second, (120, y + 16), 950, body_font, 9, "left")
    draw_wrapped(draw, third, (120, y + 16), 950, body_font, 9, "left")


def draw_perimeter_page(page: Image.Image, variant: VariantData) -> None:
    """Заменяет рисунки 2 и 3 одним индивидуальным рисунком 2."""

    clear_area(page, (0, 65, 1191, 1540))
    perimeter_path = GRAPHS_DIR / f"perimeter_curves_{variant.stem}.png"
    paste_fit(page, perimeter_path, (150, 105, 900, 700))
    draw = ImageDraw.Draw(page)
    caption_font = pil_font(24, bold=True)
    caption = f"Рис. 2 — Зависимость безразмерного периметра от толщины сгоревшего свода для индивидуального варианта {genitive_name(variant)}"
    draw_wrapped(draw, caption, (105, 830), 980, caption_font, 7, "center")


def draw_metrics_page(page: Image.Image, variant: VariantData) -> None:
    """Заменяет рисунок 4 и поясняющий текст индивидуальными результатами."""

    clear_area(page, (0, 70, 1191, 1540))
    draw = ImageDraw.Draw(page)
    body_font = pil_font(24)
    caption_font = pil_font(23, bold=True)
    first_row = variant.results[0]
    last_row = variant.results[-1]
    paragraph = (
        f"Рисунок 3 детализирует ход показателей индивидуального варианта {genitive_name(variant)} "
        f"С увеличением ē0 коэффициент заполнения растёт от {first_row['εf']} до {last_row['εf']}, "
        f"одновременно растут κ̄max и отклонение σe0 от единицы. Доля дегрессивных остатков, "
        f"напротив, уменьшается от {first_row['ξдегр']} до {last_row['ξдегр']}. Поэтому крайние "
        "значения ē0 требуют компромисса: повышение заполнения сопровождается ростом параметра "
        "Победоносцева и более выраженной прогрессивностью процесса."
    )
    draw_wrapped(draw, paragraph, (125, 92), 950, body_font, 10, "left")
    paste_fit(page, GRAPHS_DIR / f"individual_metrics_{variant.stem}.png", (145, 335, 900, 700))
    draw = ImageDraw.Draw(page)
    caption = f"Рис. 3 — Изменение показателей индивидуального варианта {genitive_name(variant)}."
    draw_wrapped(draw, caption, (95, 1080), 1000, caption_font, 6, "center")


def draw_geometry_page(page: Image.Image, variant: VariantData) -> None:
    """Обновляет параметры для ручного построения выбранного заряда."""

    clear_area(page, (0, 160, 1191, 675))
    draw = ImageDraw.Draw(page)
    font = pil_font(25)
    geometry = variant.geometry
    paragraph = (
        "В отчёт не включается чертёж звезды на миллиметровой бумаге. Для его самостоятельного "
        "построения выбран разумный наружный диаметр D = 100 мм. Для выбранного варианта "
        f"ē0 = {geometry['ē0']} параметры рисунка 2 методических указаний имеют значения: "
        f"e0 = {geometry['e0']} мм, R = {geometry['R']} мм, r = {geometry['r']} мм, "
        f"α = {geometry['α']}°, β = {geometry['β']}°, γ = {variant.gamma_1_deg:.3f}°. "
        f"Дополнительно: длина плоской части луча в начальный момент b(0) = {variant.b0_mm:.3f} мм, "
        f"граница первой стадии e1 = {geometry['e1']} мм, конец горения дегрессивных остатков "
        f"emax = {geometry['emax']} мм. Эти данные следует зеркально отложить относительно оси "
        "полулуча и повторить для восьми лучей с шагом 45°."
    )
    draw_wrapped(draw, paragraph, (145, 153), 930, font, 12, "left")


def draw_conclusion_page(page: Image.Image, variant: VariantData) -> None:
    """Обновляет заключение индивидуальными результатами."""

    clear_area(page, (0, 160, 1191, 650))
    draw = ImageDraw.Draw(page)
    font = pil_font(25)
    rows = variant.results
    selected = variant.selected
    selected_e = decimal(selected["ē0"])
    previous = next(row for row in rows if abs(decimal(row["ē0"]) - (selected_e - 0.03)) < 1.0e-8)
    paragraph = (
        f"Для индивидуального варианта {variant.name} выбран ē0 = {selected['ē0']}. При нём "
        f"εf = {selected['εf']}, κ̄max = {selected['κ̄max']}, ξдегр = {selected['ξдегр']}, "
        f"σe0 = {selected['σe0']}. По сравнению с ē0 = {previous['ē0']} коэффициент заполнения "
        f"увеличивается с {previous['εf']} до {selected['εf']}, а доля дегрессивных остатков "
        f"уменьшается с {previous['ξдегр']} до {selected['ξдегр']}. Рост κ̄max остаётся умеренным, "
        "а отклонение σe0 от единицы составляет около 5 %, поэтому закон изменения поверхности "
        "горения близок к нейтральному. Варианты с большим ē0 обеспечивают более высокое "
        "заполнение, но дают заметно больший максимум параметра Победоносцева и более выраженную "
        "прогрессивность, поэтому для выбранного варианта они менее рациональны."
    )
    draw_wrapped(draw, paragraph, (125, 178), 945, font, 12, "left")


def edit_pages(pages: Sequence[Image.Image], variant: VariantData) -> List[Image.Image]:
    """Создаёт полный комплект отредактированных страниц одного отчёта."""

    edited = [page.copy() for page in pages]
    draw_title_page(edited[0], variant)
    draw_inputs_page(edited[6], variant)
    draw_table_2(edited[7], variant)
    draw_figure_1_preceding_paragraph(edited[7], variant)
    draw_thermal_page(edited[8], variant)
    draw_perimeter_page(edited[9], variant)
    draw_metrics_page(edited[10], variant)
    draw_geometry_page(edited[11], variant)
    draw_conclusion_page(edited[12], variant)
    return edited


def save_page_images(pages: Sequence[Image.Image], stem: str) -> List[Path]:
    """Сохраняет промежуточные страницы отчёта в рабочий каталог."""

    target = WORK_DIR / stem
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, page in enumerate(pages, start=1):
        path = target / f"page_{index:02d}.png"
        page.save(path, format="PNG", dpi=(200, 200))
        paths.append(path)
    return paths


def save_pdf(page_paths: Sequence[Path], path: Path) -> None:
    """Собирает страницы-изображения в PDF формата A4."""

    canvas = Canvas(str(path), pagesize=A4)
    width, height = A4
    for page_path in page_paths:
        canvas.drawImage(ImageReader(str(page_path)), 0, 0, width=width, height=height)
        canvas.showPage()
    canvas.save()


def configure_docx_section(section) -> None:
    """Настраивает страницу DOCX на формат A4 без дополнительных полей."""

    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(0)
    section.bottom_margin = Mm(0)
    section.left_margin = Mm(0)
    section.right_margin = Mm(0)
    section.header_distance = Mm(0)
    section.footer_distance = Mm(0)


def save_docx(page_paths: Sequence[Path], path: Path, title: str) -> None:
    """Создаёт редактируемую Word-версию отчёта из подготовленных страниц."""

    document = Document()
    configure_docx_section(document.sections[0])
    document.core_properties.title = title
    document.core_properties.subject = "Исследование влияния параметров заряда твёрдого топлива"
    document.core_properties.author = ""

    for index, page_path in enumerate(page_paths):
        if index > 0:
            section = document.add_section(WD_SECTION.NEW_PAGE)
            configure_docx_section(section)
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = 0
        paragraph.paragraph_format.space_after = 0
        paragraph.paragraph_format.line_spacing = 1
        run = paragraph.add_run()
        run.add_picture(str(page_path), width=Mm(210), height=Mm(297))
    document.save(path)


def create_report(variant: VariantData, reference_pages: Sequence[Image.Image]) -> None:
    """Формирует PDF и DOCX для одного студента."""

    pages = edit_pages(reference_pages, variant)
    page_paths = save_page_images(pages, variant.stem)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    save_pdf(page_paths, REPORTS_DIR / f"Отчёт_{variant.stem}.pdf")
    save_docx(page_paths, REPORTS_DIR / f"Отчёт_{variant.stem}.docx", f"Отчёт — {variant.name}")


def main_run() -> None:
    """Формирует оба индивидуальных отчёта."""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reference_pages = render_reference_pages()
    variants = [
        load_variant("Барышев А.А.", "baryshev_AA", "0,9β* = 33,576°"),
        load_variant("Барышев С.А.", "baryshev_SA", "β* = 37,307°"),
    ]
    for variant in variants:
        create_report(variant, reference_pages)
        print(f"Создан отчёт: {variant.name}")


if __name__ == "__main__":
    main_run()
