from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from dataclasses import replace

from ralph_bench.adapters import built_in_registry, resolve_sut
from ralph_bench.adapters.contracts import CostCapabilities, ModelOffer, ProbeContext, ProbeResult, ProcessResult
from ralph_bench.adapters.codex import CodexHarnessAdapter
from ralph_bench.adapters.chatgpt import ChatGPTProviderAdapter
from ralph_bench.adapters.lmstudio import LMStudioProviderAdapter
from ralph_bench.adapters.pi import PiHarnessAdapter
from ralph_bench.adapters.resolver import ResolutionError
from ralph_bench.experiments import parse_experiment
from tests.test_experiments import cloud_raw


class AdapterTests(unittest.TestCase):
    def test_codex_plan_uses_current_preflight_verified_flags_and_toml_config(self):
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

    def test_new_codex_version_is_accepted_and_verified_during_preflight(self):
        def future_version(argv, timeout):
            return ProcessResult(0, "codex-cli 0.150.0\n")

        result = CodexHarnessAdapter(process_runner=future_version).detect(
            ProbeContext(process_runner=future_version)
        )
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.available)
        self.assertEqual(result.version, "0.150.0")
        self.assertIn("preflight", " ".join(result.warnings))

    def test_pi_refreshes_self_and_extensions_and_preserves_package_identity(self):
        calls: list[tuple[str, ...]] = []

        def process(argv, _timeout):
            calls.append(argv)
            if argv[-1] == "--version":
                return ProcessResult(0, "0.84.3\n")
            if argv[1:] == ("list", "--no-approve"):
                return ProcessResult(0, "npm:pi-wiggum\nnpm:pi-subagents\n")
            return ProcessResult(0, "updated\n")

        result = PiHarnessAdapter(process_runner=process).ensure_current(
            ProbeContext(
                process_runner=process,
                metadata={"pi_extension_root": "/path/that/does/not/exist"},
            )
        )
        self.assertEqual(result.status, "current")
        self.assertEqual(
            result.commands,
            (
                ("pi", "list", "--no-approve"),
                ("pi", "update"),
                ("pi", "update", "--extensions"),
                ("pi", "list", "--no-approve"),
            ),
        )
        self.assertEqual(
            result.evidence["extension_identities_after"],
            ["npm:pi-wiggum", "npm:pi-subagents"],
        )
        self.assertEqual(calls[2:4], [("pi", "update"), ("pi", "update", "--extensions")])

    def test_pi_self_update_failure_still_attempts_extension_refresh(self):
        calls: list[tuple[str, ...]] = []

        def process(argv, _timeout):
            calls.append(argv)
            if argv[-1] == "--version":
                return ProcessResult(0, "0.84.3\n")
            if argv[1:] == ("update",):
                return ProcessResult(1, "", "global npm install is not writable")
            if argv[1:] == ("list", "--no-approve"):
                return ProcessResult(0, "npm:pi-wiggum\n")
            return ProcessResult(0, "updated\n")

        result = PiHarnessAdapter(process_runner=process).ensure_current(
            ProbeContext(
                process_runner=process,
                metadata={"pi_extension_root": "/path/that/does/not/exist"},
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("global npm", result.message)
        self.assertIn(("pi", "update", "--extensions"), calls)
        self.assertEqual(result.evidence["failed_commands"], [["pi", "update"]])

    def test_pi_plan_loads_native_wiggum_resources_and_explicit_local_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "pkg" / "pi-wiggum"
            (root / "extensions").mkdir(parents=True)
            (root / "prompts").mkdir()
            for path in (
                root / "extensions" / "plan-mode-guard.ts",
                root / "extensions" / "stop-guard.ts",
                root / "prompts" / "wiggum.md",
            ):
                path.write_text("fixture", encoding="utf-8")
            subagents = root.parent / "pi-subagents"
            subagents.mkdir()
            (subagents / "index.ts").write_text("fixture", encoding="utf-8")
            plan = PiHarnessAdapter(extension_root=root).plan(
                "candidate", "medium", "workspace-write", "/tmp/workspace"
            )
            self.assertIn("--provider", plan.argv)
            self.assertIn("lmstudio", plan.argv)
            self.assertIn("--prompt-template", plan.argv)
            self.assertEqual(plan.prompt_argument, "-")
            self.assertEqual(plan.warnings, ())

    def test_lmstudio_refresh_and_readiness_use_bounded_cli_evidence(self):
        calls: list[tuple[str, ...]] = []

        def process(argv, _timeout):
            calls.append(argv)
            if argv[1:] == ("--version",):
                return ProcessResult(0, "CLI commit: 71bd99c\n")
            if argv[1:4] == ("server", "status", "--json"):
                return ProcessResult(0, '{"status":"running"}\n')
            if argv[1:5] == ("runtime", "update", "--all", "--yes"):
                return ProcessResult(0, "runtime is current\n")
            if argv[1:] == ("ls", "--llm", "--json"):
                return ProcessResult(0, '{"models":[{"modelKey":"gemma-local","displayName":"Gemma local"}]}\n')
            if argv[1:] == ("ps", "--json"):
                return ProcessResult(0, '{"models":[{"id":"gemma-local"}]}\n')
            return ProcessResult(1, "", "unexpected")

        adapter = LMStudioProviderAdapter(process_runner=process)
        context = ProbeContext(process_runner=process)
        update = adapter.ensure_current(context)
        self.assertEqual(update.status, "current")
        self.assertEqual(update.before_version, "71bd99c")
        self.assertEqual(update.after_version, "71bd99c")
        self.assertEqual(adapter.discover_models(context)[0].provider_model_id, "gemma-local")
        preparation = adapter.prepare("gemma-local", context)
        self.assertTrue(preparation.readiness.available)
        self.assertEqual(preparation.readiness.status, "ready")
        self.assertEqual(preparation.cleanup().status, "not-applicable")
        self.assertIn(("lms", "runtime", "update", "--all", "--yes"), calls)

    def test_lmstudio_stopped_server_is_available_but_not_ready(self):
        def process(argv, _timeout):
            if argv[1:] == ("--version",):
                return ProcessResult(0, "CLI commit: 71bd99c\n")
            return ProcessResult(0, '{"status":"stopped"}\n')

        adapter = LMStudioProviderAdapter(process_runner=process)
        probe = adapter.detect(ProbeContext(process_runner=process))
        self.assertTrue(probe.available)
        self.assertEqual(probe.status, "partial")
        preparation = adapter.prepare("gemma-local", ProbeContext(process_runner=process))
        self.assertFalse(preparation.readiness.available)
        self.assertEqual(preparation.readiness.status, "not-ready")

    def test_lmstudio_transaction_starts_loads_and_restores_only_owned_state(self):
        calls: list[tuple[str, ...]] = []
        state = {"running": False, "loaded": False}

        def process(argv, _timeout):
            calls.append(argv)
            if argv[1:] == ("server", "status", "--json"):
                return ProcessResult(0, '{"status":"running"}' if state["running"] else '{"status":"stopped"}')
            if argv[1:] == ("server", "start"):
                state["running"] = True
                return ProcessResult(0, "started")
            if argv[1:] == ("server", "stop"):
                state["running"] = False
                return ProcessResult(0, "stopped")
            if argv[1:] == ("load", "gemma-local", "--yes"):
                state["loaded"] = True
                return ProcessResult(0, "loaded")
            if argv[1:] == ("ps", "--json"):
                models = '[{"id":"gemma-local"}]' if state["loaded"] else '{"models":[]}'
                return ProcessResult(0, models)
            if argv[1:] == ("unload", "gemma-local"):
                state["loaded"] = False
                return ProcessResult(0, "unloaded")
            return ProcessResult(1, "", "unexpected")

        adapter = LMStudioProviderAdapter(process_runner=process)
        preparation = adapter.prepare("gemma-local", ProbeContext(process_runner=process))
        self.assertTrue(preparation.readiness.available)
        self.assertEqual(preparation.readiness.evidence["provider_mutation"], "server-start-and-model-load")
        cleanup = preparation.cleanup()
        self.assertEqual(cleanup.status, "complete")
        self.assertFalse(state["running"])
        self.assertFalse(state["loaded"])
        call_count = len(calls)
        self.assertIs(preparation.cleanup(), cleanup)
        self.assertEqual(len(calls), call_count)
        self.assertIn(("lms", "server", "stop"), calls)
        self.assertIn(("lms", "unload", "gemma-local"), calls)

    def test_lmstudio_failed_load_keeps_cleanup_registered(self):
        calls: list[tuple[str, ...]] = []
        state = {"running": False}

        def process(argv, _timeout):
            calls.append(argv)
            if argv[1:] == ("server", "status", "--json"):
                return ProcessResult(0, '{"status":"running"}' if state["running"] else '{"status":"stopped"}')
            if argv[1:] == ("server", "start"):
                state["running"] = True
                return ProcessResult(0, "started")
            if argv[1:] == ("load", "gemma-local", "--yes"):
                return ProcessResult(1, "", "load failed")
            if argv[1:] == ("ps", "--json"):
                return ProcessResult(0, '{"models":[]}')
            if argv[1:] == ("server", "stop"):
                state["running"] = False
                return ProcessResult(0, "stopped")
            return ProcessResult(1, "", "unexpected")

        adapter = LMStudioProviderAdapter(process_runner=process)
        preparation = adapter.prepare("gemma-local", ProbeContext(process_runner=process))
        self.assertFalse(preparation.readiness.available)
        cleanup = preparation.cleanup()
        self.assertEqual(cleanup.status, "complete")
        self.assertFalse(state["running"])
        self.assertIn(("lms", "server", "stop"), calls)
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
