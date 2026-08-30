from __future__ import annotations

import unittest

from ralph_bench.adapters import (
    LMStudioProviderAdapter,
    PiHarnessAdapter,
    ProbeContext,
    built_in_registry,
    resolve_sut,
)
from ralph_bench.experiments import parse_experiment
from ralph_bench.preflight import PreflightError, run_sut_preflight
from ralph_bench.adapters.contracts import ProcessResult


def local_raw(**overrides):
    value = {
        "schema_version": "experiment/v1",
        "name": "local-demo",
        "challenge": "busy-intersection/v1",
        "client": "pi",
        "provider": "lm-studio",
        "model": "gemma-local",
        "track": "local",
        "client_options": {"loop": "native", "reasoning_effort": "medium"},
        "budget": {"max_attempts": 1},
    }
    value.update(overrides)
    return value


class PreflightTests(unittest.TestCase):
    @staticmethod
    def process(argv, _timeout):
        if argv[0] == "pi":
            if argv[1:] == ("--version",):
                return ProcessResult(0, "0.84.3\n")
            if argv[1:] == ("list", "--no-approve"):
                return ProcessResult(0, "npm:pi-wiggum\nnpm:pi-subagents\n")
            return ProcessResult(0, "updated\n")
        if argv[1:] == ("--version",):
            return ProcessResult(0, "CLI commit: 71bd99c\n")
        if argv[1:4] == ("server", "status", "--json"):
            return ProcessResult(0, '{"status":"running"}\n')
        if argv[1:5] == ("runtime", "update", "--all", "--yes"):
            return ProcessResult(0, "runtime is current\n")
        if argv[1:] == ("ls", "--llm", "--json"):
            return ProcessResult(0, '{"models":[{"modelKey":"gemma-local"}]}\n')
        if argv[1:] == ("ps", "--json"):
            return ProcessResult(0, '{"models":[{"id":"gemma-local"}]}\n')
        return ProcessResult(1, "", "unexpected command")

    def test_local_native_composition_refreshes_both_sides_before_readiness(self):
        experiment = parse_experiment(local_raw())
        registry = built_in_registry(
            pi=PiHarnessAdapter(process_runner=self.process),
            lmstudio=LMStudioProviderAdapter(process_runner=self.process),
        )
        context = ProbeContext(process_runner=self.process)
        sut = resolve_sut(experiment, registry, context=context)
        self.assertEqual(sut.harness_id, "harness/pi")
        self.assertEqual(sut.provider_id, "provider/lm-studio")
        session = run_sut_preflight(experiment, sut, registry, context=context)
        evidence = session.evidence
        self.assertEqual(evidence["schema_version"], "toolchain-preflight/v1")
        self.assertEqual(evidence["status"], "ready")
        self.assertEqual(
            evidence["harness"]["update"]["commands"][1:3],
            [["pi", "update"], ["pi", "update", "--extensions"]],
        )
        self.assertEqual(
            evidence["provider"]["readiness"]["evidence"]["loaded_models"],
            ["gemma-local"],
        )
        self.assertEqual(session.cleanup().status, "not-applicable")

    def test_failed_harness_refresh_blocks_provider_and_evaluation(self):
        def failed(argv, _timeout):
            if argv[0] == "pi" and argv[1:] == ("--version",):
                return ProcessResult(0, "0.84.3\n")
            if argv[0] == "pi" and argv[1:] == ("update",):
                return ProcessResult(1, "", "update failed with secret")
            return self.process(argv, _timeout)

        experiment = parse_experiment(local_raw())
        registry = built_in_registry(
            pi=PiHarnessAdapter(process_runner=failed),
            lmstudio=LMStudioProviderAdapter(process_runner=failed),
        )
        context = ProbeContext(process_runner=failed)
        sut = resolve_sut(experiment, registry, context=context)
        with self.assertRaisesRegex(PreflightError, "harness current-toolchain"):
            run_sut_preflight(experiment, sut, registry, context=context)


if __name__ == "__main__":
    unittest.main()
