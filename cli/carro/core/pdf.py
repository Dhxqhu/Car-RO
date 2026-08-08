"""Customer-facing PDF export."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from carro.config import DATA_DIR, load_config, photos_dir
from carro.core.models import RepairOrder
from carro.storage.photos import ensure_local_photos

CONTENT_WIDTH = 6.5 * inch
BOX_BORDER = colors.HexColor("#444444")
BOX_FILL = colors.HexColor("#F7F7F7")


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _resolve_logo(cfg: dict) -> Path | None:
    """Prefer config logo_path; fall back to common local branding paths."""
    candidates: list[Path] = []
    raw = (cfg.get("logo_path") or "").strip()
    if raw:
        candidates.append(Path(raw).expanduser())
    candidates.extend(
        [
            Path.home() / ".config" / "carro" / "logo.png",
            Path.home() / "Documents" / "Car-RO" / "branding" / "logo.png",
        ]
    )
    for p in candidates:
        if p.is_file():
            return p
    return None


def _body_html(text: str) -> str:
    return _xml_escape(text or "—").replace("\n", "<br/>")


def _section_box(heading: str, text: str, *, head_style, body_style) -> Table:
    """Bordered block that grows with content."""
    cell = [
        Paragraph(f"{heading}:", head_style),
        Spacer(1, 0.08 * inch),
        Paragraph(_body_html(text), body_style),
    ]
    box = Table([[cell]], colWidths=[CONTENT_WIDTH])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.9, BOX_BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), BOX_FILL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return box


def _append_kept(
    story: list,
    *bits: Flowable,
    min_remain_inch: float = 1.0,
) -> None:
    """Page-break if needed, then keep heading+content together (no orphan titles)."""
    story.append(CondPageBreak(min_remain_inch * inch))
    story.append(KeepTogether(list(bits)))


def export_pdf(order: RepairOrder, dest: Path | None = None) -> Path:
    cfg = load_config()
    shop = cfg.get("shop_name") or "(shop name here)"
    out_dir = DATA_DIR / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = dest or (out_dir / f"{order.id}.pdf")

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ROTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "ROH2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
    )
    box_head = ParagraphStyle(
        "ROBoxHead",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=0,
        spaceAfter=0,
        textColor=colors.HexColor("#222222"),
    )
    box_body = ParagraphStyle(
        "ROBoxBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
    )
    body = styles["Normal"]
    label_style = ParagraphStyle(
        "ROLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=10,
    )
    value_style = ParagraphStyle(
        "ROValue",
        parent=body,
        fontSize=10,
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
    left = [
        Paragraph(shop, title),
        Paragraph(f"Repair Order <b>{order.id}</b>", body),
        Paragraph(f"Status: {order.status} · Updated: {order.updated}", body),
    ]
    right: object = ""
    logo = _resolve_logo(cfg)
    if logo:
        try:
            from reportlab.lib.utils import ImageReader

            reader = ImageReader(str(logo))
            iw, ih = reader.getSize()
            max_w, max_h = 1.9 * inch, 0.55 * inch
            if iw > 0 and ih > 0:
                scale = min(max_w / iw, max_h / ih)
                right = Image(str(logo), width=iw * scale, height=ih * scale)
            else:
                right = Image(str(logo), width=max_w, height=max_h)
        except Exception:
            right = Image(str(logo), width=1.9 * inch, height=0.46 * inch)
    header = Table([[left, right]], colWidths=[4.6 * inch, 2.0 * inch])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.2 * inch))

    cust_rows = [
        ("Customer:", order.customer_label()),
        ("Phone:", order.phone or "—"),
        ("Year:", order.year or "—"),
        ("Make:", order.make or "—"),
        ("Model:", order.model or "—"),
        ("VIN:", order.vin or "—"),
        ("Mileage:", order.mileage or "—"),
        ("Plate:", order.plate or "—"),
    ]
    cust = [
        [Paragraph(_xml_escape(lab), label_style), Paragraph(_xml_escape(val), value_style)]
        for lab, val in cust_rows
    ]
    info = Table(cust, colWidths=[1.25 * inch, 5.25 * inch])
    info.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    _append_kept(story, info, min_remain_inch=1.6)

    complaint_box = _section_box(
        "Customer complaint / request",
        order.complaint or "—",
        head_style=box_head,
        body_style=box_body,
    )
    _append_kept(story, Spacer(1, 0.12 * inch), complaint_box, min_remain_inch=1.2)

    notes_box = _section_box(
        "Technician notes",
        order.tech_notes or "—",
        head_style=box_head,
        body_style=box_body,
    )
    _append_kept(story, Spacer(1, 0.12 * inch), notes_box, min_remain_inch=1.2)

    if order.obd_snapshot.strip():
        obd_html = _xml_escape(order.obd_snapshot).replace("\n", "<br/>")
        obd_para = Paragraph(
            f"<font face='Courier' size='8'>{obd_html}</font>",
            body,
        )
        _append_kept(
            story,
            Paragraph("OBD snapshot:", h2),
            obd_para,
            min_remain_inch=1.4,
        )

    photo_paths = []
    ensure_local_photos(order)
    for meta in order.photos:
        rel = meta.get("relpath") or meta.get("filename")
        if not rel:
            continue
        p = photos_dir() / order.id / Path(rel).name
        if p.is_file():
            photo_paths.append({**meta, "_path": p})

    caption = ParagraphStyle(
        "PhotoCaption",
        parent=body,
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        spaceBefore=2,
    )

    if photo_paths:
        rows: list = []
        row: list = []
        for meta in photo_paths[:8]:
            path = meta["_path"]
            try:
                img = Image(str(path), width=2.2 * inch, height=1.6 * inch, kind="proportional")
            except Exception:
                continue
            tag = _xml_escape(str(meta.get("tag") or "other"))
            note = _xml_escape(str(meta.get("notes") or meta.get("note") or "").strip())
            bits = [f"<i>{tag}</i>"]
            if note:
                bits.append(note.replace("\n", "<br/>"))
            cell = [img, Paragraph("<br/>".join(bits), caption)]
            row.append(cell)
            if len(row) == 2:
                rows.append(Table([row], colWidths=[3.2 * inch, 3.2 * inch]))
                row = []
        if row:
            while len(row) < 2:
                row.append("")
            rows.append(Table([row], colWidths=[3.2 * inch, 3.2 * inch]))
        if rows:
            _append_kept(
                story,
                Paragraph("Photos:", h2),
                rows[0],
                min_remain_inch=2.4,
            )
            for extra in rows[1:]:
                story.append(extra)
    elif order.photos:
        _append_kept(
            story,
            Paragraph("Photos:", h2),
            Paragraph(
                f"{len(order.photos)} on file but image bytes were not available locally "
                "(try sync / phone refresh).",
                body,
            ),
            min_remain_inch=0.9,
        )

    story.append(Spacer(1, 0.3 * inch))
    story.append(
        Paragraph(
            f"<font size='8' color='#666666'>Generated by Car-RO · {order.id}</font>",
            body,
        )
    )
    doc.build(story)
    return dest
