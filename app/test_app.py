from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from server import SAFE_FILENAME, generate_package


SAMPLE = """
The target outcome is broadly understood, but success measures are not yet agreed.
The delivery route is uncertain, key data dependencies are unresolved, and decision
rights are unclear. The team needs a practical 30-day plan before committing to a
fixed scope, cost or delivery date.
""".strip()


class GenerationTests(unittest.TestCase):
    def run_case(self, **overrides):
        with tempfile.TemporaryDirectory() as temp:
            result = generate_package(
                {
                    "title": "Sample Assessment",
                    "email": "client@example.com",
                    "assessment": SAMPLE,
                    **overrides,
                },
                Path(temp),
            )
            run_dir = Path(temp) / result["run_id"]
            names = {item["name"] for item in result["files"]}
            for name in names:
                self.assertRegex(name, SAFE_FILENAME)
                self.assertNotIn(" ", name)
                self.assertGreater((run_dir / name).stat().st_size, 0)
            with zipfile.ZipFile(run_dir / "project-delivery-files.zip") as bundle:
                zipped = set(bundle.namelist())
            self.assertIn("project-delivery-email.eml", zipped)
            self.assertEqual({path.name for path in run_dir.iterdir()}, names)
            return result, names, zipped

    def test_complete_package(self):
        result, names, zipped = self.run_case()
        self.assertTrue(result["complete"])
        self.assertIn("project-delivery-assessment.pdf", names)
        self.assertIn("project-delivery-handover.pptx", names)
        self.assertIn("project-delivery-assessment.pdf", zipped)
        self.assertIn("project-delivery-handover.pptx", zipped)

    def test_pdf_failure_still_creates_powerpoint_and_email(self):
        result, names, zipped = self.run_case(force_pdf_failure=True)
        self.assertFalse(result["complete"])
        self.assertNotIn("project-delivery-assessment.pdf", names)
        self.assertIn("project-delivery-handover.pptx", names)
        self.assertIn("project-delivery-email.eml", names)
        self.assertIn("project-delivery-handover.pptx", zipped)

    def test_powerpoint_failure_still_creates_pdf_and_email(self):
        result, names, zipped = self.run_case(force_powerpoint_failure=True)
        self.assertFalse(result["complete"])
        self.assertIn("project-delivery-assessment.pdf", names)
        self.assertNotIn("project-delivery-handover.pptx", names)
        self.assertIn("project-delivery-email.eml", names)
        self.assertIn("project-delivery-assessment.pdf", zipped)


if __name__ == "__main__":
    unittest.main()
