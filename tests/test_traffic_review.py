from __future__ import annotations

import json
import copy
from pathlib import Path
import tempfile
import unittest

from ralph_bench.capture_validation import capture_metadata_issues
from ralph_bench.reporting import _comparison_eligibility, build_site
from ralph_bench.traffic_review import REQUIRED_RULES, REVIEW_RUBRIC, ReviewDocument, load_review_documents, resolve_traffic_review
from tests import test_bundles
from ralph_bench.bundles import finalize_bundle


class TrafficReviewTests(unittest.TestCase):
    def _review(self, artifact_hash="a" * 64):
        return {
            "schema_version": "traffic-review/v2", "run_id": "run-1",
            "artifact_hash": artifact_hash, "status": "pass", "reviewer": "human",
            "rubric_version": REVIEW_RUBRIC, "scenario_id": "busy-intersection-balanced",
            "seed": 17, "coverage_complete": True, "reviewed_intervals": ["full evaluation"],
            "coverage_ms": [[0, 100]], "evidence_refs": ["captures/overview.webm"],
            "findings": {rule: {"status": "pass", "detail": "Observed entry, movement, transitions and finish over the complete recording.", "evidence_refs": ["captures/overview.webm"]} for rule in REQUIRED_RULES},
        }

    def _bundle(self, root: Path, *, functional: bool = True, isolation: str = "L1") -> tuple[Path, str]:
        stage = root / "stage"
        test_bundles.BundleTests().make_staging(stage)
        run_path = stage / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run.update(
            {
                "performance_eligible": functional,
                "measurement_status": "measured" if functional else "unmeasurable",
                "traffic_review": {"status": "pending", "reason": "awaiting review"},
                "public_conformance": {"outcome": "passed"},
            }
        )
        run_path.write_text(json.dumps(run), encoding="utf-8")
        experiment_path = stage / "experiment.json"
        experiment = json.loads(experiment_path.read_text())
        experiment["track"] = "cloud-subscription"
        experiment_path.write_text(json.dumps(experiment))
        (stage / "provenance" / "configuration.json").write_text(json.dumps({"effective": {"tool_policy": "standard", "loop": "controlled"}}))
        (stage / "provenance" / "isolation.json").write_text(
            json.dumps({"level": isolation}), encoding="utf-8"
        )
        bundle = root / "run.ralph.zip"
        finalized = finalize_bundle(stage, bundle)
        return finalized.path, run["selected_candidate_hash"]

    def test_missing_failed_and_insufficient_reviews_never_compare(self) -> None:
        run = {"run_id": "r", "selected_candidate_hash": "a" * 64}
        self.assertEqual(resolve_traffic_review(run).status, "pending")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fail.json").write_text(
                json.dumps(
                    {
                        "schema_version": "traffic-review/v1",
                        "run_id": "r",
                        "artifact_hash": "a" * 64,
                        "status": "fail",
                        "reviewer": "human",
                        "rubric_version": "traffic/v2",
                        "evidence_refs": ["captures/overview.webm"],
                        "reviewed_intervals": ["all"],
                    }
                ),
                encoding="utf-8",
            )
            docs, _ = load_review_documents(root)
            failed = resolve_traffic_review(run, docs)
            self.assertEqual(failed.status, "fail")
            self.assertFalse(failed.performance_comparison_eligible)

            (root / "fail.json").write_text(
                json.dumps(
                    {
                        "schema_version": "traffic-review/v1",
                        "run_id": "r",
                        "artifact_hash": "a" * 64,
                        "status": "pass",
                        "reviewer": "human",
                        "rubric_version": "traffic/v2",
                        "evidence_refs": ["captures/overview.webm"],
                        "coverage_complete": False,
                        "reviewed_intervals": [],
                    }
                ),
                encoding="utf-8",
            )
            docs, _ = load_review_documents(root)
            insufficient = resolve_traffic_review(run, docs)
            self.assertEqual(insufficient.status, "unverifiable")
            self.assertFalse(insufficient.performance_comparison_eligible)

    def test_artifact_provenance_mismatch_is_unverifiable(self) -> None:
        run = {"run_id": "r", "selected_candidate_hash": "a" * 64}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "r.json").write_text(
                json.dumps(
                    {
                        "schema_version": "traffic-review/v1",
                        "run_id": "r",
                        "artifact_hash": "b" * 64,
                        "status": "pass",
                        "reviewer": "human",
                        "rubric_version": "traffic/v2",
                        "evidence_refs": ["captures/overview.webm"],
                        "reviewed_intervals": ["all"],
                        "coverage_complete": True,
                    }
                ),
                encoding="utf-8",
            )
            docs, _ = load_review_documents(root)
            review = resolve_traffic_review(run, docs)
            self.assertEqual(review.status, "unverifiable")
            self.assertIn("review_artifact_mismatch", {item.code for item in review.diagnostics})

    def test_report_keeps_review_outside_immutable_bundle_and_marks_l0_experimental(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, artifact_hash = self._bundle(root, isolation="L0/unsealed")
            inbox = root / "inbox"
            inbox.mkdir()
            bundle.replace(inbox / bundle.name)
            original = (inbox / bundle.name).read_bytes()
            reviews = root / "reviews"
            reviews.mkdir()
            (reviews / "run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "traffic-review/v1",
                        "run_id": "run-1",
                        "artifact_hash": artifact_hash,
                        "status": "pass",
                        "reviewer": "human",
                        "rubric_version": "traffic/v2",
                        "evidence_refs": ["captures/overview.webm"],
                        "reviewed_intervals": ["all"],
                        "coverage_complete": True,
                    }
                ),
                encoding="utf-8",
            )
            (reviews / "run.json").write_text(json.dumps(self._review(artifact_hash)))
            result = build_site(inbox, root / "site", reviews=reviews)
            catalog = json.loads((root / "site" / "data" / "catalog.json").read_text())
            self.assertEqual(result.review_diagnostic_count, 0)
            self.assertTrue(catalog[0]["performance_comparison_eligible"])
            self.assertFalse(catalog[0]["official_ranking_eligible"])
            self.assertEqual((inbox / bundle.name).read_bytes(), original)

    def test_report_quarantines_mismatched_review_without_rejecting_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _artifact_hash = self._bundle(root)
            inbox = root / "inbox"
            inbox.mkdir()
            bundle.replace(inbox / bundle.name)
            reviews = root / "reviews"
            reviews.mkdir()
            (reviews / "run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "traffic-review/v1",
                        "run_id": "run-1",
                        "artifact_hash": "b" * 64,
                        "status": "pass",
                        "reviewer": "human",
                        "rubric_version": "traffic/v2",
                        "evidence_refs": ["captures/overview.webm"],
                        "reviewed_intervals": ["all"],
                        "coverage_complete": True,
                    }
                ),
                encoding="utf-8",
            )
            result = build_site(inbox, root / "site", reviews=reviews)
            catalog = json.loads((root / "site" / "data" / "catalog.json").read_text())
            invalid = json.loads((root / "site" / "data" / "invalid-reviews.json").read_text())
            self.assertEqual(result.valid_bundle_count, 1)
            self.assertEqual(catalog[0]["traffic_review"]["status"], "unverifiable")
            self.assertFalse(catalog[0]["performance_comparison_eligible"])
            self.assertTrue(any(item["code"] == "review_artifact_mismatch" for item in invalid[0]["diagnostics"]))

    def test_report_rejects_review_that_points_outside_bundle_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, artifact_hash = self._bundle(root)
            inbox = root / "inbox"
            inbox.mkdir()
            bundle.replace(inbox / bundle.name)
            reviews = root / "reviews"
            reviews.mkdir()
            (reviews / "run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "traffic-review/v1",
                        "run_id": "run-1",
                        "artifact_hash": artifact_hash,
                        "status": "pass",
                        "reviewer": "human",
                        "rubric_version": "traffic/v2",
                        "evidence_refs": ["missing/physical-proof.json"],
                        "reviewed_intervals": ["all"],
                        "coverage_complete": True,
                    }
                ),
                encoding="utf-8",
            )
            build_site(inbox, root / "site", reviews=reviews)
            catalog = json.loads((root / "site" / "data" / "catalog.json").read_text())
            self.assertEqual(catalog[0]["traffic_review"]["status"], "unverifiable")
            self.assertFalse(catalog[0]["performance_comparison_eligible"])

    def test_pass_requires_each_rule_scenario_and_recording(self):
        run = {"run_id": "run-1", "selected_candidate_hash": "a" * 64,
               "scenario_id": "busy-intersection-balanced", "seed": 17}
        changes = [
            {"schema_version": "traffic-review/v1"}, {"findings": {}},
            {"coverage_ms": [[0, True]]}, {"coverage_ms": [[5, 1]]},
            {"seed": 18}, {"scenario_id": "other"}, {"rubric_version": "invented"},
            {"evidence_refs": ["captures/overview.png"]}, {"status": []},
        ]
        for change in changes:
            with self.subTest(change=change):
                value = {**self._review(), **change}
                result = resolve_traffic_review(run, [ReviewDocument("r.json", value)])
                self.assertFalse(result.performance_comparison_eligible)
        value = self._review()
        value["findings"]["collision-avoidance"]["status"] = "fail"
        value["coverage_complete"] = False
        self.assertEqual(resolve_traffic_review(run, [ReviewDocument("r.json", value)]).status, "fail")

    def test_review_gaps_and_unknown_isolation_never_get_official_rank(self):
        for coverage in ([[0, 40], [60, 100]], [[0, 50]], [[0, 100]]):
            with self.subTest(coverage=coverage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bundle, artifact_hash = self._bundle(root, isolation="invented-trusted-level")
                inbox = root / "inbox"
                inbox.mkdir()
                bundle.replace(inbox / bundle.name)
                reviews = root / "reviews"
                reviews.mkdir()
                review = self._review(artifact_hash)
                review["coverage_ms"] = coverage
                (reviews / "r.json").write_text(json.dumps(review))
                build_site(inbox, root / "site", reviews=reviews)
                record = json.loads((root / "site/data/catalog.json").read_text())[0]
                self.assertFalse(record["official_ranking_eligible"])
                self.assertEqual(record["performance_comparison_eligible"], coverage == [[0, 100]])

    def test_comparison_requires_public_private_and_standard_policy(self):
        run = {"run_id": "run-1", "selected_candidate_hash": "a" * 64,
               "scenario_id": "busy-intersection-balanced", "seed": 17,
               "challenge": "busy-intersection/v1", "scenario_pack": "traffic-intersection-p0a",
               "scenario_profile": "balanced", "public_conformance": {"status": "passed"},
               "performance_eligible": True, "measurement_status": "measured"}
        review = resolve_traffic_review(run, [ReviewDocument("r.json", self._review())])
        configuration = {"effective": {"tool_policy": "standard", "loop": "controlled"}}
        experiment = {"track": "cloud-subscription"}
        eligible, _, cohort = _comparison_eligibility(run, experiment, configuration, review)
        self.assertTrue(eligible)
        self.assertEqual(cohort["challenge"], "busy-intersection/v1")
        for change in ({"public_conformance": {}}, {"public_conformance": {"status": "failed"}},
                       {"performance_eligible": "true"}, {"measurement_status": "unmeasurable"},
                       {"challenge": "busy-intersection/v2"}, {"scenario_profile": None}):
            self.assertFalse(_comparison_eligibility({**run, **change}, experiment, configuration, review)[0])
        for policy in ("calibration", "unknown", None):
            changed = copy.deepcopy(configuration)
            changed["effective"]["tool_policy"] = policy
            self.assertFalse(_comparison_eligibility(run, experiment, changed, review)[0])

    def test_capture_v1_is_historically_readable_and_v2_has_explicit_clock(self) -> None:
        legacy = {
            "schema_version": "capture/v1",
            "viewport": {"width": 2, "height": 1},
            "scenario_id": "s",
            "scenario_profile": "p",
            "seed": 1,
            "simulated_horizon_ms": 100,
            "simulation_interval_ms": {"start": 0, "end": 100, "step": 10},
            "simulation_phase": "legacy",
            "playback_step_ms": 10,
            "playback_delay_ms": 1,
            "playback_rate": 1,
            "duration_ms": 10,
            "frame_rate_fps": 25,
            "capture_worker": {"id": "fixture", "protocol": "p", "version": "1"},
            "browser": "chromium",
            "browser_version": "fixture",
            "playwright_version": "fixture",
        }
        self.assertEqual(capture_metadata_issues(legacy), ())
        current = dict(legacy)
        current.update(
            {
                "schema_version": "capture/v2",
                "evaluation_horizon_ms": 100,
                "evaluation_elapsed_ms": 125,
                "poster_evaluation_elapsed_ms": 50,
                "evaluation_interval_ms": {"start": 0, "end": 100, "step": 10},
                "capture_wall_time_ms": 140,
            }
        )
        for key in ("simulated_horizon_ms", "simulation_interval_ms", "duration_ms"):
            current.pop(key, None)
        self.assertEqual(capture_metadata_issues(current), ())


if __name__ == "__main__":
    unittest.main()
