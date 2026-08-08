"""Tech-facing vehicle history packs (text diag + multi-RO PDF)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from carro.config import DATA_DIR, photos_dir
from carro.core.history import normalize_vin
from carro.core.models import RepairOrder
from carro.storage.photos import ensure_local_photos

HISTORY_DIR = DATA_DIR / "history"
HISTORY_PDF_PAGE_WARN = 10
OBD_TEXT_MAX = 8000
CONTENT_WIDTH = 6.5 * inch
BOX_BORDER = colors.HexColor("#444444")
BOX_FILL = colors.HexColor("#F7F7F7")
PHOTOS_PER_RO = 8


def history_dir() -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


def pack_slug(*, vin: str = "", name: str = "", orders: list[RepairOrder] | None = None) -> str:
    vin_n = normalize_vin(vin)
    if vin_n:
        return vin_n
    if orders:
        for o in orders:
            v = normalize_vin(o.vin)
            if v:
                return v
    name_s = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "history").strip())[:40]
    return name_s or "history"


def write_text_pack(
    orders: list[RepairOrder],
    *,
    vin: str = "",
    name: str = "",
    dest: Path | None = None,
) -> Path:
    """Plain-text diag pack: complaint, tech notes, OBD — no photos."""
    slug = pack_slug(vin=vin, name=name, orders=orders)
    dest = dest or (history_dir() / f"{slug}-diag.txt")
    lines: list[str] = [
        f"Vehicle history diag pack — {len(orders)} job(s)",
        f"VIN query: {normalize_vin(vin) or '(none)'}  name: {name or '(none)'}",
        "=" * 72,
        "",
    ]
    for order in orders:
        lines.extend(_text_ro_block(order))
        lines.append("")
        lines.append("-" * 72)
        lines.append("")
    dest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return dest


def _text_ro_block(order: RepairOrder) -> list[str]:
    header = (
        f"{order.id} · {order.updated or order.created or '—'} · {order.status} · "
        f"{order.customer_label()} · {order.vehicle_label()} · VIN {order.vin or '—'}"
    )
    obd = (order.obd_snapshot or "").strip()
    if len(obd) > OBD_TEXT_MAX:
        obd = obd[:OBD_TEXT_MAX] + "\n… truncated"
    return [
        header,
        "",
        "Complaint / request:",
        (order.complaint or "—").strip() or "—",
        "",
        "Technician notes:",
        (order.tech_notes or "—").strip() or "—",
        "",
        "OBD / DTC:",
        obd or "—",
    ]


def open_text_pack(path: Path) -> None:
    """Open pack in $PAGER / less, or print path."""
    candidates: list[list[str]] = []
    pager = (os.environ.get("PAGER") or "").strip()
    if pager:
        candidates.append(pager.split() + [str(path)])
    for exe in ("less", "more"):
        if shutil.which(exe):
            candidates.append([exe, str(path)])
    for cmd in candidates:
        try:
            env = os.environ.copy()
            if cmd[0].endswith("less") or cmd[0] == "less":
                env.setdefault("LESS", "FRX")
            subprocess.run(cmd, check=False, env=env)
            return
        except OSError:
            continue
    print(path)


def estimate_pack_pages(orders: list[RepairOrder], *, include_photos: bool) -> float:
    """Rough page estimate for oversized warning."""
    pages = 0.35  # title
    for order in orders:
        text_chars = (
            len(order.complaint or "")
            + len(order.tech_notes or "")
            + min(len(order.obd_snapshot or ""), OBD_TEXT_MAX)
        )
        pages += 0.35 + text_chars / 3500.0
        if include_photos:
            n = _count_local_photos(order)
            # ~2 photos per row, ~0.55 page per row
            rows = (min(n, PHOTOS_PER_RO) + 1) // 2
            pages += rows * 0.55
    return max(1.0, pages)


def _count_local_photos(order: RepairOrder) -> int:
    ensure_local_photos(order)
    n = 0
    for meta in order.photos:
        rel = meta.get("relpath") or meta.get("filename")
        if not rel:
            continue
        if (photos_dir() / order.id / Path(rel).name).is_file():
            n += 1
    return n


def write_pdf_pack(
    orders: list[RepairOrder],
    *,
    vin: str = "",
    name: str = "",
    include_photos: bool = True,
    dest: Path | None = None,
) -> Path:
    """Rebuild multi-RO tech PDF from live data (not merge of old customer PDFs)."""
    slug = pack_slug(vin=vin, name=name, orders=orders)
    suffix = "pack" if include_photos else "pack-lite"
    dest = dest or (history_dir() / f"{slug}-{suffix}.pdf")

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "HistTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "HistH2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=10,
        spaceAfter=4,
    )
    box_head = ParagraphStyle(
        "HistBoxHead",
        parent=styles["Heading2"],
        fontSize=10,
        spaceBefore=0,
        spaceAfter=0,
        textColor=colors.HexColor("#222222"),
    )
    box_body = ParagraphStyle(
        "HistBoxBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
    )
    body = styles["Normal"]
    caption = ParagraphStyle(
        "HistCap",
        parent=body,
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        spaceBefore=2,
    )

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )
    story: list = []
    vin_label = normalize_vin(vin) or "(mixed / name lookup)"
    story.append(Paragraph("Vehicle history pack (tech)", title))
    story.append(
        Paragraph(
            f"{len(orders)} job(s) · VIN { _xml_escape(vin_label) }"
            + (f" · name {_xml_escape(name)}" if name else "")
            + (" · photos included" if include_photos else " · text + OBD only"),
            body,
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    for order in orders:
        story.extend(
            _pdf_ro_sections(
                order,
                h2=h2,
                box_head=box_head,
                box_body=box_body,
                body=body,
                caption=caption,
                include_photos=include_photos,
            )
        )

    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(
            f"<font size='8' color='#666666'>Car-RO history pack · {len(orders)} RO(s)</font>",
            body,
        )
    )
    doc.build(story)
    return dest


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _body_html(text: str) -> str:
    return _xml_escape(text or "—").replace("\n", "<br/>")


def _section_box(heading: str, text: str, *, head_style, body_style) -> Table:
    cell = [
        Paragraph(f"{heading}:", head_style),
        Spacer(1, 0.06 * inch),
        Paragraph(_body_html(text), body_style),
    ]
    box = Table([[cell]], colWidths=[CONTENT_WIDTH])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, BOX_BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), BOX_FILL),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return box


def _pdf_ro_sections(
    order: RepairOrder,
    *,
    h2,
    box_head,
    box_body,
    body,
    caption,
    include_photos: bool,
) -> list:
    bits: list = []
    head = (
        f"<b>{_xml_escape(order.id)}</b> · {_xml_escape(order.status)} · "
        f"{_xml_escape(order.updated or order.created or '—')}<br/>"
        f"{_xml_escape(order.customer_label())} · {_xml_escape(order.vehicle_label())} · "
        f"VIN {_xml_escape(order.vin or '—')}"
    )
    bits.append(CondPageBreak(1.2 * inch))
    bits.append(KeepTogether([Paragraph(head, h2)]))
    bits.append(Spacer(1, 0.08 * inch))
    bits.append(
        KeepTogether(
            [
                _section_box(
                    "Customer complaint / request",
                    order.complaint or "—",
                    head_style=box_head,
                    body_style=box_body,
                )
            ]
        )
    )
    bits.append(Spacer(1, 0.08 * inch))
    bits.append(
        KeepTogether(
            [
                _section_box(
                    "Technician notes",
                    order.tech_notes or "—",
                    head_style=box_head,
                    body_style=box_body,
                )
            ]
        )
    )
    if order.obd_snapshot.strip():
        obd = order.obd_snapshot.strip()
        if len(obd) > OBD_TEXT_MAX:
            obd = obd[:OBD_TEXT_MAX] + "\n… truncated"
        obd_html = _xml_escape(obd).replace("\n", "<br/>")
        bits.append(CondPageBreak(1.0 * inch))
        bits.append(
            KeepTogether(
                [
                    Paragraph("OBD / DTC:", h2),
                    Paragraph(f"<font face='Courier' size='7'>{obd_html}</font>", body),
                ]
            )
        )

    if include_photos:
        bits.extend(_pdf_photos(order, body=body, caption=caption, h2=h2))
    return bits


def _pdf_photos(order: RepairOrder, *, body, caption, h2) -> list:
    ensure_local_photos(order)
    paths = []
    for meta in order.photos:
        rel = meta.get("relpath") or meta.get("filename")
        if not rel:
            continue
        p = photos_dir() / order.id / Path(rel).name
        if p.is_file():
            paths.append({**meta, "_path": p})
    if not paths:
        return []

    rows: list = []
    row: list = []
    for meta in paths[:PHOTOS_PER_RO]:
        try:
            img = Image(
                str(meta["_path"]),
                width=2.2 * inch,
                height=1.6 * inch,
                kind="proportional",
            )
        except Exception:
            continue
        tag = _xml_escape(str(meta.get("tag") or "other"))
        note = _xml_escape(str(meta.get("notes") or meta.get("note") or "").strip())
        cap = [f"<i>{tag}</i>"]
        if note:
            cap.append(note.replace("\n", "<br/>"))
        row.append([img, Paragraph("<br/>".join(cap), caption)])
        if len(row) == 2:
            rows.append(Table([row], colWidths=[3.2 * inch, 3.2 * inch]))
            row = []
    if row:
        while len(row) < 2:
            row.append("")
        rows.append(Table([row], colWidths=[3.2 * inch, 3.2 * inch]))
    if not rows:
        return []
    out: list = [CondPageBreak(2.2 * inch), KeepTogether([Paragraph("Photos:", h2), rows[0]])]
    out.extend(rows[1:])
    return out
