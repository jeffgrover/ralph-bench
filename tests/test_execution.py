from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from ralph_bench.events import EventRecorder
from ralph_bench.execution import (
    AttemptPreservationError,
    AttemptStore,
    CleanupStack,
    ControlledAttemptLoop,
    ExecutionError,
    HarnessAttemptResult,
    PublicCheckResult,
    RunState,
    RunStateMachine,
    StateTransitionError,
    candidate_tree_hash,
    expand_repetitions,
)


class IncrementingClock:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> int:
        self.value += 1_000_000
        return self.value


class ExecutionTests(unittest.TestCase):
    def test_state_machine_accepts_lifecycle_and_rejects_terminal_reentry(self) -> None:
        machine = RunStateMachine()
        for state in (
            RunState.PREFLIGHT,
            RunState.READY,
            RunState.RUNNING,
            RunState.PUBLIC_CHECK,
            RunState.FINALIZING,
            RunState.COMPLETE,
        ):
            machine.transition(state, f"enter {state.value}")
        self.assertEqual(machine.state, RunState.COMPLETE)
        with self.assertRaises(StateTransitionError):
            machine.transition(RunState.RUNNING, "cannot reopen")

    def test_repetition_ids_are_preallocated_and_unique(self) -> None:
        ids = iter(("run-a", "run-b", "run-c"))
        self.assertEqual(
            expand_repetitions("experiment-a", 3, lambda: next(ids)),
            ("run-a", "run-b", "run-c"),
        )
        duplicates = iter(("same", "same"))
        with self.assertRaises(ExecutionError):
            expand_repetitions("experiment-a", 2, lambda: next(duplicates))

    def test_cleanup_runs_lifo_continues_after_failure_and_is_idempotent(self) -> None:
        calls: list[str] = []
        stack = CleanupStack()
        stack.register("first", lambda: calls.append("first"))

        def fail() -> None:
            calls.append("failure")
            raise RuntimeError("fixture cleanup failed")

        stack.register("failure", fail)
        stack.register("last", lambda: calls.append("last"))
        report = stack.run()
        self.assertEqual(calls, ["last", "failure", "first"])
        self.assertFalse(report.succeeded)
        self.assertEqual(stack.run(), report)
        self.assertEqual(calls, ["last", "failure", "first"])

    def test_controlled_loop_preserves_failure_then_green_and_charges_both(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live_candidate = root / "live"
            live_candidate.mkdir()
            feedback_seen: list[object] = []

            def execute(attempt_number, feedback, admission):
                feedback_seen.append(feedback)
                (live_candidate / "index.html").write_text(
                    f"attempt {attempt_number}", encoding="utf-8"
                )
                admission.admit(
                    process_spawned=True,
                    prompt_provided=True,
                    evidence_ref=f"events/raw/attempt-{attempt_number}.jsonl#1",
                )
                return HarnessAttemptResult(live_candidate, "process_exited")

            def check(_attempt_number, candidate):
                content = (candidate / "index.html").read_text(encoding="utf-8")
                passed = content == "attempt 2"
                return PublicCheckResult(
                    passed,
                    {} if passed else {"failed_assertions": ["entrypoint-title"]},
                    ("entrypoint-title",),
                )

            recorder = EventRecorder(IncrementingClock())
            result = ControlledAttemptLoop(
                executor=execute,
                public_checker=check,
                attempt_store=AttemptStore(root / "attempts"),
                recorder=recorder,
            ).run()

            self.assertTrue(result.accepted)
            self.assertEqual(result.chargeable_attempt_units, 2)
            self.assertEqual(len(result.attempts), 2)
            self.assertIsNone(feedback_seen[0])
            self.assertEqual(
                feedback_seen[1], {"failed_assertions": ["entrypoint-title"]}
            )
            self.assertEqual(
                (root / "attempts/attempt-001/submission/index.html").read_text(),
                "attempt 1",
            )
            self.assertEqual(
                (root / "attempts/attempt-002/submission/index.html").read_text(),
                "attempt 2",
            )
            event_types = [event.event_type for event in recorder.snapshot()]
            self.assertEqual(event_types.count("model_invocation.started"), 2)

    def test_pre_invocation_failure_has_zero_chargeable_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def execute(_attempt_number, _feedback, _admission):
                return HarnessAttemptResult(None, "spawn_failed")

            result = ControlledAttemptLoop(
                executor=execute,
                public_checker=lambda _number, _path: self.fail("checker must not run"),
                attempt_store=AttemptStore(Path(temporary) / "attempts"),
                recorder=EventRecorder(IncrementingClock()),
            ).run()
            self.assertEqual(result.chargeable_attempt_units, 0)
            self.assertEqual(len(result.attempts), 1)

    def test_executor_exception_after_admission_is_preserved_and_charged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def execute(_attempt_number, _feedback, admission):
                admission.admit(
                    process_spawned=True,
                    prompt_provided=True,
                    evidence_ref="events/raw/attempt.jsonl#spawned",
                )
                raise RuntimeError("fixture secret must not enter canonical evidence")

            recorder = EventRecorder(IncrementingClock())
            result = ControlledAttemptLoop(
                executor=execute,
                public_checker=lambda _number, _path: self.fail("checker must not run"),
                attempt_store=AttemptStore(Path(temporary) / "attempts"),
                recorder=recorder,
            ).run()
            self.assertEqual(result.chargeable_attempt_units, 1)
            self.assertEqual(result.attempts[0].failure.stage, "harness_execution")
            self.assertEqual(result.attempts[0].failure.error_type, "RuntimeError")
            self.assertNotIn("fixture secret", recorder.to_jsonl())

    def test_public_feedback_is_detached_from_checker_mutation(self) -> None:
        feedback = {"failed": ["one"]}
        result = PublicCheckResult(False, feedback, ("one",))
        feedback["failed"].append("two")
        self.assertEqual(result.feedback["failed"], ["one"])

    def test_invocation_admission_requires_spawn_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def execute(_number, _feedback, admission):
                with self.assertRaises(ExecutionError):
                    admission.admit(
                        process_spawned=True,
                        prompt_provided=False,
                        evidence_ref="raw#1",
                    )
                return HarnessAttemptResult(None, "prompt_failed")

            ControlledAttemptLoop(
                executor=execute,
                public_checker=lambda _number, _path: self.fail("checker must not run"),
                attempt_store=AttemptStore(Path(temporary) / "attempts"),
                recorder=EventRecorder(IncrementingClock()),
            ).run()

    def test_candidate_tree_hash_is_stable_and_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "b.txt").write_text("b")
            (candidate / "a.txt").write_text("a")
            self.assertEqual(candidate_tree_hash(candidate), candidate_tree_hash(candidate))
            try:
                (candidate / "link").symlink_to(candidate / "a.txt")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            with self.assertRaises(AttemptPreservationError):
                candidate_tree_hash(candidate)

    def test_candidate_tree_hash_has_unambiguous_file_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "a").write_bytes(b"bc")
            (first / "d").write_bytes(b"")
            (second / "a").write_bytes(b"b")
            (second / "d").write_bytes(b"c")
            self.assertNotEqual(candidate_tree_hash(first), candidate_tree_hash(second))


if __name__ == "__main__":
    unittest.main()
