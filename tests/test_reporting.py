from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ralph_bench.bundles import finalize_bundle
from ralph_bench.reporting import ReportBuildError, build_site
from tests import test_bundles


class ReportingTests(unittest.TestCase):
    def test_build_reads_valid_bundles_without_executing_candidate_markup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "staging"
            test_bundles.BundleTests().make_staging(staging)
            inbox = root / "inbox"
            inbox.mkdir()
            finalize_bundle(staging, inbox / "run-1.ralph.zip")
            output = root / "site"

            result = build_site(inbox, output)

            self.assertEqual(result.valid_bundle_count, 1)
            self.assertEqual(result.invalid_bundle_count, 0)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "data" / "catalog.json").is_file())
            catalog = json.loads((output / "data" / "catalog.json").read_text())
            self.assertEqual(len(catalog), 1)
            run_page = next((output / "runs").glob("*/index.html"))
            report = run_page.read_text()
            self.assertIn("download candidate entrypoint", report)
            self.assertNotIn("<html></html>", report)

    def test_invalid_bundles_are_recorded_outside_normal_views(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "broken.ralph.zip").write_bytes(b"not a zip")

            result = build_site(inbox, root / "site")

            self.assertEqual(result.valid_bundle_count, 0)
            self.assertEqual(result.invalid_bundle_count, 1)
            self.assertIn("broken.ralph.zip", (root / "site" / "data" / "invalid-bundles.json").read_text())
            self.assertNotIn("broken.ralph.zip", (root / "site" / "index.html").read_text())

    def test_build_refuses_to_overwrite_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "site"
            output.mkdir()
            with self.assertRaisesRegex(ReportBuildError, "already exists"):
                build_site(root / "missing", output)


if __name__ == "__main__":
    unittest.main()
