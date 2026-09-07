from __future__ import annotations

import tempfile
from pathlib import Path
import shutil
import unittest

from ralph_bench.review_server import ReviewServerError, prepare_review


class ReviewServerTests(unittest.TestCase):
    def test_prepare_review_copies_only_review_inputs(self):
        project_root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "run"
            captures = source / "captures"
            captures.mkdir(parents=True)
            (source / "run.json").write_text('{"run_id":"demo"}\n')
            (captures / "overview.json").write_text('{"duration_ms":1000}\n')
            (captures / "overview.webm").write_bytes(b"webm")
            (source / "candidate").mkdir()
            (source / "candidate" / "index.html").write_text("not served")

            prepared = prepare_review(source, project_root)
            try:
                self.assertTrue((prepared.root / "index.html").is_file())
                self.assertTrue((prepared.root / "run" / "run.json").is_file())
                self.assertTrue((prepared.root / "run" / "captures" / "overview.webm").is_file())
                self.assertFalse((prepared.root / "run" / "candidate").exists())
                self.assertIn("/run/captures/overview.webm", prepared.url)
            finally:
                shutil.rmtree(prepared.root, ignore_errors=True)

    def test_prepare_review_rejects_missing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ReviewServerError):
                prepare_review(Path(directory), Path(__file__).parents[1])
