from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ralph_bench.browser_runtime import (
    BrowserRuntimeError,
    find_chromium,
    find_playwright_browsers_path,
    run_browser_evaluation,
)


class BrowserRuntimeTests(unittest.TestCase):
    def test_explicit_browser_and_playwright_environment_overrides_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chromium = root / "Google Chrome"
            chromium.touch()
            chromium.chmod(0o700)
            ffmpeg = root / "ffmpeg-1011" / "ffmpeg-mac"
            ffmpeg.parent.mkdir()
            ffmpeg.touch()
            ffmpeg.chmod(0o700)
            with patch.dict(
                os.environ,
                {
                    "RALPH_BENCH_CHROMIUM": str(chromium),
                    "PLAYWRIGHT_BROWSERS_PATH": str(root),
                },
            ):
                self.assertEqual(find_chromium(), chromium.resolve())
                self.assertEqual(find_playwright_browsers_path(), root.resolve())

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
