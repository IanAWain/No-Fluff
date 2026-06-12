from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask_app import create_app


class FlaskProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE": str(root / "test.sqlite3"),
                "RUNS_DIR": str(root / "runs"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def create_project(self):
        response = self.client.post(
            "/projects",
            data={
                "name": "Sample Transformation",
                "client": "Example Client",
                "owner": "Ian",
                "due_date": "2026-07-31",
                "status": "Discovery",
            },
        )
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"].split("/")[-1]

    def test_dashboard_and_project_workflow(self):
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        project_id = self.create_project()
        response = self.client.post(
            f"/projects/{project_id}",
            data={
                "name": "Sample Transformation",
                "client": "Example Client",
                "owner": "Ian",
                "due_date": "2026-07-31",
                "status": "Active",
                "assessment": "The outcome is clear but the route is uncertain. This is a Quest.",
            },
        )
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(f"/projects/{project_id}")
        self.assertIn(b"Sample Transformation", detail.data)
        self.assertIn(b"The outcome is clear", detail.data)

    def test_generate_client_package(self):
        project_id = self.create_project()
        assessment = (
            "The outcome is broadly understood, but measures, dependencies and "
            "the route are uncertain. Do not lock cost or dates."
        )
        self.client.post(
            f"/projects/{project_id}",
            data={
                "name": "Sample Transformation",
                "client": "Example Client",
                "owner": "Ian",
                "due_date": "2026-07-31",
                "status": "Active",
                "assessment": assessment,
            },
        )
        response = self.client.post(
            f"/projects/{project_id}/generate",
            data={"assessment": assessment, "email": "client@example.com"},
        )
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(f"/projects/{project_id}")
        self.assertIn(b"Download all files (ZIP)", detail.data)
        projects = self.client.get("/api/projects").json
        self.assertEqual(projects[0]["project_type"], "Walking in Fog")
        run_id = projects[0]["run_id"]
        download = self.client.get(f"/downloads/{run_id}/project-delivery-files.zip")
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download.headers["Content-Disposition"])
        download.close()


if __name__ == "__main__":
    unittest.main()
