import errno
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from RealLLM.run_voidtoken_v5_frozen import (  # noqa: E402
    FROZEN_CONFIGURATION,
    FROZEN_CONFIGURATION_SHA256,
    PHASES,
    PRETEST_TAG,
    PROTOCOL_SOURCE_FILES,
    SELECTION_PROTOCOL_TAG,
    _create_attempt_marker,
    _exclusive_write,
    _load_json_object,
    _require_clean_head,
    _require_public_pretest_freeze,
    _write_verified_result,
    attempt_schema_errors,
    compute_confidence_and_verdict,
    implementation_sha256,
    parse_arguments,
    phase_schema_errors,
    registration_sha256,
    run_phase,
    validate_frozen_registration,
    verify_phase_artifact_self_consistency,
)
import RealLLM.run_voidtoken_v5_frozen as frozen_runner  # noqa: E402
from RealLLM.benchmark_real_llm import RuntimeOptions  # noqa: E402


class FrozenVoidTokenV5ProtocolTests(unittest.TestCase):
    def _records(self, *, delta=0.001, mismatches=0):
        records = []
        base_mismatches, extra_blocks = divmod(mismatches, 32)
        self.assertLessEqual(base_mismatches + bool(extra_blocks), 128)
        for relative_index, block_index in enumerate(range(32, 64)):
            block_mismatches = base_mismatches + (
                1 if relative_index < extra_blocks else 0
            )
            agreement = 128 - block_mismatches
            records.append(
                {
                    "blockIndex": block_index,
                    "predictionTokens": 128,
                    "top1AgreementCount": agreement,
                    "deltaNLLNatPerToken": delta,
                }
            )
        return records

    def _baselines(self):
        return [
            {
                "exactRebuildMaxAbsLogitDifference": 0.0,
                "exactRebuildTop1Identical": True,
                "layoutRebuildMaxAbsLogitDifference": 0.0,
                "layoutRebuildTop1Identical": True,
            }
            for _ in range(32)
        ]

    def _aggregate(self, *, delta=0.001, mismatches=0):
        trials = 32 * 128
        return {
            "compressionRatioVsBF16": 2.05,
            "deltaNLLNatPerToken": delta,
            "top1Agreement": (trials - mismatches) / trials,
        }

    def test_registration_and_normative_manifest_are_self_consistent(self):
        validate_frozen_registration()
        self.assertEqual(len(registration_sha256()), 64)
        self.assertEqual(len(implementation_sha256()), 64)
        self.assertEqual(
            FROZEN_CONFIGURATION_SHA256,
            "4c7be8c836aa725722b51f66dce78af7a5094e887432e622b5322f7ca2cf0af8",
        )
        self.assertEqual(PRETEST_TAG, "voidtoken-v5-pretest-v1")
        self.assertEqual(
            SELECTION_PROTOCOL_TAG,
            "voidtoken-v5-selection-protocol-v1",
        )
        self.assertEqual(
            [index for index, bits in enumerate(
                FROZEN_CONFIGURATION["bitsByLayer"]
            ) if bits == 9],
            [0, 8],
        )
        registration = json.loads(
            (
                ROOT / "RealLLM" / "v5_registration.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            registration["protocolSourceFiles"],
            PROTOCOL_SOURCE_FILES,
        )

    def test_registered_phases_are_disjoint_and_reserve_is_inaccessible(self):
        selection = set(range(32, 64))
        holdout = set(range(384, 416))
        reserve = set(range(416, 448))
        historical = set(range(8, 16))
        self.assertEqual(PHASES["selection"]["startBlock"], 32)
        self.assertEqual(PHASES["holdout"]["startBlock"], 384)
        self.assertTrue(selection.isdisjoint(holdout))
        self.assertTrue(holdout.isdisjoint(reserve))
        self.assertTrue(holdout.isdisjoint(historical))
        self.assertNotIn("reserve", PHASES)
        with self.assertRaisesRegex(ValueError, "prospectively frozen"):
            RuntimeOptions(
                test_start_block=384,
                test_blocks=1,
            ).validate()
        with self.assertRaisesRegex(ValueError, "prospectively frozen"):
            RuntimeOptions(
                test_start_block=383,
                test_blocks=2,
            ).validate()
        RuntimeOptions(
            test_start_block=8,
            test_blocks=8,
        ).validate()

    def test_frozen_cli_has_no_source_or_configuration_overrides(self):
        parsed = parse_arguments(["selection", "--local-files-only"])
        self.assertEqual(parsed.phase, "selection")
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                parse_arguments(
                    ["selection", "--validation-start-block", "0"]
                )
            with self.assertRaises(SystemExit):
                parse_arguments(["holdout", "--candidate-index", "28"])
            with self.assertRaises(SystemExit):
                parse_arguments(["holdout", "--device", "cpu"])

    def test_phase_schema_is_fail_closed_and_nested_objects_are_strict(self):
        problems = phase_schema_errors({"phase": "selection"})
        self.assertTrue(problems)
        schema = json.loads(
            (
                ROOT
                / "schemas"
                / "voidtoken-v5-phase-result.schema.json"
            ).read_text(encoding="utf-8")
        )
        for name in ("baseline", "record", "aggregate"):
            self.assertFalse(schema["$defs"][name]["additionalProperties"])
        self.assertEqual(
            schema["$defs"]["record"]["properties"]["configurationId"],
            {"const": "4c7be8c836aa7257"},
        )

    def test_frozen_json_loader_rejects_duplicate_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            duplicate = Path(temporary) / "duplicate.json"
            duplicate.write_text('{"phase":"a","phase":"b"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                _load_json_object(duplicate)
            overflow = Path(temporary) / "overflow.json"
            overflow.write_text('{"value":1e999}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite JSON"):
                _load_json_object(overflow)

    def test_malformed_phase_records_return_errors_without_traceback(self):
        malformed = {
            "gitCommitAtExecution": "a" * 40,
            "records": ["not-an-object"],
            "baselines": [{}],
            "aggregate": {},
        }
        errors = verify_phase_artifact_self_consistency(
            malformed, "selection"
        )
        self.assertTrue(errors)
        self.assertIn(
            "every candidate record must be an object",
            errors,
        )

    def test_clean_worktree_guard_rejects_untracked_injection(self):
        def fake_git(*arguments):
            if arguments[0] == "status":
                return "?? sitecustomize.py"
            if arguments[:2] == ("rev-parse", "HEAD"):
                return "a" * 40
            self.fail(f"unexpected git call {arguments}")

        with patch.object(frozen_runner, "_git", side_effect=fake_git):
            with self.assertRaisesRegex(ValueError, "sitecustomize.py"):
                _require_clean_head()

    def test_invalid_selection_schema_stops_before_pretest_git_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            selection = Path(temporary) / "selection.json"
            selection.write_text('{"phase":"selection"}\n', encoding="utf-8")
            with (
                patch.object(frozen_runner, "SELECTION_PATH", selection),
                patch.object(
                    frozen_runner, "_require_clean_head"
                ) as clean_guard,
            ):
                with self.assertRaisesRegex(
                    ValueError, "selection artifact is invalid"
                ):
                    _require_public_pretest_freeze()
                clean_guard.assert_not_called()

    def test_confidence_gates_pass_a_strong_result(self):
        records = self._records(delta=0.001, mismatches=8)
        aggregate = self._aggregate(delta=0.001, mismatches=8)
        confidence, gates, passed = compute_confidence_and_verdict(
            records, self._baselines(), aggregate
        )
        self.assertTrue(passed)
        self.assertTrue(all(gates.values()))
        self.assertGreater(confidence["wilsonLowerOneSided95"], 0.99)

    def test_wilson_gate_can_fail_when_point_top1_passes(self):
        records = self._records(delta=0.001, mismatches=40)
        aggregate = self._aggregate(delta=0.001, mismatches=40)
        confidence, gates, passed = compute_confidence_and_verdict(
            records, self._baselines(), aggregate
        )
        self.assertGreaterEqual(aggregate["top1Agreement"], 0.99)
        self.assertLess(confidence["wilsonLowerOneSided95"], 0.99)
        self.assertTrue(gates["top1Agreement"])
        self.assertFalse(gates["wilsonLowerOneSided95"])
        self.assertFalse(passed)

    def test_wilson_gate_has_frozen_30_mismatch_boundary(self):
        records_30 = self._records(delta=0.001, mismatches=30)
        aggregate_30 = self._aggregate(delta=0.001, mismatches=30)
        confidence_30, gates_30, passed_30 = (
            compute_confidence_and_verdict(
                records_30, self._baselines(), aggregate_30
            )
        )
        self.assertGreaterEqual(
            confidence_30["wilsonLowerOneSided95"], 0.99
        )
        self.assertTrue(gates_30["wilsonLowerOneSided95"])
        self.assertTrue(passed_30)

        records_31 = self._records(delta=0.001, mismatches=31)
        aggregate_31 = self._aggregate(delta=0.001, mismatches=31)
        confidence_31, gates_31, passed_31 = (
            compute_confidence_and_verdict(
                records_31, self._baselines(), aggregate_31
            )
        )
        self.assertLess(confidence_31["wilsonLowerOneSided95"], 0.99)
        self.assertTrue(gates_31["top1Agreement"])
        self.assertFalse(gates_31["wilsonLowerOneSided95"])
        self.assertFalse(passed_31)

    def test_blockwise_upper_gate_can_fail_when_point_delta_passes(self):
        deltas = [0.02] * 16 + [-0.002] * 16
        records = self._records(delta=0.0)
        for record, delta in zip(records, deltas):
            record["deltaNLLNatPerToken"] = delta
        aggregate = self._aggregate(delta=sum(deltas) / len(deltas))
        confidence, gates, passed = compute_confidence_and_verdict(
            records, self._baselines(), aggregate
        )
        self.assertLessEqual(aggregate["deltaNLLNatPerToken"], 0.01)
        self.assertGreater(
            confidence["blockwiseDeltaNLLUpperOneSided95"], 0.01
        )
        self.assertTrue(gates["deltaNLLNatPerToken"])
        self.assertFalse(gates["blockwiseDeltaNLLUpperOneSided95"])
        self.assertFalse(passed)

    def test_blockwise_top1_gate_catches_clustered_errors(self):
        records = self._records(delta=0.001)
        records[0]["top1AgreementCount"] = 98
        aggregate = self._aggregate(delta=0.001, mismatches=30)
        confidence, gates, passed = compute_confidence_and_verdict(
            records, self._baselines(), aggregate
        )
        self.assertGreaterEqual(aggregate["top1Agreement"], 0.99)
        self.assertGreaterEqual(
            confidence["wilsonLowerOneSided95"], 0.99
        )
        self.assertLess(
            confidence["blockwiseTop1LowerOneSided95"], 0.99
        )
        self.assertFalse(gates["blockwiseTop1LowerOneSided95"])
        self.assertFalse(passed)

    def test_structural_replay_is_a_hard_gate(self):
        baselines = self._baselines()
        baselines[7]["layoutRebuildTop1Identical"] = False
        _, gates, passed = compute_confidence_and_verdict(
            self._records(),
            baselines,
            self._aggregate(),
        )
        self.assertFalse(gates["structuralReplay"])
        self.assertFalse(passed)

    def test_one_shot_runner_refuses_an_existing_output(self):
        original = PHASES["selection"]["output"]
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "selection.json"
            existing.write_text("do not overwrite", encoding="utf-8")
            PHASES["selection"]["output"] = existing
            try:
                with self.assertRaisesRegex(
                    ValueError, "refusing to overwrite"
                ):
                    run_phase("selection", local_files_only=True)
                self.assertEqual(
                    existing.read_text(encoding="utf-8"),
                    "do not overwrite",
                )
            finally:
                PHASES["selection"]["output"] = original

    def test_one_shot_runner_refuses_an_existing_attempt_marker(self):
        original_output = PHASES["selection"]["output"]
        original_attempt = PHASES["selection"]["attempt"]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "selection.json"
            attempt = Path(temporary) / "selection.attempt.json"
            attempt.write_text("consumed", encoding="utf-8")
            PHASES["selection"]["output"] = output
            PHASES["selection"]["attempt"] = attempt
            try:
                with (
                    patch.object(
                        frozen_runner,
                        "_resolve_model_and_split",
                    ) as resolver,
                    self.assertRaisesRegex(ValueError, "already consumed"),
                ):
                    run_phase("selection", local_files_only=True)
                resolver.assert_not_called()
                self.assertFalse(output.exists())
            finally:
                PHASES["selection"]["output"] = original_output
                PHASES["selection"]["attempt"] = original_attempt

    def test_attempt_marker_is_durable_before_resolver_and_crash_consumes(self):
        original_output = PHASES["selection"]["output"]
        original_attempt = PHASES["selection"]["attempt"]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "selection.json"
            attempt = Path(temporary) / "selection.attempt.json"
            PHASES["selection"]["output"] = output
            PHASES["selection"]["attempt"] = attempt

            def crash_after_marker(*_arguments, **_keywords):
                self.assertTrue(attempt.is_file())
                marker = json.loads(attempt.read_text(encoding="utf-8"))
                self.assertEqual(
                    marker["status"],
                    "attempt-started-split-not-yet-resolved",
                )
                self.assertFalse(attempt_schema_errors(marker))
                raise RuntimeError("simulated resolver crash")

            registration_digest = registration_sha256()
            implementation_digest = implementation_sha256()
            try:
                with (
                    patch.object(
                        frozen_runner,
                        "_require_bootstrap_attestation",
                        return_value={
                            "phase": "selection",
                            "gitCommit": "a" * 40,
                            "gitTag": SELECTION_PROTOCOL_TAG,
                        },
                    ),
                    patch.object(
                        frozen_runner, "_require_isolated_python"
                    ),
                    patch.object(
                        frozen_runner,
                        "_require_clean_head",
                        return_value="a" * 40,
                    ),
                    patch.object(
                        frozen_runner,
                        "registration_sha256_at_commit",
                        return_value=registration_digest,
                    ),
                    patch.object(
                        frozen_runner,
                        "implementation_sha256_at_commit",
                        return_value=implementation_digest,
                    ),
                    patch.object(
                        frozen_runner,
                        "_require_public_selection_freeze",
                        return_value={
                            "freezeGitCommit": "a" * 40,
                            "freezeGitTag": SELECTION_PROTOCOL_TAG,
                            "publicRepository": frozen_runner.PUBLIC_ORIGIN,
                        },
                    ),
                    patch.object(
                        frozen_runner,
                        "_validate_runtime_versions",
                    ),
                    patch.object(
                        frozen_runner,
                        "_resolve_device",
                        return_value="mps",
                    ),
                    patch.object(
                        frozen_runner,
                        "_resolve_model_and_split",
                        side_effect=crash_after_marker,
                    ) as resolver,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "simulated resolver crash"
                    ):
                        run_phase("selection", local_files_only=True)
                resolver.assert_called_once()
                self.assertTrue(attempt.is_file())
                self.assertFalse(output.exists())
                with self.assertRaisesRegex(ValueError, "already consumed"):
                    run_phase("selection", local_files_only=True)
            finally:
                PHASES["selection"]["output"] = original_output
                PHASES["selection"]["attempt"] = original_attempt

    def test_exclusive_attempt_creation_rejects_second_writer(self):
        original_attempt = PHASES["selection"]["attempt"]
        with tempfile.TemporaryDirectory() as temporary:
            attempt = Path(temporary) / "selection.attempt.json"
            PHASES["selection"]["attempt"] = attempt
            freeze = {
                "freezeGitCommit": "a" * 40,
                "freezeGitTag": SELECTION_PROTOCOL_TAG,
                "publicRepository": frozen_runner.PUBLIC_ORIGIN,
            }
            try:
                _create_attempt_marker(
                    "selection",
                    git_commit="a" * 40,
                    registration_digest="b" * 64,
                    implementation_digest="c" * 64,
                    execution_freeze=freeze,
                )
                with self.assertRaises(FileExistsError):
                    _create_attempt_marker(
                        "selection",
                        git_commit="a" * 40,
                        registration_digest="b" * 64,
                        implementation_digest="c" * 64,
                        execution_freeze=freeze,
                    )
            finally:
                PHASES["selection"]["attempt"] = original_attempt

    def test_directory_fsync_io_error_is_not_silenced(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "durable.json"
            with patch.object(
                frozen_runner.os,
                "open",
                side_effect=OSError(errno.EIO, "simulated directory I/O"),
            ):
                with self.assertRaises(OSError):
                    _exclusive_write(target, b"{}\n")
            self.assertTrue(target.is_file())

    def test_marker_change_during_result_verification_blocks_write(self):
        original_output = PHASES["selection"]["output"]
        original_attempt = PHASES["selection"]["attempt"]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "selection.json"
            attempt = Path(temporary) / "selection.attempt.json"
            PHASES["selection"]["output"] = output
            PHASES["selection"]["attempt"] = attempt
            registration_digest = registration_sha256()
            implementation_digest = implementation_sha256()
            marker, artifact_digest = _create_attempt_marker(
                "selection",
                git_commit="a" * 40,
                registration_digest=registration_digest,
                implementation_digest=implementation_digest,
                execution_freeze={
                    "freezeGitCommit": "a" * 40,
                    "freezeGitTag": SELECTION_PROTOCOL_TAG,
                    "publicRepository": frozen_runner.PUBLIC_ORIGIN,
                },
            )

            def mutate_marker(*_arguments):
                attempt.write_text('{"tampered":true}\n', encoding="utf-8")
                return []

            try:
                with (
                    patch.object(
                        frozen_runner,
                        "verify_phase_result",
                        side_effect=mutate_marker,
                    ),
                    patch.object(
                        frozen_runner,
                        "_require_clean_head",
                        return_value="a" * 40,
                    ),
                    patch.object(
                        frozen_runner,
                        "registration_sha256_at_commit",
                        return_value=registration_digest,
                    ),
                    patch.object(
                        frozen_runner,
                        "implementation_sha256_at_commit",
                        return_value=implementation_digest,
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "attempt marker changed"
                    ):
                        _write_verified_result(
                            "selection",
                            {"resultSHA256": "0" * 64},
                            git_commit="a" * 40,
                            registration_digest=registration_digest,
                            implementation_digest=implementation_digest,
                            attempt_marker=marker,
                            attempt_artifact_digest=artifact_digest,
                        )
                self.assertFalse(output.exists())
            finally:
                PHASES["selection"]["output"] = original_output
                PHASES["selection"]["attempt"] = original_attempt

    def test_holdout_guard_fails_before_test_resolver(self):
        original_output = PHASES["holdout"]["output"]
        original_attempt = PHASES["holdout"]["attempt"]
        with tempfile.TemporaryDirectory() as temporary:
            PHASES["holdout"]["output"] = (
                Path(temporary) / "holdout.json"
            )
            PHASES["holdout"]["attempt"] = (
                Path(temporary) / "holdout.attempt.json"
            )
            try:
                with (
                    patch.object(
                        frozen_runner,
                        "validate_frozen_registration",
                    ),
                    patch.object(
                        frozen_runner, "_require_isolated_python"
                    ),
                    patch.object(
                        frozen_runner,
                        "_require_bootstrap_attestation",
                        return_value={
                            "phase": "holdout",
                            "gitCommit": "a" * 40,
                            "gitTag": PRETEST_TAG,
                        },
                    ),
                    patch.object(
                        frozen_runner,
                        "_require_clean_head",
                        return_value="a" * 40,
                    ),
                    patch.object(
                        frozen_runner,
                        "registration_sha256_at_commit",
                        return_value=registration_sha256(),
                    ),
                    patch.object(
                        frozen_runner,
                        "implementation_sha256_at_commit",
                        return_value=implementation_sha256(),
                    ),
                    patch.object(
                        frozen_runner,
                        "_require_public_pretest_freeze",
                        side_effect=ValueError("pretest freeze missing"),
                    ),
                    patch.object(
                        frozen_runner,
                        "_resolve_model_and_split",
                    ) as resolver,
                ):
                    with self.assertRaisesRegex(
                        ValueError, "pretest freeze missing"
                    ):
                        run_phase("holdout", local_files_only=True)
                    resolver.assert_not_called()
            finally:
                PHASES["holdout"]["output"] = original_output
                PHASES["holdout"]["attempt"] = original_attempt


if __name__ == "__main__":
    unittest.main()
