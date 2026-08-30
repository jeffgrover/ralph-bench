from __future__ import annotations

from importlib.metadata import PackageNotFoundError
import unittest
from unittest.mock import patch

from ralph_bench.browser_worker import _worker_version


class BrowserWorkerTests(unittest.TestCase):
    def test_source_checkout_has_explicit_worker_version_fallback(self) -> None:
        with patch(
            "ralph_bench.browser_worker.package_version",
            side_effect=PackageNotFoundError,
        ):
            self.assertEqual(_worker_version(), "source-checkout")


if __name__ == "__main__":
    unittest.main()
