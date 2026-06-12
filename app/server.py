from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import uuid
import zipfile
from email.message import EmailMessage
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from powerpoint import build_powerpoint_file


APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
RUNS_DIR = ROOT / "outputs" / "runs"
SAFE_FILENAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PROJECT_TYPES = ("Paint by Numbers", "Making Movies", "Quest", "Walking in Fog")
TYPE_GUIDANCE = {
    "Paint by Numbers": {
        "plain_english": "The outcome and the method are understood. Delivery should be repeatable, tightly sequenced and managed for variance.",
        "delivery": [
            "Use a clear baseline plan with defined hand-offs and acceptance checks.",
            "Standardise the method and track exceptions rather than redesigning the approach.",
            "Escalate missed dependencies and quality variance early.",
        ],
        "control": "Use milestone control, quality checks, dependency tracking and exception reporting.",
    },
    "Making Movies": {
        "plain_english": "The intended result is clear, but quality depends on specialists working together and making good review decisions.",
        "delivery": [
            "Protect the agreed vision and define who has final creative authority.",
            "Plan specialist hand-offs, integration points and review cycles.",
            "Use prototypes and staged reviews before final production.",
        ],
        "control": "Use a clear brief, named creative authority, integration reviews and staged approvals.",
    },
    "Quest": {
        "plain_english": "The destination is clear, but the route is not. The team must test options before committing to the full plan.",
        "delivery": [
            "Break the work into short experiments against a clear outcome.",
            "Compare routes using evidence, cost, risk and time.",
            "Keep options open until a preferred route is proven.",
        ],
        "control": "Use hypothesis tracking, evidence reviews, option comparisons and decision gates.",
    },
    "Walking in Fog": {
        "plain_english": "Neither the destination nor the route is firm enough for a conventional plan. The first job is to create clarity.",
        "delivery": [
            "Plan in short horizons and make the next decision visible.",
            "Separate facts, assumptions and commitments.",
            "Use evidence gates before fixing cost, scope or timing.",
        ],
        "control": "Use an outcome frame, ranked assumption log, decision log and staged funding gates.",
    },
}


def clean_text(value: object, limit: int = 8000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def classify(assessment: str) -> str:
    text = assessment.lower()
    if "paint by numbers" in text or ("known outcome" in text and "known method" in text):
        return "Paint by Numbers"
    if "making movies" in text or "creative" in text:
        return "Making Movies"
    if "quest" in text or ("clear outcome" in text and "uncertain route" in text):
        return "Quest"
    return "Walking in Fog"


def safe_file(path: Path) -> bool:
    return bool(SAFE_FILENAME.fullmatch(path.name)) and " " not in path.name


def build_pdf(data: dict, output: Path) -> None:
    if data.get("force_pdf_failure"):
        raise RuntimeError("Forced PDF failure for test")

    navy = colors.HexColor("#18324A")
    blue = colors.HexColor("#2878B5")
    pale = colors.HexColor("#EAF2F8")
    grey = colors.HexColor("#65717C")
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1D252C"),
        spaceAfter=7,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=27,
        textColor=navy,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=navy,
        spaceBefore=10,
        spaceAfter=5,
    )
    lead = ParagraphStyle("Lead", parent=body, fontSize=12, leading=16, textColor=grey)
    small = ParagraphStyle("Small", parent=body, fontSize=8.5, leading=11)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Project Delivery Assessment",
    )

    project_type = data["project_type"]
    guidance = TYPE_GUIDANCE[project_type]
    assessment = data["assessment"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    callout = Table(
        [[
            Paragraph("<b>LIKELY PROJECT TYPE</b>", small),
            Paragraph(f"<b>{project_type}</b><br/>{guidance['plain_english']}", body),
        ]],
        colWidths=[1.45 * inch, 5.0 * inch],
    )
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("LINEBEFORE", (0, 0), (0, 0), 4, blue),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))

    def bullets(items: list[str]) -> ListFlowable:
        return ListFlowable(
            [ListItem(Paragraph(item, body), leftIndent=8) for item in items],
            bulletType="bullet",
            leftIndent=18,
            bulletColor=blue,
        )

    story = [
        Paragraph("PROJECT DELIVERY ASSESSMENT", ParagraphStyle(
            "Kicker", parent=small, fontName="Helvetica-Bold", textColor=blue, spaceAfter=7
        )),
        Paragraph(data["title"], h1),
        Paragraph("A practical No Fluff delivery assessment.", lead),
        Spacer(1, 8),
        callout,
        Paragraph("Assessment input", h2),
        Paragraph(assessment.replace("\n", "<br/>"), body),
        Paragraph("The four project types", h2),
        Table(
            [
                ["Project type", "Use when"],
                ["Paint by Numbers", "Outcome and method are known."],
                ["Making Movies", "Outcome is clear; coordinated creative execution drives quality."],
                ["Quest", "Outcome is clear; route is uncertain."],
                ["Walking in Fog", "Outcome and route are not yet firm."],
            ],
            colWidths=[1.65 * inch, 4.8 * inch],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8DEE3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]),
        ),
        Paragraph("What this means for delivery", h2),
        bullets(guidance["delivery"]),
        Paragraph("Main risks", h2),
        bullets([
            "Solving the wrong problem.",
            "Premature scope lock.",
            "Hidden dependencies and delayed decisions.",
            "Activity being reported as progress.",
        ]),
        Paragraph("Recommended control approach", h2),
        bullets([
            guidance["control"],
            "Record every material decision with an owner, evidence and date.",
            "Review delivery, risks and the next decision at least weekly.",
        ]),
        PageBreak(),
        Paragraph("Immediate next actions", h1),
        bullets([
            "Name the accountable sponsor.",
            "Write the outcome frame.",
            "Choose the top three assumptions to test.",
            "Create a two-week evidence plan.",
            "Book the first control gate.",
        ]),
        Paragraph("30-day action plan", h2),
    ]
    rows = [
        ["Timing", "Focus", "Exit test"],
        ["Days 1-5", "Frame", "Outcome, boundaries and biggest unknowns are agreed."],
        ["Days 6-10", "Test", "At least one critical assumption is narrowed."],
        ["Days 11-20", "Shape", "A preferred route and confidence range exist."],
        ["Days 21-30", "Commit", "The project is reclassified and the next stage is approved."],
    ]
    plan = Table(rows, colWidths=[1.0 * inch, 1.1 * inch, 4.35 * inch], repeatRows=1)
    plan.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D8DEE3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(plan)
    doc.build(story)


