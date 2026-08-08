"""Customer-facing PDF export."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    HRFlowable,
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
INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#555555")
RULE = colors.HexColor("#222222")
BOX_BORDER = colors.HexColor("#333333")
BOX_FILL = colors.HexColor("#FAFAFA")
ACCENT = colors.HexColor("#0B3D2E")


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
        Paragraph(f"{heading}", head_style),
        Spacer(1, 0.06 * inch),
        HRFlowable(width="100%", thickness=0.6, color=ACCENT, spaceBefore=0, spaceAfter=6),
        Paragraph(_body_html(text), body_style),
    ]
    box = Table([[cell]], colWidths=[CONTENT_WIDTH])
    box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.85, BOX_BORDER),
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


def _kv_block(rows: list[tuple[str, str]], *, label_style, value_style, width: float) -> Table:
    data = [
        [
            Paragraph(_xml_escape(lab), label_style),
            Paragraph(_xml_escape(val), value_style),
        ]
        for lab, val in rows
    ]
    t = Table(data, colWidths=[1.15 * inch, width - 1.15 * inch])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


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
    shop_style = ParagraphStyle(
        "ROShop",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=INK,
        spaceAfter=2,
    )
    meta_style = ParagraphStyle(
        "ROMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=MUTED,
    )
    ro_id_style = ParagraphStyle(
        "ROId",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=ACCENT,
        alignment=TA_RIGHT,
    )
    col_head = ParagraphStyle(
        "ROColHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=ACCENT,
        spaceAfter=4,
    )
    h2 = ParagraphStyle(
        "ROH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=INK,
        spaceBefore=10,
        spaceAfter=4,
    )
    box_head = ParagraphStyle(
        "ROBoxHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=INK,
        spaceBefore=0,
        spaceAfter=0,
    )
    box_body = ParagraphStyle(
        "ROBoxBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
        textColor=INK,
    )
    body = ParagraphStyle(
        "ROBody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=INK,
    )
    label_style = ParagraphStyle(
        "ROLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=MUTED,
    )
    value_style = ParagraphStyle(
        "ROValue",
        parent=body,
        fontSize=10,
        textColor=INK,
    )
    footer_style = ParagraphStyle(
        "ROFooter",
        parent=body,
        fontSize=8,
        textColor=MUTED,
        alignment=TA_CENTER,
    )
    sign_label = ParagraphStyle(
        "ROSignLabel",
        parent=body,
        fontSize=8,
        textColor=MUTED,
    )

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )
    story: list = []

    # --- Header: shop + logo ---
    left = [Paragraph(_xml_escape(shop), shop_style)]
    right: object = ""
    logo = _resolve_logo(cfg)
    if logo:
        try:
            from reportlab.lib.utils import ImageReader

            reader = ImageReader(str(logo))
            iw, ih = reader.getSize()
            max_w, max_h = 2.0 * inch, 0.65 * inch
            if iw > 0 and ih > 0:
                scale = min(max_w / iw, max_h / ih)
                right = Image(str(logo), width=iw * scale, height=ih * scale)
            else:
                right = Image(str(logo), width=max_w, height=max_h)
        except Exception:
            right = Image(str(logo), width=1.9 * inch, height=0.5 * inch)
    header = Table([[left, right]], colWidths=[4.4 * inch, 2.1 * inch])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.08 * inch))
    story.append(
        HRFlowable(width="100%", thickness=1.25, color=RULE, spaceBefore=0, spaceAfter=8)
    )

    # --- RO meta strip ---
    status = (order.status or "open").replace("_", " ").title()
    updated = order.updated or order.created or "—"
    tech = (order.technician_name or "").strip() or "—"
    meta_left = Paragraph(
        f"Status: <b>{_xml_escape(status)}</b> &nbsp;·&nbsp; "
        f"Updated: {_xml_escape(updated)} &nbsp;·&nbsp; "
        f"Technician: <b>{_xml_escape(tech)}</b>",
        meta_style,
    )
    meta_right = Paragraph(f"Repair Order {_xml_escape(order.id)}", ro_id_style)
    meta = Table([[meta_left, meta_right]], colWidths=[4.6 * inch, 1.9 * inch])
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 0.16 * inch))

    # --- Customer / Vehicle two-column grid ---
    half = 3.15 * inch
    cust_block = [
        Paragraph("CUSTOMER", col_head),
        _kv_block(
            [
                ("Name", order.customer_label()),
                ("Phone", order.phone or "—"),
            ],
            label_style=label_style,
            value_style=value_style,
            width=half,
        ),
    ]
    veh_block = [
        Paragraph("VEHICLE", col_head),
        _kv_block(
            [
                ("Vehicle", order.vehicle_label() or "—"),
                ("VIN", order.vin or "—"),
                ("Plate", order.plate or "—"),
                ("Mileage", order.mileage or "—"),
            ],
            label_style=label_style,
            value_style=value_style,
            width=half,
        ),
    ]
    grid = Table(
        [[cust_block, veh_block]],
        colWidths=[half + 0.1 * inch, half + 0.1 * inch],
    )
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (0, 0), 0.6, BOX_BORDER),
                ("BOX", (1, 0), (1, 0), 0.6, BOX_BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), BOX_FILL),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
            ]
        )
    )
    _append_kept(story, grid, min_remain_inch=1.8)

    complaint_box = _section_box(
        "CUSTOMER CONCERN / REQUEST",
        order.complaint or "—",
        head_style=box_head,
        body_style=box_body,
    )
    _append_kept(story, Spacer(1, 0.14 * inch), complaint_box, min_remain_inch=1.2)

    notes_box = _section_box(
        "DIAGNOSIS & TECHNICIAN NOTES",
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
            Paragraph("OBD / DIAGNOSTIC SNAPSHOT", h2),
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
        spaceBefore=3,
        textColor=MUTED,
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
            tag = _xml_escape(str(meta.get("tag") or "other")).upper()
            note = _xml_escape(str(meta.get("notes") or meta.get("note") or "").strip())
            bits = [f"<b>{tag}</b>"]
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
                Paragraph("PHOTOS", h2),
                rows[0],
                min_remain_inch=2.4,
            )
            for extra in rows[1:]:
                story.append(extra)
    elif order.photos:
        _append_kept(
            story,
            Paragraph("PHOTOS", h2),
            Paragraph(
                f"{len(order.photos)} on file but image bytes were not available locally "
                "(try sync / phone refresh).",
                body,
            ),
            min_remain_inch=0.9,
        )

    # --- Signature / acknowledgment ---
    story.append(Spacer(1, 0.28 * inch))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=0, spaceAfter=10)
    )
    sign_line = Table(
        [
            [
                Paragraph("Technician acknowledgment", sign_label),
                Paragraph("Date", sign_label),
            ],
            [
                Paragraph("________________________________", body),
                Paragraph("____________________", body),
            ],
        ],
        colWidths=[4.2 * inch, 2.3 * inch],
    )
    sign_line.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    _append_kept(story, sign_line, min_remain_inch=1.3)

    story.append(Spacer(1, 0.22 * inch))
    story.append(
        Paragraph(
            f"Customer copy · {_xml_escape(shop)} · {_xml_escape(order.id)} · Car-RO",
            footer_style,
        )
    )
    doc.build(story)
    return dest
