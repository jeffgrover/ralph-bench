"""Missing usage after an interrupted attempt must never become free work."""
import json
from pathlib import Path
import tempfile
import unittest

from ralph_bench.adapters.codex_execution import parse_codex_jsonl
from ralph_bench.adapters.pi_execution import parse_pi_jsonl
from ralph_bench.conductor import _usage


class UsageEvidenceTests(unittest.TestCase):
    def test_both_parsers_preserve_absent_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps({"type": "message_end", "message": {"role": "assistant", "content": []}}) + "\n")
            self.assertEqual(dict(parse_codex_jsonl(path).usage), {})
            self.assertEqual(dict(parse_pi_jsonl(path).usage), {})

    def test_shared_totals_distinguish_missing_partial_and_reported_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "codex-attempt-001.summary.json"
            missing.write_text(json.dumps({"usage": {}, "turns": 0}))
            result = _usage(root)
            self.assertIsNone(result["total_tokens"])
            self.assertEqual(result["status"], "unavailable")
            second = root / "codex-attempt-002.summary.json"
            second.write_text(json.dumps({"usage": {"total_tokens": 17}}))
            result = _usage(root)
            self.assertIsNone(result["total_tokens"])
            self.assertEqual(result["observed_tokens"]["total_tokens"], 17)
            self.assertEqual(result["status"], "partial")
            zero = {key: 0 for key in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cache_read_tokens")}
            missing.write_text(json.dumps({"usage": zero}))
            second.write_text(json.dumps({"usage": zero}))
            self.assertEqual(_usage(root)["total_tokens"], 0)
            self.assertEqual(_usage(root)["status"], "complete")