def build_powerpoint(data: dict, output: Path) -> None:
    if data.get("force_powerpoint_failure"):
        raise RuntimeError("Forced PowerPoint failure for test")
    build_powerpoint_file(data, output)


def build_email(data: dict, output: Path, attachments: list[Path], errors: list[str]) -> None:
    message = EmailMessage()
    message["Subject"] = f"{data['title']} - project delivery assessment"
    message["From"] = "delivery-assessment@example.invalid"
    message["To"] = clean_text(data.get("email")) or "client@example.invalid"
    status = "Both client files were generated." if len(attachments) == 2 else "The available client file is attached."
    body = [
        "Hello,",
        "",
        status,
        f"Likely project type: {data['project_type']}",
        "",
        "Immediate actions:",
        "1. Name the accountable sponsor.",
        "2. Agree the outcome frame.",
        "3. Test the highest-impact assumptions.",
        "4. Hold a control gate within 30 days.",
    ]
    if errors:
        body.extend(["", "Generation note:", *errors])
    body.extend(["", "Regards,", "Project Delivery Team"])
    message.set_content("\n".join(body))
    for attachment in attachments:
        mime, _ = mimetypes.guess_type(attachment.name)
        main, sub = (mime or "application/octet-stream").split("/", 1)
        message.add_attachment(
            attachment.read_bytes(),
            maintype=main,
            subtype=sub,
            filename=attachment.name,
        )
    output.write_bytes(message.as_bytes())


def generate_package(payload: dict, runs_dir: Path = RUNS_DIR) -> dict:
    assessment = clean_text(payload.get("assessment"))
    if not assessment:
        raise ValueError("Assessment text is required.")
    title = clean_text(payload.get("title"), 100) or "Project Delivery Assessment"
    run_id = uuid.uuid4().hex[:16]
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    data = {
        "title": title,
        "assessment": assessment,
        "email": clean_text(payload.get("email"), 200),
        "project_type": classify(assessment),
        "force_pdf_failure": bool(payload.get("force_pdf_failure")),
        "force_powerpoint_failure": bool(payload.get("force_powerpoint_failure")),
    }
    errors: list[str] = []
    generated: list[Path] = []

    pdf = run_dir / "project-delivery-assessment.pdf"
    try:
        build_pdf(data, pdf)
        generated.append(pdf)
    except Exception as exc:
        errors.append(f"PDF was not generated: {exc}")

    pptx = run_dir / "project-delivery-handover.pptx"
    try:
        build_powerpoint(data, pptx)
        generated.append(pptx)
    except Exception as exc:
        errors.append(f"PowerPoint was not generated: {exc}")

    email = run_dir / "project-delivery-email.eml"
    build_email(data, email, generated.copy(), errors)
    generated.append(email)

    zip_path = run_dir / "project-delivery-files.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for item in generated:
            bundle.write(item, arcname=item.name)
    generated.append(zip_path)

    for path in generated:
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"Expected generated file is missing or empty: {path.name}")
        if not safe_file(path):
            raise RuntimeError(f"Unsafe generated filename: {path.name}")

    files = [
        {
            "name": path.name,
            "size": path.stat().st_size,
            "url": f"/downloads/{run_id}/{path.name}",
        }
        for path in generated
    ]
    return {
        "run_id": run_id,
        "project_type": data["project_type"],
        "files": files,
        "errors": errors,
        "complete": not errors,
    }


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "DeliveryAssessment/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100_000:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = generate_package(payload)
            self.send_json(HTTPStatus.OK, result)
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Generation failed: {exc}"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/downloads/"):
            self.serve_download(parsed.path)
            return
        super().do_GET()

    def serve_download(self, request_path: str):
        parts = [unquote(part) for part in request_path.split("/") if part]
        if len(parts) != 3 or parts[0] != "downloads":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        run_id, filename = parts[1], parts[2]
        if not re.fullmatch(r"[a-f0-9]{16}", run_id) or not SAFE_FILENAME.fullmatch(filename):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        run_dir = (RUNS_DIR / run_id).resolve()
        target = (run_dir / filename).resolve()
        if target.parent != run_dir or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: HTTPStatus, payload: dict):
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(format % args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Open http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
