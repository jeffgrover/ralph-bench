from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ralph_bench.bundles import finalize_bundle
from ralph_bench.preview import open_bundle_preview, prepare_bundle_preview
from tests import test_bundles


class PreviewTests(unittest.TestCase):
    def test_preview_extracts_recorded_media_and_never_opens_candidate_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            test_bundles.BundleTests().make_staging(payload)
            bundle = finalize_bundle(payload, root / "result.ralph.zip").path
            prepared = prepare_bundle_preview(bundle)
            self.assertEqual(prepared.media_path.name, "overview.webm")
            self.assertTrue(prepared.media_path.is_file())

            opened: list[str] = []
            preview = open_bundle_preview(
                bundle, opener=lambda uri: opened.append(uri) or True
            )
            self.assertEqual(opened, [preview.media_path.as_uri()])
            self.assertNotIn("index.html", opened[0])


if __name__ == "__main__":
    unittest.main()
