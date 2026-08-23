from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ralph_bench.browser_runtime import BrowserRuntimeError, run_browser_evaluation


class BrowserRuntimeTests(unittest.TestCase):
    def _invoke(self, root: Path, wait_error: BaseException) -> Mock:
        process = Mock()
        process.wait.side_effect = wait_error
        with (
            patch("ralph_bench.browser_runtime.subprocess.Popen", return_value=process),
            patch("ralph_bench.browser_runtime._terminate_group") as terminate,
        ):
            if isinstance(wait_error, subprocess.TimeoutExpired):
                with self.assertRaisesRegex(BrowserRuntimeError, "exceeded"):
                    run_browser_evaluation(
                        root / "candidate",
                        root / "browser-output",
                        raw_evidence=root / "raw",
                        timeout_seconds=1,
                        chromium=root / "chromium",
                        playwright_browsers_path=root / "playwright",
                    )
            else:
                with self.assertRaises(type(wait_error)):
                    run_browser_evaluation(
                        root / "candidate",
                        root / "browser-output",
                        raw_evidence=root / "raw",
                        timeout_seconds=1,
                        chromium=root / "chromium",
                        playwright_browsers_path=root / "playwright",
                    )
            terminate.assert_called_once_with(process)
        return process

    def test_timeout_terminates_browser_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._invoke(
                Path(temporary),
                subprocess.TimeoutExpired(("browser-worker",), 1),
            )

    def test_interrupt_terminates_browser_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self._invoke(Path(temporary), KeyboardInterrupt())


if __name__ == "__main__":
    unittest.main()
