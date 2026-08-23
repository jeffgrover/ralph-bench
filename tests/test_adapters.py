from __future__ import annotations

import unittest
from dataclasses import replace

from ralph_bench.adapters import built_in_registry, resolve_sut
from ralph_bench.adapters.contracts import CostCapabilities, ModelOffer, ProbeContext, ProbeResult, ProcessResult
from ralph_bench.adapters.codex import CodexHarnessAdapter
from ralph_bench.adapters.chatgpt import ChatGPTProviderAdapter
from ralph_bench.adapters.resolver import ResolutionError
from ralph_bench.experiments import parse_experiment
from tests.test_experiments import cloud_raw


class AdapterTests(unittest.TestCase):
    def test_codex_plan_uses_supported_01490_flags_and_toml_config(self):
        plan = CodexHarnessAdapter().plan(
            "gpt-5.6-luna", "max", "workspace-write", "/tmp/workspace"
        )
        self.assertEqual(
            plan.argv,
            (
                "codex", "exec", "--ignore-user-config", "--ignore-rules",
                "--strict-config", "--json", "--ephemeral", "--model",
                "gpt-5.6-luna", "--sandbox", "workspace-write",
                "--skip-git-repo-check", "-c", 'model_reasoning_effort="max"',
                "-C", "/tmp/workspace", "-",
            ),
        )
        self.assertEqual(plan.stdin_mode, "prompt")
        self.assertEqual(plan.prompt_argument, "-")

    def test_partial_and_failed_codex_probes_are_bounded_and_nonsecret(self):
        def timeout(argv, timeout):
            return ProcessResult(124, "", "", True)
        result = CodexHarnessAdapter(process_runner=timeout).detect(ProbeContext(process_runner=timeout))
        self.assertEqual(result.status, "timed-out")
        secret = "super-secret-token"
        def failed(argv, timeout):
            return ProcessResult(1, "", f"failed {secret}")
        result = CodexHarnessAdapter(process_runner=failed).detect(ProbeContext(process_runner=failed))
        self.assertEqual(result.status, "failed")
        self.assertNotIn(secret, repr(result))

        def tainted_version(argv, timeout):
            return ProcessResult(0, f"codex-cli 0.149.0 {secret}\n")

        result = CodexHarnessAdapter(process_runner=tainted_version).detect(
            ProbeContext(process_runner=tainted_version)
        )
        self.assertFalse(result.available)
        self.assertNotIn(secret, repr(result))

    def test_unverified_codex_version_is_rejected_before_resolution(self):
        def future_version(argv, timeout):
            return ProcessResult(0, "codex-cli 0.150.0\n")

        result = CodexHarnessAdapter(process_runner=future_version).detect(
            ProbeContext(process_runner=future_version)
        )
        self.assertEqual(result.status, "unsupported")
        self.assertFalse(result.available)
        self.assertEqual(result.version, "0.150.0")
    def test_codex_chatgpt_luna_composes_without_cross_product_runner(self):
        calls = []
        def process(argv, timeout):
            calls.append(argv)
            return ProcessResult(0, "codex-cli 0.149.0\n" if argv[-1] == "--version" else "Logged in using ChatGPT\n")
        sut = resolve_sut(parse_experiment(cloud_raw()), built_in_registry(), context=ProbeContext(process_runner=process))
        self.assertEqual(sut.harness_id, "harness/codex-cli")
        self.assertEqual(sut.provider_id, "provider/openai-chatgpt")
        self.assertEqual(sut.model_id, "model/gpt-5.6-luna")
        self.assertEqual(calls, [("codex", "--version"), ("codex", "login", "status")])
        self.assertIn("static P0 descriptor", " ".join(sut.warnings))

        cost_capabilities = ChatGPTProviderAdapter().cost_capabilities()
        self.assertEqual(
            cost_capabilities.billing_modes, ("flat_subscription",)
        )
        self.assertEqual(
            cost_capabilities.evidence_statuses, ("unavailable",)
        )

    def test_probe_context_detaches_metadata_and_rejects_invalid_timeout(self):
        metadata = {"credential_available": True}
        context = ProbeContext(metadata=metadata)
        metadata["credential_available"] = False
        self.assertIs(context.metadata["credential_available"], True)
        with self.assertRaises(ValueError):
            ProbeContext(timeout_seconds=0)

    def test_unknown_model_gets_conservative_generic_capabilities(self):
        experiment = parse_experiment({**cloud_raw(), "model": "operator-model"})
        def process(argv, timeout):
            return ProcessResult(0, "codex-cli 0.149.0\n" if argv[-1] == "--version" else "Logged in using ChatGPT\n")
        sut = resolve_sut(experiment, built_in_registry(), context=ProbeContext(process_runner=process))
        self.assertEqual(sut.model_id, "model/generic")
        self.assertFalse(sut.model_binding.capabilities.known)
        self.assertIn("unknown", " ".join(sut.warnings))

    def test_explicit_executable_is_used_during_resolution_and_planning(self):
        experiment = parse_experiment(
            {
                **cloud_raw(),
                "client_options": {
                    "executable": "/opt/codex/bin/codex",
                    "reasoning_effort": "max",
                },
            }
        )
        calls: list[tuple[str, ...]] = []

        def process(argv, timeout):
            calls.append(argv)
            output = (
                "codex-cli 0.149.0\n"
                if argv[-1] == "--version"
                else "Logged in using ChatGPT\n"
            )
            return ProcessResult(0, output)

        resolve_sut(
            experiment,
            built_in_registry(),
            context=ProbeContext(process_runner=process),
        )
        self.assertEqual(calls[0][0], "/opt/codex/bin/codex")
        self.assertEqual(calls[1][0], "/opt/codex/bin/codex")
        plan = CodexHarnessAdapter().plan(
            experiment.model,
            experiment.client_options.reasoning_effort,
            executable=experiment.client_options.executable,
        )
        self.assertEqual(plan.argv[0], "/opt/codex/bin/codex")

    def test_incompatible_fake_provider_has_structured_resolution_error(self):
        class IncompatibleProvider(ChatGPTProviderAdapter):
            descriptor = replace(ChatGPTProviderAdapter.descriptor, capabilities=())
            def detect(self, context=ProbeContext()):
                return ProbeResult("ok", True, "fake")
            def discover_models(self, context=ProbeContext()):
                return (ModelOffer("gpt-5.6-luna", "Luna"),)
            def cost_capabilities(self):
                return CostCapabilities()

        registry = built_in_registry()
        registry.providers["provider/openai-chatgpt"] = IncompatibleProvider()
        def process(argv, timeout):
            output = (
                "codex-cli 0.149.0\n"
                if argv[-1] == "--version"
                else "Logged in using ChatGPT\n"
            )
            return ProcessResult(0, output)

        with self.assertRaises(ResolutionError) as raised:
            resolve_sut(
                parse_experiment(cloud_raw()),
                registry,
                context=ProbeContext(process_runner=process),
            )
        self.assertEqual(raised.exception.issue.code, "connection-incompatible")

    def test_provider_billing_mode_must_match_experiment_track(self):
        class MeteredProvider(ChatGPTProviderAdapter):
            def cost_capabilities(self):
                return CostCapabilities(
                    billing_modes=("metered_api",),
                    evidence_statuses=("complete",),
                )

        registry = built_in_registry()
        registry.providers["provider/openai-chatgpt"] = MeteredProvider()

        def process(argv, timeout):
            return ProcessResult(
                0,
                "codex-cli 0.149.0\n"
                if argv[-1] == "--version"
                else "Logged in using ChatGPT\n",
            )

        with self.assertRaises(ResolutionError) as raised:
            resolve_sut(
                parse_experiment(cloud_raw()),
                registry,
                context=ProbeContext(process_runner=process),
            )
        self.assertEqual(raised.exception.issue.code, "track-incompatible")


if __name__ == "__main__":
    unittest.main()
