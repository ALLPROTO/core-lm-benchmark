import copy
import hashlib
import tempfile
import unittest
from pathlib import Path


from security import automated_media
from security import verify_portfolio_tag_ci as tag_ci


class AutomatedMediaContractTests(unittest.TestCase):
    def _ffprobe_frames(self):
        return [
            {
                "best_effort_timestamp_time": "0.000000",
                "duration_time": "0.016667",
                "width": 2400,
                "height": 1540,
                "side_data_list": [
                    {
                        "side_data_type": (
                            "H.26[45] User Data Unregistered SEI message"
                        )
                    }
                ],
            },
            {
                "best_effort_timestamp_time": "0.016667",
                "duration_time": "0.016667",
                "width": 2400,
                "height": 1540,
            },
            {
                "best_effort_timestamp_time": "0.050000",
                "duration_time": "0.033333",
                "width": 2400,
                "height": 1540,
            },
        ]

    def test_ffprobe_n812_frame_pts_projection_is_exact_and_side_data_neutral(self):
        frames = self._ffprobe_frames()
        self.assertEqual(
            automated_media.frame_pts_identity(frames, width=2400, height=1540),
            (
                3,
                "f05b183e0a5212fbb531913fe939231d0246425d45269f687e4ea6ca8a07e57b",
            ),
        )
        without_sei = copy.deepcopy(frames)
        without_sei[0].pop("side_data_list")
        self.assertEqual(
            automated_media.frame_pts_identity(without_sei, width=2400, height=1540),
            automated_media.frame_pts_identity(frames, width=2400, height=1540),
        )

    def test_frame_pts_projection_rejects_legacy_fields_and_nonexact_topology(self):
        frames = self._ffprobe_frames()
        legacy = copy.deepcopy(frames)
        legacy[0]["pkt_duration_time"] = legacy[0].pop("duration_time")
        extra = copy.deepcopy(frames)
        extra[1]["unexpected"] = True
        malformed_sei = copy.deepcopy(frames)
        malformed_sei[0]["side_data_list"] = [
            {"side_data_type": "H.264 User Data Unregistered SEI message"}
        ]
        zero_duration = copy.deepcopy(frames)
        zero_duration[1]["duration_time"] = "0.000000"
        nonmonotonic = copy.deepcopy(frames)
        nonmonotonic[2]["best_effort_timestamp_time"] = "0.016667"
        wrong_dimensions = copy.deepcopy(frames)
        wrong_dimensions[2]["width"] = 2399
        numeric_timestamp = copy.deepcopy(frames)
        numeric_timestamp[0]["best_effort_timestamp_time"] = 0.0
        for invalid in (
            legacy,
            extra,
            malformed_sei,
            zero_duration,
            nonmonotonic,
            wrong_dimensions,
            numeric_timestamp,
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                automated_media.AutomatedMediaError
            ):
                automated_media.frame_pts_identity(invalid, width=2400, height=1540)

    def _segment(self, role, owner_pid, window_id, duration, digest):
        return {
            "role": role,
            "owner_pid": owner_pid,
            "window_id": window_id,
            "width": 1280,
            "height": 720,
            "requested_duration_seconds": duration,
            "duration_seconds": duration,
            "frame_count": max(1, int(duration * 30)),
            "pts_sha256": digest,
            "sha256": digest,
        }

    def _readiness(self):
        return {
            "schema_version": 1,
            "status": "CAPTURE_RESULT_READY",
            "run_identifier": "12345678-1234-4234-8234-123456789abc",
            "receipt_sha256": "4" * 64,
            "result_sha256": "5" * 64,
            "application_executable_sha256": "6" * 64,
            "metric_verdict": "FAIL",
            "compression_ratio_vs_bf16": "2.000000",
            "delta_nll_nat_per_token": "0.001000",
            "top1_agreement": "0.999000",
            "module_states": {
                "qwen_model": "COMPLETE",
                "kv_cache": "COMPLETE",
                "compression": "COMPLETE",
                "primary_evidence": "COMPLETE",
                "heavy_replay": "PASS",
            },
            "verifier_state": "PASS",
        }

    def _report(self):
        return {
            "schema_version": automated_media.SCHEMA_VERSION,
            "report_kind": automated_media.REPORT_KIND,
            "verdict": automated_media.VERDICT,
            "automation_contract": automated_media.AUTOMATION_CONTRACT,
            "classification": automated_media.MEDIA_CLASSIFICATION,
            "automation_only": True,
            "human_reviewed": False,
            "manual_edits": False,
            "machine_evidence": False,
            "pixel_semantics_verified": False,
            "source": {
                "tag": "corelm-portfolio-v11",
                "commit": "1" * 40,
                "tree": "2" * 40,
            },
            "run": {
                "identifier": "12345678-1234-4234-8234-123456789abc",
                "challenge_sha256": "3" * 64,
                "receipt_sha256": "4" * 64,
                "result_sha256": "5" * 64,
                "application_executable_sha256": "6" * 64,
                "metric_verdict": "FAIL",
                "terminal_outcome": "END-TO-END PROOF VERIFIED — METRIC FAIL",
                "structural_verdict": "PASS",
                "replay_verdict": automated_media.REPLAY_VERDICT,
                "workload_classification": automated_media.WORKLOAD_CLASSIFICATION,
                "synthetic_data": False,
            },
            "capture": {
                "mode": automated_media.CAPTURE_MODE,
                "bundle_identifier": automated_media.BUNDLE_IDENTIFIER,
                "result_readiness_sha256": "f" * 64,
                "preflight_segment": self._segment(
                    "preflight", 99, 199, automated_media.PREFLIGHT_SEGMENT_SECONDS, "6" * 64
                ),
                "segments": [
                    self._segment(
                        "post_proof_presentation", 100, 200,
                        automated_media.POST_PROOF_PRESENTATION_SEGMENT_SECONDS,
                        "7" * 64,
                    ),
                    self._segment(
                        "same_run_result", 101, 201,
                        automated_media.RESULT_SEGMENT_SECONDS, "8" * 64,
                    ),
                ],
            },
            "tools": {
                "window_helper": {
                    "source_sha256": "9" * 64,
                    "executable_sha256": "a" * 64,
                    "swift_version": "Apple Swift version 6.3.3 fixture",
                },
                "screencapture": {
                    "executable_sha256": "b" * 64,
                    "codesign_identifier": "com.apple.screencapture",
                },
                "ffmpeg": {
                    "executable_sha256": "c" * 64,
                    "version": "ffmpeg version 8.1.2 fixture",
                },
                "ffprobe": {
                    "executable_sha256": "d" * 64,
                    "version": "ffprobe version 8.1.2 fixture",
                },
            },
            "output": {
                "video_sha256": "e" * 64,
                "poster_sha256": "f" * 64,
                "poster_frame_timestamp_seconds": automated_media.POSTER_TIMESTAMP_SECONDS,
                "duration_seconds": 30.0,
                "width": 1280,
                "height": 720,
                "frame_count": 900,
                "pts_sha256": "0" * 64,
                "decoded_frames_sha256": "1" * 64,
            },
            "privacy": {
                "input_surface": "ALLOWLISTED_APP_VIEW_ONLY",
                "byte_and_metadata_scan": "PASS",
                "ocr_role": "NOT_RUN_NOT_A_COMPLETENESS_PROOF",
                "verdict": "NO_CONFIGURED_PATTERN_DETECTED",
                "semantic_pixel_privacy": "NOT_CLAIMED",
            },
            "attempt": {
                "proof_invocation_count": 1,
                "event_count": automated_media.ATTEMPT_EVENT_COUNT,
                "scope": automated_media.ATTEMPT_SCOPE,
                "state_log_sha256": "2" * 64,
                "tag_ci_receipt_sha256": "3" * 64,
                "local_tag_trust_receipt_sha256": "4" * 64,
            },
        }

    def _attempt_state(self, report):
        preflight = report["capture"]["preflight_segment"]
        presentation, result = report["capture"]["segments"]
        common = {
            "schema_version": automated_media.ATTEMPT_STATE_SCHEMA_VERSION,
            "tag": report["source"]["tag"],
        }
        events = [
            {**common, "event": "ATTEMPT_STARTED", "proof_invocation_count": 0,
             "source_commit": report["source"]["commit"], "source_tree": report["source"]["tree"],
             "preflight_segment_sha256": preflight["sha256"],
             "preflight_owner_pid": preflight["owner_pid"], "preflight_window_id": preflight["window_id"],
             "window_helper_sha256": report["tools"]["window_helper"]["executable_sha256"],
             "tag_ci_receipt_sha256": report["attempt"]["tag_ci_receipt_sha256"],
             "local_tag_trust_receipt_sha256": report["attempt"]["local_tag_trust_receipt_sha256"]},
            {**common, "event": "PROOF_INVOKED", "proof_invocation_count": 1,
             "challenge_sha256": report["run"]["challenge_sha256"]},
            {**common, "event": "PROOF_TERMINAL", "proof_invocation_count": 1,
             "metric_verdict": report["run"]["metric_verdict"],
             "run_identifier": report["run"]["identifier"],
             "terminal_outcome": report["run"]["terminal_outcome"]},
            {**common, "event": "REPLAY_VERIFIED", "proof_invocation_count": 1,
             "replay_verdict": report["run"]["replay_verdict"],
             "run_identifier": report["run"]["identifier"]},
            {**common, "event": "POST_PROOF_PRESENTATION_SURFACE_READY",
             "proof_invocation_count": 1,
             "executable_sha256": report["run"]["application_executable_sha256"],
             "owner_pid": presentation["owner_pid"], "window_id": presentation["window_id"]},
            {**common, "event": "POST_PROOF_PRESENTATION_CAPTURED", "proof_invocation_count": 1,
             "segment_sha256": presentation["sha256"], "window_id": presentation["window_id"]},
            {**common, "event": "SAME_RUN_REOPENED", "proof_invocation_count": 1,
             "result_readiness_sha256": report["capture"]["result_readiness_sha256"],
             "run_identifier": report["run"]["identifier"], "window_id": result["window_id"]},
            {**common, "event": "RESULT_CAPTURED", "proof_invocation_count": 1,
             "segment_sha256": result["sha256"], "window_id": result["window_id"]},
            {**common, "event": "MEDIA_SEALED_FOR_COLLECTION", "proof_invocation_count": 1,
             "poster_sha256": report["output"]["poster_sha256"],
             "video_sha256": report["output"]["video_sha256"]},
        ]
        return b"".join(automated_media.canonical_json_bytes(event) for event in events)

    def _tag_ci_receipt(self):
        tag = "corelm-portfolio-v11"
        commit = "1" * 40
        tree = "2" * 40
        workflows = []
        for name, path, run_id, jobs in (
            (
                "Verify Linux",
                ".github/workflows/verify-linux.yml",
                31_320_957_015,
                (
                    ("python-and-publication", 93_257_094_239),
                    ("supply-chain", 93_257_094_240),
                ),
            ),
            (
                "Verify macOS",
                ".github/workflows/verify-macos.yml",
                31_320_957_016,
                (("native-application", 93_257_094_241),),
            ),
        ):
            workflows.append({
                "workflow_name": name, "workflow_path": path, "run_id": run_id,
                "run_attempt": 1, "event": "push", "head_branch": tag,
                "head_sha": commit, "status": "completed", "conclusion": "success",
                "api_url": f"https://api.github.com/repos/ALLPROTO/core-lm-benchmark/actions/runs/{run_id}",
                "html_url": f"https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/{run_id}",
                "jobs": [{"job_id": job_id, "name": job_name,
                          "step_count": 1, "tag_ref_assertion": "PASS",
                          "status": "completed", "conclusion": "success"}
                         for job_name, job_id in jobs],
            })
        return {
            "schema_version": 1,
            "artifact_kind": "corelm_portfolio_tag_ci_admission_receipt",
            "status": "PASS",
            "admission_boundary": "PUBLIC_ANNOTATED_TAG_AND_FIRST_ATTEMPT_TAG_PUSH_CI",
            "automation_only": True,
            "human_reviewed": False,
            "source": {"repository": "ALLPROTO/core-lm-benchmark", "tag": tag,
                       "tag_ref": f"refs/tags/{tag}", "annotated_tag_object": "0" * 40,
                       "commit": commit, "tree": tree, "main_ref": "refs/heads/main",
                       "tag_github_verification": "VERIFIED_VALID",
                       "commit_github_verification": "VERIFIED_VALID"},
            "network_contract": {"api_origin": "https://api.github.com",
                                 "authentication_sent_by_fetcher": False,
                                 "redirects": "FORBIDDEN", "response_limit_bytes": 4 * 1024 * 1024,
                                 "timeout_max_seconds": 30.0, "offline_validation": True},
            "responses": [{"role": role,
                           "url": f"https://api.github.com/repos/ALLPROTO/core-lm-benchmark/{role}",
                           "sha256": f"{index:x}" * 64, "size_bytes": 1}
                          for index, role in enumerate(tag_ci.RESPONSE_ROLES, start=1)],
            "workflows": workflows,
        }

    def test_exact_report_and_external_bindings_pass(self):
        report = self._report()
        self.assertEqual(automated_media.SCHEMA_VERSION, 2)
        self.assertEqual(automated_media.ATTEMPT_STATE_SCHEMA_VERSION, 2)
        self.assertEqual(
            automated_media.REPORT_KIND,
            "corelm_automated_portfolio_media_v2",
        )
        self.assertEqual(
            automated_media.AUTOMATION_CONTRACT,
            "corelm-automated-presentation-v2",
        )
        observed = automated_media.validate_report(
            report,
            expected={
                "tag": report["source"]["tag"],
                "commit": report["source"]["commit"],
                "tree": report["source"]["tree"],
                "run_identifier": report["run"]["identifier"],
                "challenge_sha256": report["run"]["challenge_sha256"],
                "receipt_sha256": report["run"]["receipt_sha256"],
                "result_sha256": report["run"]["result_sha256"],
                "application_executable_sha256": report["run"][
                    "application_executable_sha256"
                ],
                "metric_verdict": "FAIL",
                "video_sha256": report["output"]["video_sha256"],
                "poster_sha256": report["output"]["poster_sha256"],
            },
        )
        self.assertIs(observed, report)

    def test_v1_report_role_and_attempt_grammar_are_rejected(self):
        for path, value in (
            (("schema_version",), 1),
            (("report_kind",), "corelm_automated_portfolio_media_v1"),
            (("automation_contract",), "corelm-automated-presentation-v1"),
            (("capture", "segments", 0, "role"), "live_presentation"),
        ):
            report = copy.deepcopy(self._report())
            target = report
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(
                automated_media.AutomatedMediaError
            ):
                automated_media.validate_report(report)

        state = self._attempt_state(self._report()).replace(
            b'"event":"POST_PROOF_PRESENTATION_SURFACE_READY"',
            b'"event":"LIVE_SURFACE_READY"',
            1,
        )
        with self.assertRaises(automated_media.AutomatedMediaError):
            automated_media.validate_attempt_state_bytes(state)

    def test_downgrade_human_claim_manual_edit_and_second_proof_fail(self):
        for path, value in (
            (("classification",), "HUMAN_REVIEWED_PRESENTATION_NOT_MACHINE_EVIDENCE"),
            (("human_reviewed",), True),
            (("manual_edits",), True),
            (("machine_evidence",), True),
            (("attempt", "proof_invocation_count"), 2),
        ):
            report = copy.deepcopy(self._report())
            target = report
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(
                automated_media.AutomatedMediaError
            ):
                automated_media.validate_report(report)

    def test_cross_run_window_mode_and_media_swaps_fail(self):
        mutations = (
            ("source", "tag", "corelm-portfolio-v2"),
            ("run", "identifier", "not-a-uuid"),
            ("run", "terminal_outcome", "END-TO-END PROOF PASS"),
            ("capture", "mode", "FULL_SCREEN"),
            ("capture", "bundle_identifier", "com.apple.Terminal"),
            ("privacy", "semantic_pixel_privacy", "PROVEN_SAFE"),
        )
        for group, key, value in mutations:
            report = copy.deepcopy(self._report())
            report[group][key] = value
            with self.subTest(group=group, key=key), self.assertRaises(
                automated_media.AutomatedMediaError
            ):
                automated_media.validate_report(report)

    def test_fixed_media_topology_and_readiness_are_exact(self):
        for key, value in (
            ("duration_seconds", 45.0),
            ("width", 1),
            ("height", 1),
            ("frame_count", 1),
        ):
            report = copy.deepcopy(self._report())
            report["output"][key] = value
            with self.subTest(key=key), self.assertRaises(
                automated_media.AutomatedMediaError
            ):
                automated_media.validate_report(report)

        readiness = self._readiness()
        self.assertIs(automated_media.validate_readiness(readiness), readiness)
        for path, value in (
            (("status",), "CAPTURE_RESULT_LOADING"),
            (("run_identifier",), "not-a-uuid"),
            (("compression_ratio_vs_bf16",), "2.0"),
            (("module_states", "heavy_replay"), "NOT_RETAINED"),
        ):
            tampered = copy.deepcopy(readiness)
            target = tampered
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(
                automated_media.AutomatedMediaError
            ):
                automated_media.validate_readiness(tampered)
        report = self._report()
        with self.assertRaisesRegex(
            automated_media.AutomatedMediaError, "differs from video_sha256"
        ):
            automated_media.validate_report(
                report, expected={"video_sha256": "9" * 64}
            )

    def test_canonical_writer_is_nonoverwriting_and_reader_rejects_unknown_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            path = root / "automation.json"
            report = self._report()
            automated_media.write_report(path, report)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(automated_media.read_canonical_report(path), report)
            with self.assertRaisesRegex(
                automated_media.AutomatedMediaError, "absent absolute"
            ):
                automated_media.write_report(path, report)
            tampered = copy.deepcopy(report)
            tampered["unexpected"] = True
            path.write_bytes(automated_media.canonical_json_bytes(tampered))
            with self.assertRaisesRegex(
                automated_media.AutomatedMediaError, "fields are not exact"
            ):
                automated_media.validate_report(
                    automated_media.read_canonical_report(path)
                )

    def test_exact_nine_event_state_is_report_bound_and_tamper_fails(self):
        report = self._report()
        state = self._attempt_state(report)
        report["attempt"]["state_log_sha256"] = hashlib.sha256(state).hexdigest()
        self.assertEqual(
            len(automated_media.validate_attempt_state_bytes(state, report=report)), 9
        )
        for tampered in (
            state.replace(
                b'"event":"POST_PROOF_PRESENTATION_CAPTURED"',
                b'"event":"RESULT_CAPTURED"',
                1,
            ),
            state.replace(("7" * 64).encode(), ("8" * 64).encode(), 1),
            state + automated_media.canonical_json_bytes({"event": "EXTRA"}),
        ):
            with self.assertRaises(automated_media.AutomatedMediaError):
                automated_media.validate_attempt_state_bytes(tampered, report=report)
        wrong_tag_state = state.replace(
            b'"tag":"corelm-portfolio-v11"',
            b'"tag":"corelm-portfolio-v12"',
        )
        wrong_tag_report = copy.deepcopy(report)
        wrong_tag_report["attempt"]["state_log_sha256"] = hashlib.sha256(
            wrong_tag_state
        ).hexdigest()
        with self.assertRaisesRegex(
            automated_media.AutomatedMediaError,
            "differ from automation report",
        ):
            automated_media.validate_attempt_state_bytes(
                wrong_tag_state,
                report=wrong_tag_report,
            )

    def test_tag_ci_receipt_is_canonical_source_bound_and_tamper_fails(self):
        receipt = self._tag_ci_receipt()
        payload = tag_ci.canonical_receipt_bytes(receipt)
        self.assertEqual(
            automated_media.validate_tag_ci_receipt_bytes(
                payload,
                expected={"repository": "ALLPROTO/core-lm-benchmark",
                          "tag": "corelm-portfolio-v11", "commit": "1" * 40,
                          "tree": "2" * 40},
            ),
            receipt,
        )
        tampered = copy.deepcopy(receipt)
        tampered["workflows"][0]["conclusion"] = "failure"
        with self.assertRaises(automated_media.AutomatedMediaError):
            automated_media.validate_tag_ci_receipt_bytes(
                tag_ci.canonical_receipt_bytes(tampered)
            )
        with self.assertRaises(automated_media.AutomatedMediaError):
            automated_media.validate_tag_ci_receipt_bytes(payload[:-1] + b" \n")

    def test_tag_ci_receipt_accepts_realistic_and_maximum_github_ids(self):
        receipt = self._tag_ci_receipt()
        self.assertGreater(receipt["workflows"][0]["run_id"], 2**31 - 1)
        self.assertGreater(receipt["workflows"][0]["jobs"][0]["job_id"], 2**31 - 1)
        self.assertEqual(
            automated_media.validate_tag_ci_receipt_bytes(
                tag_ci.canonical_receipt_bytes(receipt)
            ),
            receipt,
        )

        boundary = copy.deepcopy(receipt)
        boundary["workflows"][0]["run_id"] = automated_media.MAX_GITHUB_ID
        boundary["workflows"][0]["api_url"] = (
            "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/actions/runs/"
            f"{automated_media.MAX_GITHUB_ID}"
        )
        boundary["workflows"][0]["html_url"] = (
            "https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/"
            f"{automated_media.MAX_GITHUB_ID}"
        )
        boundary["workflows"][0]["jobs"][0]["job_id"] = (
            automated_media.MAX_GITHUB_ID
        )
        self.assertEqual(
            automated_media.validate_tag_ci_receipt_bytes(
                tag_ci.canonical_receipt_bytes(boundary)
            ),
            boundary,
        )

    def test_tag_ci_github_id_mutations_fail_closed_at_64_bit_boundary(self):
        for path in (
            ("workflows", 0, "run_id"),
            ("workflows", 0, "jobs", 0, "job_id"),
        ):
            for invalid in (0, True, automated_media.MAX_GITHUB_ID + 1):
                receipt = copy.deepcopy(self._tag_ci_receipt())
                target = receipt
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = invalid
                with self.subTest(path=path, invalid=invalid), self.assertRaisesRegex(
                    automated_media.AutomatedMediaError,
                    "bounded positive integer",
                ):
                    automated_media.validate_tag_ci_receipt_bytes(
                        tag_ci.canonical_receipt_bytes(receipt)
                    )

    def test_tag_ci_step_count_keeps_existing_31_bit_bound(self):
        boundary = self._tag_ci_receipt()
        boundary["workflows"][0]["jobs"][0]["step_count"] = 2**31 - 1
        self.assertEqual(
            automated_media.validate_tag_ci_receipt_bytes(
                tag_ci.canonical_receipt_bytes(boundary)
            ),
            boundary,
        )

        for invalid in (0, True, 2**31):
            receipt = copy.deepcopy(self._tag_ci_receipt())
            receipt["workflows"][0]["jobs"][0]["step_count"] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                automated_media.AutomatedMediaError,
                "bounded positive integer",
            ):
                automated_media.validate_tag_ci_receipt_bytes(
                    tag_ci.canonical_receipt_bytes(receipt)
                )


if __name__ == "__main__":
    unittest.main()
