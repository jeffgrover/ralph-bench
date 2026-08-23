from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ralph_bench.bundle_materialization import (
    AttemptBundleEvidence,
    BundleMaterializationError,
    RunBundleEvidence,
    finalize_run_bundle,
)
from ralph_bench.bundles import validate_bundle
from ralph_bench.capture_validation import PNG_SIGNATURE, WEBM_EBML_SIGNATURE
from ralph_bench.costs import CostEvidence
from ralph_bench.execution import candidate_tree_hash


class BundleMaterializationTests(unittest.TestCase):
    def evidence(self, root: Path) -> RunBundleEvidence:
        scenario_id = "busy-intersection-balanced"
        profile = "balanced"
        seed = 17
        artifact = root / "artifact"
        artifact.mkdir()
        (artifact / "index.html").write_text("<html></html>", encoding="utf-8")
        artifact_hash = candidate_tree_hash(artifact)
        raw = root / "raw"
        raw.mkdir()
        (raw / "codex.jsonl").write_text('{"type":"thread.started"}\n')
        video = root / "overview.webm"
        video.write_bytes(WEBM_EBML_SIGNATURE + b"\x42\x82\x84webm")
        poster = root / "overview.png"
        poster.write_bytes(
            PNG_SIGNATURE
            + b"\x00\x00\x00\rIHDR"
            + (2).to_bytes(4, "big")
            + (1).to_bytes(4, "big")
        )
        return RunBundleEvidence(
            run_manifest={
                "schema_version": "run/v1",
                "run_id": "run-1",
                "selected_candidate_hash": artifact_hash,
                "challenge": "busy-intersection/v1",
                "scenario_pack": "traffic-intersection-p0a",
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
            },
            experiment={"schema_version": "experiment/v1"},
            challenge={
                "challenge_id": "busy-intersection/v1",
                "scenario_pack": "traffic-intersection-p0a",
                "scenario": {
                    "scenario_id": scenario_id,
                    "profile": profile,
                    "seed": seed,
                },
            },
            prompt="Build a simulation.\n",
            metrics={"accepted": True},
            cost=CostEvidence.subscription_unmetered(
                requested_model="gpt-5.6-luna"
            ),
            failures=(),
            canonical_events_jsonl=(
                '{"schema_version":"event/v1","sequence":1}\n'
            ),
            assertions={
                "passed": True,
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
            },
            capacity_curve={
                "stages": [],
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
            },
            runtime_observations={"browser": "fixture"},
            overview_video=video,
            overview_poster=poster,
            overview_metadata={
                "schema_version": "capture/v1",
                "viewport": {"width": 2, "height": 1},
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
                "simulated_horizon_ms": 100,
                "simulation_interval_ms": {"start": 0, "end": 100, "step": 10},
                "simulation_phase": "full-scenario-replay",
                "playback_step_ms": 10,
                "playback_delay_ms": 1,
                "playback_rate": 10,
                "duration_ms": 10,
                "frame_rate_fps": 25,
                "capture_worker": {
                    "id": "fixture",
                    "protocol": "browser-worker/v1",
                    "version": "1",
                },
                "browser": "chromium",
                "browser_version": "fixture",
                "playwright_version": "fixture",
                "artifact_hash": artifact_hash,
                "challenge": "busy-intersection/v1",
                "evidence_refs": ["events/raw/codex.jsonl"],
            },
            artifact=artifact,
            raw_evidence=raw,
            attempts=(
                AttemptBundleEvidence(
                    1,
                    {"attempt_number": 1},
                    "Build a simulation.\n",
                    {"passed": True},
                    candidate=artifact,
                ),
            ),
            provenance={
                "environment": {"keys": []},
                "redaction": {"status": "complete"},
                "configuration": {"requested": {}},
                "sut-resolution": {"harness": "codex-cli"},
                "isolation": {"level": "L1"},
            },
        )

    def test_materialized_bundle_is_complete_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = finalize_run_bundle(
                self.evidence(root),
                staging=root / "staging",
                output=root / "run-1.ralph.zip",
            )
            validation = validate_bundle(result.path)
            self.assertTrue(
                validation.valid,
                [(item.code, item.path, item.detail) for item in validation.diagnostics],
            )
            self.assertEqual(validation.run_id, "run-1")

    def test_missing_provenance_fails_before_a_partial_tree_survives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = self.evidence(root)
            broken = replace(evidence, provenance={"environment": {}})
            with self.assertRaisesRegex(
                BundleMaterializationError, "missing bundle provenance"
            ):
                finalize_run_bundle(
                    broken,
                    staging=root / "staging",
                    output=root / "run-1.ralph.zip",
                )
            self.assertFalse((root / "staging").exists())


if __name__ == "__main__":
    unittest.main()
