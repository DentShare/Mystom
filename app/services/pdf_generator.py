from datetime import datetime
from io import BytesIO
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.database.models import User, Patient, ImplantLog, Treatment, Service
from app.utils.formatters import format_money, treatment_effective_price


# Цвета для имплантов на карте зубов
IMPLANT_COLORS = [
    "#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#E91E63",
    "#00BCD4", "#795548", "#607D8B", "#8BC34A", "#3F51B5"
]


def _parse_implant_size(implant_size: str) -> tuple[str, str]:
    """Парсинг размера '4.0 x 10.0' -> (диаметр, длина)"""
    if not implant_size:
        return "-", "-"
    parts = implant_size.replace(",", ".").split("x")
    if len(parts) >= 2:
        try:
            d = parts[0].strip()
            l = parts[1].strip()
            return d, l
        except (ValueError, IndexError):
            pass
    return implant_size, "-"


def generate_implant_card_pdf(doctor: User, patient: Patient, implants: list[ImplantLog]) -> bytes:
    """Генерация PDF карты имплантации с картой зубов и цветовой индикацией"""
    template_dir = Path(__file__).parent.parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("implant_card.html")

    # Карта зубов FDI: 4 ряда
    tooth_rows_fdi = [
        [18, 17, 16, 15, 14, 13, 12, 11],
        [21, 22, 23, 24, 25, 26, 27, 28],
        [31, 32, 33, 34, 35, 36, 37, 38],
        [41, 42, 43, 44, 45, 46, 47, 48],
    ]

    # Словарь: номер зуба -> индекс импланта (для цвета)
    tooth_to_implant_idx = {}
    for i, imp in enumerate(implants):
        try:
            tn = int(imp.tooth_number)
            tooth_to_implant_idx[tn] = i % len(IMPLANT_COLORS)
        except (ValueError, TypeError):
            pass

    # Строим строки для карты зубов
    tooth_rows = []
    for row in tooth_rows_fdi:
        tooth_row = []
        for num in row:
            idx = tooth_to_implant_idx.get(num)
            if idx is not None:
                tooth_row.append({"num": num, "class": f"implant implant-{idx}"})
            else:
                tooth_row.append({"num": num, "class": ""})
        tooth_rows.append(tooth_row)

    # Импланты с распарсенными диаметром и длиной
    implants_with_parsed = []
    for i, imp in enumerate(implants):
        diameter, length = _parse_implant_size(imp.implant_size)
        color = IMPLANT_COLORS[i % len(IMPLANT_COLORS)]
        implants_with_parsed.append({
            "tooth_number": imp.tooth_number,
            "system_name": imp.system_name,
            "implant_size": imp.implant_size,
            "diameter": diameter,
            "length": length,
            "operation_date": imp.operation_date,
            "notes": imp.notes,
            "color": color,
        })

    html_content = template.render(
        doctor=doctor,
        patient=patient,
        implants=implants,
        implants_with_parsed=implants_with_parsed,
        tooth_rows=tooth_rows,
        generation_date=datetime.now()
    )

    html = HTML(string=html_content)
    pdf_bytes = html.write_pdf()
    return pdf_bytes


def generate_invoice_pdf(
    doctor: User,
    patient: Patient,
    treatments: list[Treatment],
    services: list[Service] | None = None
) -> bytes:
    """Генерация PDF счета (для Premium)"""
    # Загружаем шаблон
    template_dir = Path(__file__).parent.parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.filters["format_money"] = format_money
    template = env.get_template("invoice.html")
    
    # Вычисляем итоговую сумму с учётом скидок (процент и сумма)
    total = sum(t.price or 0 for t in treatments)
    final_total = sum(
        treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
        for t in treatments
    )
    total_discount = total - final_total
    
    effective_prices = {
        t.id: treatment_effective_price(t.price, t.discount_percent, t.discount_amount)
        for t in treatments
    }
    total_paid = sum(getattr(t, "paid_amount", None) or 0 for t in treatments)
    total_debt = max(0, final_total - total_paid)
    html_content = template.render(
        doctor=doctor,
        patient=patient,
        treatments=treatments,
        effective_prices=effective_prices,
        services=services or [],
        total=total,
        total_discount=total_discount,
        final_total=final_total,
        total_paid=total_paid,
        total_debt=total_debt,
        generation_date=datetime.now(),
    )
    
    # Генерируем PDF
    html = HTML(string=html_content)
    pdf_bytes = html.write_pdf()
    
    return pdf_bytes

