from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import unicodedata
import zipfile

from ralph_bench.bundles import (
    BundleError,
    BundleLimits,
    BundleValidationError,
    P0_REQUIRED_FILES,
    finalize_bundle,
    safe_extract_bundle,
    validate_bundle,
)
from ralph_bench.capture_validation import PNG_SIGNATURE, WEBM_EBML_SIGNATURE
from ralph_bench.costs import CostEvidence


class BundleTests(unittest.TestCase):
    def make_staging(self, root: Path) -> None:
        values = {name: b"{}\n" for name in P0_REQUIRED_FILES if name.endswith(".json")}
        artifact_data = b"<html></html>\n"
        relative = b"index.html"
        artifact_digest = hashlib.sha256()
        artifact_digest.update(len(relative).to_bytes(8, "big"))
        artifact_digest.update(relative)
        artifact_digest.update(len(artifact_data).to_bytes(8, "big"))
        artifact_digest.update(artifact_data)
        artifact_hash = artifact_digest.hexdigest()
        scenario_id = "busy-intersection-balanced"
        profile = "balanced"
        seed = 17
        values["prompt.txt"] = b"build the thing\n"
        values["events/canonical.jsonl"] = b"{\"schema_version\":\"event/v1\"}\n"
        values["captures/overview.webm"] = WEBM_EBML_SIGNATURE + b"\x42\x82\x84webm"
        values["captures/overview.png"] = (
            PNG_SIGNATURE
            + b"\x00\x00\x00\rIHDR"
            + (2).to_bytes(4, "big")
            + (1).to_bytes(4, "big")
        )
        values["events/raw/client.jsonl"] = b"raw\n"
        values["attempts/attempt-001/attempt.json"] = b"{}\n"
        values["attempts/attempt-001/prompt.txt"] = b"prompt\n"
        values["attempts/attempt-001/public-checks.json"] = b"{}\n"
        values["artifact/submission/index.html"] = artifact_data
        values["run.json"] = json.dumps(
            {
                "schema_version": "run/v1",
                "run_id": "run-1",
                "selected_candidate_hash": artifact_hash,
                "challenge": "busy-intersection/v1",
                "scenario_pack": "traffic-intersection-p0a",
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
            }
        ).encode("utf-8")
        values["challenge.json"] = json.dumps(
            {
                "challenge_id": "busy-intersection/v1",
                "scenario_pack": "traffic-intersection-p0a",
                "scenario": {
                    "scenario_id": scenario_id,
                    "profile": profile,
                    "seed": seed,
                },
            }
        ).encode("utf-8")
        values["evaluation/assertions.json"] = json.dumps(
            {
                "schema_version": "assertions/v1",
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
                "assertions": [],
            }
        ).encode("utf-8")
        values["evaluation/capacity-curve.json"] = json.dumps(
            {
                "schema_version": "capacity-curve/v1",
                "scenario_id": scenario_id,
                "scenario_profile": profile,
                "seed": seed,
                "stages": [],
            }
        ).encode("utf-8")
        values["captures/overview.json"] = json.dumps(
            {
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
                "evidence_refs": ["events/raw/client.jsonl"],
            }
        ).encode("utf-8")
        values["cost.json"] = (
            json.dumps(
                CostEvidence.subscription_unmetered(
                    requested_model="gpt-5.6-luna"
                ).as_dict()
            ).encode("utf-8")
            + b"\n"
        )
        for name, data in values.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def test_invalid_capture_media_and_identity_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            self.make_staging(stage)
            (stage / "captures/overview.png").write_bytes(b"not-png")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "invalid-png.ralph.zip")
            self.assertIn("invalid_png", {item.code for item in caught.exception.diagnostics})

            self.make_staging(base / "webm-stage")
            (base / "webm-stage/captures/overview.webm").write_bytes(b"not-webm")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "webm-stage", base / "invalid-webm.ralph.zip")
            self.assertIn("invalid_webm", {item.code for item in caught.exception.diagnostics})

            self.make_staging(base / "metadata-stage")
            metadata_path = base / "metadata-stage/captures/overview.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            del metadata["frame_rate_fps"]
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "metadata-stage", base / "metadata.ralph.zip")
            self.assertIn(
                "capture_metadata_invalid",
                {item.code for item in caught.exception.diagnostics},
            )

            self.make_staging(base / "artifact-stage")
            artifact_capture_path = base / "artifact-stage/captures/overview.json"
            artifact_capture = json.loads(
                artifact_capture_path.read_text(encoding="utf-8")
            )
            artifact_capture["artifact_hash"] = "b" * 64
            artifact_capture_path.write_text(
                json.dumps(artifact_capture), encoding="utf-8"
            )
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "artifact-stage", base / "artifact.ralph.zip")
            self.assertIn(
                "capture_artifact_mismatch",
                {item.code for item in caught.exception.diagnostics},
            )

            self.make_staging(base / "identity-stage")
            capture_path = base / "identity-stage/captures/overview.json"
            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            capture["seed"] = 29
            capture_path.write_text(json.dumps(capture), encoding="utf-8")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "identity-stage", base / "mismatch.ralph.zip")
            self.assertIn(
                "capture_identity_mismatch",
                {item.code for item in caught.exception.diagnostics},
            )

    def test_finalize_is_byte_deterministic_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first, second = base / "a", base / "b"
            self.make_staging(first)
            self.make_staging(second)
            one = finalize_bundle(first, base / "one.ralph.zip")
            two = finalize_bundle(second, base / "two.ralph.zip")
            self.assertEqual((base / "one.ralph.zip").read_bytes(), (base / "two.ralph.zip").read_bytes())
            self.assertTrue(validate_bundle(one.path).valid)
            self.assertEqual(one.bundle_sha256, hashlib.sha256((base / "one.ralph.zip").read_bytes()).hexdigest())
            with zipfile.ZipFile(one.path) as archive:
                names = archive.namelist()
                self.assertEqual(names[-1], "checksums.sha256")
                self.assertEqual(names[:-1], sorted(names[:-1]))
                self.assertEqual(tuple(sorted(names)), two.entries)
            extracted = safe_extract_bundle(one.path, base / "extracted")
            with zipfile.ZipFile(one.path) as archive:
                inventory = archive.read("checksums.sha256")
            self.assertEqual((base / "extracted" / "checksums.sha256").read_bytes(), inventory)
            self.assertEqual(tuple(sorted(extracted.entries)), two.entries)
            with self.assertRaises(BundleError) as caught:
                safe_extract_bundle(one.path, base / "extracted")
            self.assertIn("extraction_exists", {item.code for item in caught.exception.diagnostics})

    def test_atomic_install_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.make_staging(base / "stage")
            destination = base / "same.ralph.zip"
            finalize_bundle(base / "stage", destination)
            original = destination.read_bytes()
            with self.assertRaises(BundleError) as caught:
                finalize_bundle(base / "stage", destination)
            self.assertIn("output_exists", {item.code for item in caught.exception.diagnostics})
            self.assertEqual(destination.read_bytes(), original)

    def test_missing_profile_and_unknown_schema_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.make_staging(base / "stage")
            (base / "stage" / "run.json").write_text('{"schema_version":"run/v999","run_id":"x"}')
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "stage", base / "bad.ralph.zip")
            codes = {item.code for item in caught.exception.diagnostics}
            self.assertIn("run_schema_unknown", codes)

    def test_unknown_and_malformed_required_features_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            self.make_staging(stage)
            (stage / "run.json").write_text(
                json.dumps(
                    {
                        "schema_version": "run/v1",
                        "run_id": "run-1",
                        "required_features": ["future/encrypted-evidence"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "unknown-feature.ralph.zip")
            self.assertIn(
                "required_feature_unknown",
                {item.code for item in caught.exception.diagnostics},
            )

            (stage / "run.json").write_text(
                '{"schema_version":"run/v1","run_id":"run-1",'
                '"required_features":"not-a-list"}',
                encoding="utf-8",
            )
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "malformed-feature.ralph.zip")
            self.assertIn(
                "required_features_invalid",
                {item.code for item in caught.exception.diagnostics},
            )

    def test_traversal_and_case_collision_never_extract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            malicious = base / "bad.zip"
            with zipfile.ZipFile(malicious, "w") as archive:
                archive.writestr("../escape", b"x")
                archive.writestr("Run.json", b"x")
                archive.writestr("run.json", b"x")
            result = validate_bundle(malicious)
            codes = {item.code for item in result.diagnostics}
            self.assertIn("unsafe_path", codes)
            self.assertIn("case_collision", codes)
            target = base / "extracted"
            with self.assertRaises(BundleValidationError):
                safe_extract_bundle(malicious, target)
            self.assertFalse(target.exists())
            self.assertFalse((base / "escape").exists())

    def test_checksum_mismatch_and_missing_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.make_staging(base / "stage")
            destination = base / "bundle.ralph.zip"
            finalize_bundle(base / "stage", destination)
            # Mutating a payload without touching the inventory must fail.
            tampered = base / "tampered.zip"
            with zipfile.ZipFile(destination) as source, zipfile.ZipFile(tampered, "w") as target:
                for info in source.infolist():
                    target.writestr(info, b"tampered" if info.filename == "metrics.json" else source.read(info))
            result = validate_bundle(tampered)
            codes = {item.code for item in result.diagnostics}
            self.assertIn("checksum_mismatch", codes)
            # A missing explicit evidence reference is rejected at finalization.
            metrics = base / "stage" / "metrics.json"
            metrics.write_text('{"evidence_refs":["events/raw/missing.json"]}')
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "stage", base / "reference-missing.ralph.zip")
            self.assertIn("missing_evidence_reference", {item.code for item in caught.exception.diagnostics})

            metrics.write_text('{"evidence_refs":["events/raw/client.jsonl#event-1"]}')
            valid = finalize_bundle(base / "stage", base / "reference-fragment.ralph.zip")
            self.assertTrue(validate_bundle(valid.path).valid)
            metrics.write_text('{"evidence_refs":["events/raw/client.jsonl:42"]}')
            valid = finalize_bundle(base / "stage", base / "reference-line.ralph.zip")
            self.assertTrue(validate_bundle(valid.path).valid)
            metrics.write_text('{"evidence_refs":["https://example.test/evidence.json"]}')
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "stage", base / "external-reference.ralph.zip")
            self.assertIn("external_evidence_reference", {item.code for item in caught.exception.diagnostics})

    def test_cost_invocation_evidence_references_must_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            self.make_staging(stage)
            (stage / "cost.json").write_text(
                json.dumps(
                    CostEvidence.subscription_unmetered(
                        requested_model="gpt-5.6-luna",
                        evidence_references=(
                            "events/raw/missing.jsonl#attempt-1",
                            "events/raw/also-missing.jsonl#attempt-1",
                        ),
                    ).as_dict()
                ),
                encoding="utf-8",
            )
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "missing-cost-evidence.ralph.zip")
            diagnostics = caught.exception.diagnostics
            missing = [
                item for item in diagnostics if item.code == "missing_evidence_reference"
            ]
            self.assertEqual(len(missing), 2)
            self.assertTrue(all(item.path == "cost.json" for item in missing))

    def test_invalid_cost_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            self.make_staging(stage)
            (stage / "cost.json").write_text(
                '{"schema_version":"cost/v1","status":"unavailable"}',
                encoding="utf-8",
            )
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "invalid-cost.ralph.zip")
            self.assertIn(
                "cost_evidence_invalid",
                {item.code for item in caught.exception.diagnostics},
            )

    def test_invalid_cost_mode_and_currency_are_rejected(self) -> None:
        for field, value in (("billing_mode", "made_up"), ("currency", "EUR")):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temp:
                    base = Path(temp)
                    stage = base / "stage"
                    self.make_staging(stage)
                    cost = CostEvidence.subscription_unmetered().as_dict()
                    cost[field] = value
                    (stage / "cost.json").write_text(
                        json.dumps(cost), encoding="utf-8"
                    )
                    with self.assertRaises(BundleValidationError) as caught:
                        finalize_bundle(stage, base / "invalid-cost.ralph.zip")
                    self.assertIn(
                        "cost_evidence_invalid",
                        {item.code for item in caught.exception.diagnostics},
                    )

    def test_staging_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            self.make_staging(stage)
            try:
                os.symlink(stage / "prompt.txt", stage / "events" / "raw" / "link")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "bundle.ralph.zip")
            self.assertIn("staging_symlink", {item.code for item in caught.exception.diagnostics})

    def test_bundle_path_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.make_staging(base / "stage")
            bundle = finalize_bundle(base / "stage", base / "bundle.ralph.zip")
            link = base / "linked.ralph.zip"
            try:
                link.symlink_to(bundle.path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            self.assertFalse(validate_bundle(link).valid)
            with self.assertRaises(BundleValidationError):
                safe_extract_bundle(link, base / "extracted")

    def test_limits_are_injectable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.make_staging(base / "stage")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "stage", base / "bundle.ralph.zip", BundleLimits(max_file_size=1))
            self.assertIn("file_size_limit", {item.code for item in caught.exception.diagnostics})
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "stage", base / "entries.ralph.zip", BundleLimits(max_entries=2))
            self.assertIn("entry_limit", {item.code for item in caught.exception.diagnostics})
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(base / "stage", base / "total.ralph.zip", BundleLimits(max_total_size=1))
            self.assertIn("total_size_limit", {item.code for item in caught.exception.diagnostics})
            valid = finalize_bundle(base / "stage", base / "ratio-source.ralph.zip")
            ratio_codes = {item.code for item in validate_bundle(valid.path, BundleLimits(max_compression_ratio=0.1)).diagnostics}
            self.assertIn("compression_ratio", ratio_codes)

            unsupported = base / "unsupported.zip"
            with zipfile.ZipFile(unsupported, "w", compression=zipfile.ZIP_BZIP2) as archive:
                archive.writestr("payload", b"payload")
            self.assertIn("unsupported_compression", {item.code for item in validate_bundle(unsupported).diagnostics})

            inventory = base / "inventory-cases.zip"
            with zipfile.ZipFile(inventory, "w") as archive:
                digest = hashlib.sha256(b"x").hexdigest()
                archive.writestr("payload", b"x")
                archive.writestr("checksums.sha256", f"{digest}  payload\n{digest}  payload\n{digest}  extra\n".encode())
            inventory_codes = {item.code for item in validate_bundle(inventory).diagnostics}
            self.assertIn("inventory_duplicate", inventory_codes)
            self.assertIn("inventory_unknown_entry", inventory_codes)

            missing_inventory = base / "inventory-missing.zip"
            with zipfile.ZipFile(missing_inventory, "w") as archive:
                archive.writestr("payload", b"x")
                archive.writestr("checksums.sha256", b"")
            self.assertIn("inventory_missing_entry", {item.code for item in validate_bundle(missing_inventory).diagnostics})

    def test_staging_inventory_is_reserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stage = base / "stage"
            self.make_staging(stage)
            (stage / "checksums.sha256").write_text("caller supplied")
            with self.assertRaises(BundleValidationError) as caught:
                finalize_bundle(stage, base / "reserved.ralph.zip")
            self.assertIn("reserved_inventory_path", {item.code for item in caught.exception.diagnostics})

    def test_path_canonicalization_and_reserved_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            archive_path = base / "unsafe.zip"
            # NFC and NFD spellings must collide after canonicalization.
            nfc = unicodedata.normalize("NFC", "café.txt")
            nfd = unicodedata.normalize("NFD", "café.txt")
            with zipfile.ZipFile(archive_path, "w") as archive:
                for name in ("/absolute", "dir\\escape", "CON.txt", "file:stream", "name. ", nfc, nfd):
                    archive.writestr(name, b"x")
            result = validate_bundle(archive_path)
            codes = {item.code for item in result.diagnostics}
            self.assertIn("unsafe_path", codes)
            self.assertIn("reserved_name", codes)
            self.assertIn("case_collision", codes)

    def test_archive_symlink_and_special_modes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for mode, expected in ((stat.S_IFLNK | 0o777, "symlink_entry"), (stat.S_IFIFO | 0o600, "special_file_entry")):
                archive_path = base / f"mode-{expected}.zip"
                info = zipfile.ZipInfo("payload")
                info.external_attr = mode << 16
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(info, b"x")
                codes = {item.code for item in validate_bundle(archive_path).diagnostics}
                self.assertIn(expected, codes)

    def test_inventory_and_extraction_failures_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            archive_path = base / "inventory.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("run.json", b"{}")
                archive.writestr("checksums.sha256", b"malformed\n")
            codes = {item.code for item in validate_bundle(archive_path).diagnostics}
            self.assertIn("inventory_malformed", codes)
            self.assertIn("inventory_missing_entry", codes)
            target = base / "existing"
            target.mkdir()
            with self.assertRaises(BundleError) as caught:
                safe_extract_bundle(archive_path, target)
            self.assertIn("inventory_malformed", {item.code for item in caught.exception.diagnostics})


if __name__ == "__main__":
    unittest.main()
