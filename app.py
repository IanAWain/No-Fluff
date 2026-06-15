from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from server import RUNS_DIR, SAFE_FILENAME, generate_package


APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
DEFAULT_DATABASE = ROOT / "data" / "no-fluff.sqlite3"
STATUSES = ("Discovery", "Active", "At Risk", "On Hold", "Complete")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "development-only-change-me"),
        DATABASE=os.environ.get("DATABASE_PATH", str(DEFAULT_DATABASE)),
        RUNS_DIR=str(RUNS_DIR),
        MAX_CONTENT_LENGTH=100_000,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["RUNS_DIR"]).mkdir(parents=True, exist_ok=True)
    init_db(app)

    @app.context_processor
    def inject_globals():
        return {"statuses": STATUSES, "today": date.today().isoformat()}

    @app.get("/")
    def dashboard():
        projects = query_db(
            app,
            """
            SELECT *,
              CASE
                WHEN due_date <> '' AND due_date < ? AND status <> 'Complete' THEN 1
                ELSE 0
              END AS overdue
            FROM projects
            ORDER BY
              CASE status WHEN 'At Risk' THEN 0 WHEN 'Active' THEN 1 ELSE 2 END,
              updated_at DESC
            """,
            (date.today().isoformat(),),
        )
        counts = {status: 0 for status in STATUSES}
        for project in projects:
            counts[project["status"]] = counts.get(project["status"], 0) + 1
        return render_template("dashboard.html", projects=projects, counts=counts)

    @app.post("/projects")
    def create_project():
        name = clean(request.form.get("name"), 100)
        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("dashboard"))
        project_id = uuid.uuid4().hex[:12]
        now = utc_now()
        execute_db(
            app,
            """
            INSERT INTO projects (
              id, name, client, owner, due_date, status, assessment,
              project_type, run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, '', '', '', ?, ?)
            """,
            (
                project_id,
                name,
                clean(request.form.get("client"), 100),
                clean(request.form.get("owner"), 100),
                clean_date(request.form.get("due_date")),
                request.form.get("status") if request.form.get("status") in STATUSES else "Discovery",
                now,
                now,
            ),
        )
        flash("Project created.", "success")
        return redirect(url_for("project_detail", project_id=project_id))

    @app.get("/projects/<project_id>")
    def project_detail(project_id: str):
        project = get_project(app, project_id)
        files = files_for_run(app, project["run_id"])
        return render_template("project.html", project=project, files=files)

    @app.post("/projects/<project_id>")
    def update_project(project_id: str):
        get_project(app, project_id)
        name = clean(request.form.get("name"), 100)
        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("project_detail", project_id=project_id))
        status = request.form.get("status")
        if status not in STATUSES:
            abort(400)
        execute_db(
            app,
            """
            UPDATE projects
            SET name = ?, client = ?, owner = ?, due_date = ?, status = ?,
                assessment = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                clean(request.form.get("client"), 100),
                clean(request.form.get("owner"), 100),
                clean_date(request.form.get("due_date")),
                status,
                clean(request.form.get("assessment"), 8000),
                utc_now(),
                project_id,
            ),
        )
        flash("Project updated.", "success")
        return redirect(url_for("project_detail", project_id=project_id))

    @app.post("/projects/<project_id>/generate")
    def generate_project_files(project_id: str):
        project = get_project(app, project_id)
        assessment = clean(request.form.get("assessment") or project["assessment"], 8000)
        if not assessment:
            flash("Add assessment text before generating files.", "error")
            return redirect(url_for("project_detail", project_id=project_id))
        try:
            result = generate_package(
                {
                    "title": project["name"],
                    "email": clean(request.form.get("email"), 200),
                    "assessment": assessment,
                },
                Path(app.config["RUNS_DIR"]),
            )
        except Exception as exc:
            flash(f"Package generation failed: {exc}", "error")
            return redirect(url_for("project_detail", project_id=project_id))
        execute_db(
            app,
            """
            UPDATE projects
            SET assessment = ?, project_type = ?, run_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (assessment, result["project_type"], result["run_id"], utc_now(), project_id),
        )
        if result["errors"]:
            flash("Package created with a partial generation warning.", "warning")
        else:
            flash("Client package created.", "success")
        return redirect(url_for("project_detail", project_id=project_id))

    @app.get("/downloads/<run_id>/<filename>")
    def download(run_id: str, filename: str):
        if not re.fullmatch(r"[a-f0-9]{16}", run_id):
            abort(404)
        if not SAFE_FILENAME.fullmatch(filename):
            abort(404)
        run_dir = (Path(app.config["RUNS_DIR"]) / run_id).resolve()
        target = (run_dir / filename).resolve()
        if target.parent != run_dir or not target.is_file():
            abort(404)
        return send_file(
            target,
            as_attachment=True,
            download_name=filename,
            max_age=0,
            conditional=True,
        )

    @app.get("/api/projects")
    def projects_api():
        projects = query_db(app, "SELECT * FROM projects ORDER BY updated_at DESC")
        return jsonify([dict(project) for project in projects])

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


def clean(value: object, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def clean_date(value: object) -> str:
    text = clean(value, 10)
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError:
        return ""
    return text


def connect(app: Flask) -> sqlite3.Connection:
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


def init_db(app: Flask) -> None:
    connection = connect(app)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              client TEXT NOT NULL DEFAULT '',
              owner TEXT NOT NULL DEFAULT '',
              due_date TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'Discovery',
              assessment TEXT NOT NULL DEFAULT '',
              project_type TEXT NOT NULL DEFAULT '',
              run_id TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def query_db(app: Flask, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    connection = connect(app)
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def execute_db(app: Flask, sql: str, params: tuple = ()) -> None:
    connection = connect(app)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def get_project(app: Flask, project_id: str) -> sqlite3.Row:
    rows = query_db(app, "SELECT * FROM projects WHERE id = ?", (project_id,))
    if not rows:
        abort(404)
    return rows[0]


def files_for_run(app: Flask, run_id: str) -> list[dict]:
    if not run_id or not re.fullmatch(r"[a-f0-9]{16}", run_id):
        return []
    run_dir = Path(app.config["RUNS_DIR"]) / run_id
    if not run_dir.is_dir():
        return []
    preferred = {
        "project-delivery-files.zip": 0,
        "project-delivery-assessment.pdf": 1,
        "project-delivery-handover.pptx": 2,
        "project-delivery-email.eml": 3,
    }
    files = []
    for path in run_dir.iterdir():
        if path.is_file() and SAFE_FILENAME.fullmatch(path.name):
            files.append(
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "primary": path.suffix == ".zip",
                    "order": preferred.get(path.name, 99),
                }
            )
    return sorted(files, key=lambda item: (item["order"], item["name"]))


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
