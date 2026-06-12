from __future__ import annotations

import json
import http.client
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO

import server


SAMPLE = (
    "The business outcome is broadly understood, but success measures, decision "
    "rights and key dependencies are unresolved. The route is uncertain and the "
    "team should not commit to fixed scope, cost or dates yet."
)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.AppHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_generate_and_download_zip(self):
        payload = json.dumps(
            {
                "title": "Mobile Sample Assessment",
                "email": "client@example.com",
                "assessment": SAMPLE,
            }
        ).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=90)
        connection.request(
            "POST",
            "/api/generate",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        result = json.loads(response.read())
        connection.close()
        self.assertGreaterEqual(len(result["files"]), 4)
        self.assertNotIn(str(server.ROOT), json.dumps(result))

        zip_item = next(item for item in result["files"] if item["name"].endswith(".zip"))
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        connection.request("GET", zip_item["url"])
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="project-delivery-files.zip"',
        )
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        archive = zipfile.ZipFile(BytesIO(response.read()))
        connection.close()
        self.assertEqual(
            set(archive.namelist()),
            {
                "project-delivery-assessment.pdf",
                "project-delivery-handover.pptx",
                "project-delivery-email.eml",
            },
        )


if __name__ == "__main__":
    unittest.main()
