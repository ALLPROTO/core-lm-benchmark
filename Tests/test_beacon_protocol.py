from __future__ import annotations

import copy
import contextlib
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from RealLLM import beacon_protocol
from RealLLM.beacon_protocol import (
    LEDGER_PATH,
    REGISTRATION_PATH,
    durable_exclusive_write,
    load_ledger,
    map_candidate_from_digest_sequence,
    select_window,
    serialized_json_bytes,
    validate_registration_and_ledger,
    verify_nist_pulse,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PULSE = (
    PROJECT_ROOT
    / "Tests"
    / "fixtures"
    / "nist-beacon-chain-2-pulse-1884240.json"
)
FIXTURE_CERTIFICATE = (
    PROJECT_ROOT
    / "Tests"
    / "fixtures"
    / "nist-beacon-certificate-528943a5.pem"
)


class BeaconProtocolTests(unittest.TestCase):
    def _fixture(self):
        pulse = json.loads(FIXTURE_PULSE.read_text(encoding="utf-8"))["pulse"]
        certificate = FIXTURE_CERTIFICATE.read_bytes()
        return pulse, certificate

    def _failure_artifacts(self, *, with_resolution: bool):
        from RealLLM import verify_beacon_evidence as verifier

        registration_digest = "1" * 64
        canonical_digest = "2" * 64
        ledger_digest = "3" * 64
        implementation_digest = "4" * 64
        execution_commit = "a" * 40
        protocol_commit = "b" * 40
        freeze = {
            "schemaVersion": "corelm-beacon-freeze-v1",
            "suiteId": beacon_protocol.SUITE_ID,
            "status": "protocol-files-frozen-before-beacon",
            "preparedAt": "2026-08-01T00:00:00Z",
            "protocolCommit": protocol_commit,
            "registrationArtifactSHA256": registration_digest,
            "registrationCanonicalSHA256": canonical_digest,
            "windowLedgerSHA256": ledger_digest,
            "implementationSHA256": implementation_digest,
            "normativeFiles": [],
        }
        attempt = {
            "schemaVersion": "corelm-beacon-attempt-v1",
            "suiteId": beacon_protocol.SUITE_ID,
            "status": "attempt-started-beacon-and-data-not-yet-resolved",
            "startedAt": "2026-08-02T18:00:00Z",
            "gitCommitAtExecution": execution_commit,
            "gitTagAtExecution": beacon_protocol.FREEZE_TAG,
            "protocolCommit": protocol_commit,
            "publicFreezeRelease": {
                "apiURL": beacon_protocol.PUBLIC_RELEASE_API,
                "htmlURL": beacon_protocol.PUBLIC_RELEASE_URL,
                "immutable": True,
                "publishedAt": "2026-08-01T12:00:00Z",
            },
            "registrationArtifactSHA256": registration_digest,
            "registrationCanonicalSHA256": canonical_digest,
            "windowLedgerSHA256": ledger_digest,
            "implementationSHA256": implementation_digest,
            "beaconTargetTimestamp": beacon_protocol.TARGET_TIMESTAMP,
            "beaconEndpoint": beacon_protocol.PULSE_URL,
            "beaconWillBeFetchedAfterMarker": True,
            "testSplitWillBeResolvedAfterBeacon": True,
            "rerunPermitted": False,
        }
        attempt["attemptSHA256"] = beacon_protocol.artifact_digest_without_field(
            attempt, "attemptSHA256"
        )

        resolution = None
        if with_resolution:
            pulse_index = 2_000_000
            list_types = ("previous", "hour", "day", "month", "year")
            pulse = {
                "uri": (
                    "https://beacon.nist.gov/beacon/2.0/chain/2/pulse/"
                    f"{pulse_index}"
                ),
                "version": "2.0",
                "cipherSuite": 0,
                "period": 60_000,
                "certificateId": beacon_protocol.EXPECTED_CERTIFICATE_ID,
                "chainIndex": 2,
                "pulseIndex": pulse_index,
                "timeStamp": beacon_protocol.TARGET_TIMESTAMP,
                "localRandomValue": "A" * 128,
                "external": {
                    "sourceId": "B" * 128,
                    "statusCode": 0,
                    "value": "C" * 128,
                },
                "listValues": [
                    {
                        "uri": (
                            "https://beacon.nist.gov/beacon/2.0/chain/2/pulse/"
                            f"{pulse_index - offset - 1}"
                        ),
                        "type": kind,
                        "value": f"{offset + 1:X}" * 128,
                    }
                    for offset, kind in enumerate(list_types)
                ],
                "precommitmentValue": "D" * 128,
                "statusCode": 0,
                "signatureValue": "AA",
                "outputValue": "E" * 128,
            }
            resolution = {
                "schemaVersion": "corelm-beacon-resolution-v1",
                "suiteId": beacon_protocol.SUITE_ID,
                "status": "beacon-resolved-before-model-data",
                "resolvedAt": "2026-08-02T18:00:01Z",
                "attemptSHA256": attempt["attemptSHA256"],
                "registrationArtifactSHA256": registration_digest,
                "windowLedgerSHA256": ledger_digest,
                "pulseEndpoint": beacon_protocol.PULSE_URL,
                "pulse": pulse,
                "certificatePEMBase64": base64.b64encode(b"x" * 64).decode(
                    "ascii"
                ),
                "verification": {
                    "certificateDER_SHA512": "5" * 128,
                    "certificatePEM_SHA256": "6" * 64,
                    "outputValue": "E" * 128,
                    "pulseIndex": pulse_index,
                    "chainIndex": 2,
                    "signatureVerified": True,
                    "outputValueVerified": True,
                },
                "selection": {
                    "candidateCount": 15,
                    "candidateIndex": 0,
                    "counter": 0,
                    "rejectionLimitHex": "f" * 128,
                    "seedDigestSHA512": "7" * 128,
                    "selectedWindow": {
                        "blocks": 32,
                        "id": "test-016-047",
                        "split": "test",
                        "startBlock": 16,
                    },
                },
            }
            resolution["resolutionSHA256"] = (
                beacon_protocol.artifact_digest_without_field(
                    resolution, "resolutionSHA256"
                )
            )

        outcome = {
            "schemaVersion": "corelm-beacon-outcome-v1",
            "suiteId": beacon_protocol.SUITE_ID,
            "evidenceClass": "post-freeze-beacon-selected-heldout-window",
            "countsTowardScientificVerdict": True,
            "verdict": "FAIL_EXECUTION",
            "status": "terminal-execution-failure",
            "finishedAt": "2026-08-02T18:00:02Z",
            "attemptSHA256": attempt["attemptSHA256"],
            "attemptArtifactSHA256": "",
            "resolutionSHA256": (
                "FOLLOW_RESOLUTION" if resolution else None
            ),
            "resolutionArtifactSHA256": (
                "FOLLOW_RESOLUTION" if resolution else None
            ),
            "error": {"type": "RuntimeError", "message": "fixture failure"},
            "scientificResult": None,
        }
        return verifier, freeze, attempt, resolution, outcome

    def _verify_failure_fixture(
        self,
        temporary: str,
        *,
        with_resolution: bool,
        mutate=None,
    ):
        verifier, freeze, attempt, resolution, outcome = self._failure_artifacts(
            with_resolution=with_resolution
        )
        root = Path(temporary)
        attempt_path = root / "attempt.json"
        resolution_path = root / "resolution.json"
        outcome_path = root / "outcome.json"
        freeze_path = root / "beacon_freeze.json"
        ledger_path = root / "beacon_window_ledger.json"
        ledger_path.write_bytes(b"ledger\n")
        if mutate is not None:
            mutate(attempt, resolution, outcome)
        attempt["attemptSHA256"] = beacon_protocol.artifact_digest_without_field(
            attempt, "attemptSHA256"
        )
        if resolution is not None:
            if resolution.get("attemptSHA256") == "FOLLOW_ATTEMPT":
                resolution["attemptSHA256"] = attempt["attemptSHA256"]
            resolution["resolutionSHA256"] = (
                beacon_protocol.artifact_digest_without_field(
                    resolution, "resolutionSHA256"
                )
            )
        attempt_raw = serialized_json_bytes(attempt)
        attempt_path.write_bytes(attempt_raw)
        if resolution is not None:
            resolution_raw = serialized_json_bytes(resolution)
            resolution_path.write_bytes(resolution_raw)
            if outcome.get("resolutionSHA256") == "FOLLOW_RESOLUTION":
                outcome["resolutionSHA256"] = resolution["resolutionSHA256"]
            if outcome.get("resolutionArtifactSHA256") == "FOLLOW_RESOLUTION":
                outcome["resolutionArtifactSHA256"] = beacon_protocol.sha256_bytes(
                    resolution_raw
                )
        outcome["attemptArtifactSHA256"] = beacon_protocol.sha256_bytes(attempt_raw)
        if outcome.get("attemptSHA256") == "FOLLOW_ATTEMPT":
            outcome["attemptSHA256"] = attempt["attemptSHA256"]
        outcome["outcomeSHA256"] = beacon_protocol.artifact_digest_without_field(
            outcome, "outcomeSHA256"
        )
        outcome_path.write_bytes(serialized_json_bytes(outcome))
        freeze_raw = serialized_json_bytes(freeze)
        freeze_path.write_bytes(freeze_raw)
        registration = {
            "suiteId": beacon_protocol.SUITE_ID,
            "execution": {"deadline": "2026-08-04T18:00:00.000Z"},
        }

        def digest(path):
            if path == ledger_path:
                return "3" * 64
            return beacon_protocol.sha256_file(path)

        with (
            mock.patch.object(verifier, "ATTEMPT_PATH", attempt_path),
            mock.patch.object(verifier, "RESOLUTION_PATH", resolution_path),
            mock.patch.object(verifier, "OUTCOME_PATH", outcome_path),
            mock.patch.object(verifier, "FREEZE_PATH", freeze_path),
            mock.patch.object(verifier, "LEDGER_PATH", ledger_path),
            mock.patch.object(
                verifier,
                "validate_registration_and_ledger",
                return_value=(registration, {}),
            ),
            mock.patch.object(
                verifier, "registration_artifact_sha256", return_value="1" * 64
            ),
            mock.patch.object(
                verifier, "registration_canonical_sha256", return_value="2" * 64
            ),
            mock.patch.object(
                verifier, "implementation_sha256", return_value="4" * 64
            ),
            mock.patch.object(verifier, "sha256_file", side_effect=digest),
            mock.patch.object(
                verifier,
                "git_text",
                return_value=verifier._git_blob_sha1(freeze_raw),
            ),
            mock.patch.object(
                verifier,
                "require_public_freeze",
                return_value={
                    **freeze,
                    "publicReleaseVerification": attempt["publicFreezeRelease"],
                },
            ),
            mock.patch.object(verifier, "verify_resolution", return_value=[]),
        ):
            return verifier.verify_evidence()

    def test_registration_and_ledger_are_internally_frozen(self):
        registration, ledger = validate_registration_and_ledger()
        self.assertEqual(registration["selection"]["candidateCount"], 15)
        self.assertEqual(len(ledger["eligibleWindows"]), 15)
        self.assertEqual(
            [window["startBlock"] for window in ledger["eligibleWindows"]],
            list(beacon_protocol.EXPECTED_ELIGIBLE_STARTS),
        )

    def test_registration_and_ledger_match_published_json_schemas(self):
        cases = (
            (
                REGISTRATION_PATH,
                PROJECT_ROOT / "schemas" / "beacon-registration.schema.json",
            ),
            (
                LEDGER_PATH,
                PROJECT_ROOT / "schemas" / "beacon-window-ledger.schema.json",
            ),
        )
        for document_path, schema_path in cases:
            with self.subTest(document=document_path.name):
                document = json.loads(document_path.read_text(encoding="utf-8"))
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                errors = sorted(
                    Draft202012Validator(schema).iter_errors(document),
                    key=lambda error: list(error.path),
                )
                self.assertEqual(errors, [])

    def test_resolution_schema_accepts_real_nist_list_value_uris(self):
        pulse, _ = self._fixture()
        schema = json.loads(
            (PROJECT_ROOT / "schemas" / "beacon-resolution.schema.json").read_text(
                encoding="utf-8"
            )
        )
        item_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
            **schema["$defs"]["nistListValue"],
        }
        validator = Draft202012Validator(item_schema)
        for item in pulse["listValues"]:
            with self.subTest(kind=item["type"]):
                self.assertEqual(list(validator.iter_errors(item)), [])
        invalid = copy.deepcopy(pulse["listValues"][0])
        invalid["uri"] = (
            "https://beacon.nist.gov/beacon/2.0/chain/02/pulse/01884239"
        )
        self.assertNotEqual(list(validator.iter_errors(invalid)), [])

    def test_public_freeze_requires_server_timestamped_immutable_release(self):
        metadata = {
            "tag_name": beacon_protocol.FREEZE_TAG,
            "html_url": beacon_protocol.PUBLIC_RELEASE_URL,
            "draft": False,
            "prerelease": False,
            "immutable": True,
            "published_at": "2026-08-01T12:00:00Z",
        }
        verified = beacon_protocol.verify_public_release_metadata(metadata)
        self.assertTrue(verified["immutable"])
        self.assertEqual(verified["publishedAt"], metadata["published_at"])
        for field, value in (
            ("immutable", False),
            ("published_at", beacon_protocol.TARGET_TIMESTAMP),
            ("tag_name", "different-tag"),
        ):
            tampered = copy.deepcopy(metadata)
            tampered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                beacon_protocol.verify_public_release_metadata(tampered)

    def test_public_tag_api_binds_lightweight_tag_to_exact_head(self):
        head = "a" * 40
        metadata = {
            "ref": f"refs/tags/{beacon_protocol.FREEZE_TAG}",
            "url": beacon_protocol.PUBLIC_TAG_REF_API.replace(
                "/git/ref/", "/git/refs/"
            ),
            "object": {
                "type": "commit",
                "sha": head,
                "url": (
                    "https://api.github.com/repos/ALLPROTO/"
                    "core-lm-benchmark/git/commits/" + head
                ),
            },
        }

        def fetch(value):
            return mock.patch.object(
                beacon_protocol,
                "_fetch_url",
                return_value=json.dumps(value).encode("utf-8"),
            )

        with fetch(metadata):
            self.assertEqual(beacon_protocol.fetch_public_tag_commit(head), head)
        for field, value in (("type", "tag"), ("sha", "b" * 40)):
            tampered = copy.deepcopy(metadata)
            tampered["object"][field] = value
            with self.subTest(field=field), fetch(tampered), self.assertRaises(
                ValueError
            ):
                beacon_protocol.fetch_public_tag_commit(head)

    def test_fail_execution_retains_freeze_and_artifact_bindings(self):
        for with_resolution in (False, True):
            with self.subTest(with_resolution=with_resolution):
                with tempfile.TemporaryDirectory() as temporary:
                    errors, outcome = self._verify_failure_fixture(
                        temporary, with_resolution=with_resolution
                    )
                self.assertEqual(errors, [])
                self.assertEqual(outcome["verdict"], "FAIL_EXECUTION")

    def test_fail_execution_tampering_fails_closed(self):
        mutations = {
            "attempt-extra-field": lambda attempt, _resolution, _outcome: attempt.update(
                {"unregistered": True}
            ),
            "implementation-freeze-binding": lambda attempt, _resolution, _outcome: attempt.update(
                {"implementationSHA256": "9" * 64}
            ),
            "public-release-binding": lambda attempt, _resolution, _outcome: attempt[
                "publicFreezeRelease"
            ].update({"htmlURL": "https://example.invalid/release"}),
            "attempt-before-beacon": lambda attempt, _resolution, _outcome: attempt.update(
                {"startedAt": "2026-08-02T17:59:59Z"}
            ),
            "noncanonical-attempt-time": lambda attempt, _resolution, _outcome: attempt.update(
                {"startedAt": "2026-08-02T18:00:00+00:00"}
            ),
            "failure-status": lambda _attempt, _resolution, outcome: outcome.update(
                {"status": "terminal-scientific-result"}
            ),
            "attempt-link": lambda _attempt, _resolution, outcome: outcome.update(
                {"attemptSHA256": "8" * 64}
            ),
            "absent-resolution-claim": lambda _attempt, _resolution, outcome: outcome.update(
                {
                    "resolutionSHA256": "7" * 64,
                    "resolutionArtifactSHA256": "6" * 64,
                }
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(tamper=label):
                with tempfile.TemporaryDirectory() as temporary:
                    errors, _ = self._verify_failure_fixture(
                        temporary,
                        with_resolution=False,
                        mutate=mutate,
                    )
                self.assertTrue(errors, label)

    def test_resolution_link_and_timestamp_tampering_fails_closed(self):
        def wrong_attempt(_attempt, resolution, outcome):
            resolution["attemptSHA256"] = "8" * 64
            outcome["resolutionSHA256"] = "FOLLOW_RESOLUTION"
            outcome["resolutionArtifactSHA256"] = "FOLLOW_RESOLUTION"

        def wrong_status(_attempt, resolution, outcome):
            resolution["status"] = "model-data-already-opened"
            outcome["resolutionSHA256"] = "FOLLOW_RESOLUTION"
            outcome["resolutionArtifactSHA256"] = "FOLLOW_RESOLUTION"

        def late_resolution(_attempt, resolution, outcome):
            resolution["resolvedAt"] = "2026-08-02T18:00:03Z"
            outcome["resolutionSHA256"] = "FOLLOW_RESOLUTION"
            outcome["resolutionArtifactSHA256"] = "FOLLOW_RESOLUTION"

        def false_list_uri(_attempt, resolution, outcome):
            resolution["pulse"]["listValues"][0]["uri"] = (
                "https://beacon.nist.gov/beacon/2.0/pulse/time/1785693600000"
            )
            outcome["resolutionSHA256"] = "FOLLOW_RESOLUTION"
            outcome["resolutionArtifactSHA256"] = "FOLLOW_RESOLUTION"

        def extra_resolution_field(_attempt, resolution, outcome):
            resolution["writerTrusted"] = True
            outcome["resolutionSHA256"] = "FOLLOW_RESOLUTION"
            outcome["resolutionArtifactSHA256"] = "FOLLOW_RESOLUTION"

        mutations = {
            "attempt-link": wrong_attempt,
            "status": wrong_status,
            "timestamp-order": late_resolution,
            "list-value-uri": false_list_uri,
            "extra-field": extra_resolution_field,
        }
        for label, mutate in mutations.items():
            with self.subTest(tamper=label):
                with tempfile.TemporaryDirectory() as temporary:
                    errors, _ = self._verify_failure_fixture(
                        temporary,
                        with_resolution=True,
                        mutate=mutate,
                    )
                self.assertTrue(errors, label)

    def test_bounded_reader_rejects_oversize_before_open(self):
        from RealLLM import verify_beacon_evidence as verifier

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oversize.json"
            path.write_bytes(b"12345")
            with mock.patch.object(Path, "open") as open_file:
                with self.assertRaisesRegex(ValueError, "outside 1..4"):
                    verifier._bounded_file_bytes(path, 4, label="oversize")
            open_file.assert_not_called()

    def test_verifier_import_preflight_rejects_local_bytecode(self):
        from RealLLM import verify_beacon_evidence as verifier

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "security" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "malicious.cpython-312.pyc").write_bytes(b"malicious")
            with mock.patch.object(verifier, "PROJECT_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "bytecode/cache"):
                    verifier._require_isolated_verifier_imports()

    def test_verifier_arithmetic_matches_frozen_producer(self):
        from RealLLM import beacon_evaluation
        from RealLLM import verify_beacon_evidence as verifier
        from RealLLM.benchmark_real_llm import aggregate_candidate_records

        registration = beacon_protocol.load_registration()
        configuration = registration["configuration"]
        identifier = beacon_protocol.sha256_bytes(
            beacon_protocol.canonical_json_bytes(configuration)
        )[:16]
        records = []
        baselines = []
        for index in range(32):
            records.append(
                {
                    "configurationId": identifier,
                    "predictionTokens": 128,
                    "denseBF16Bytes": 4_706_304,
                    "encodedFileBytes": 2_000_000 + index,
                    "top1AgreementCount": 127 + (index % 2),
                    "cacheDifferenceSumSquares": 1.0 + index / 10,
                    "cacheReferenceSumSquares": 10.0 + index,
                    "cacheCandidateSumSquares": 9.0 + index,
                    "cacheDotProduct": 8.0 + index,
                    "baselineNLLNatPerToken": 2.0 + index / 1000,
                    "candidateNLLNatPerToken": 2.001 + index / 1000,
                    "meanKLDivergenceNat": 0.001 + index / 100_000,
                    "cacheMaximumAbsoluteError": 0.1 + index / 1000,
                    "encodeNanoseconds": 100 + index,
                    "decodeNanoseconds": 200 + index,
                    "modelContinuationNanoseconds": 300 + index,
                    "payloadSHA256": f"{index:064x}",
                    "deltaNLLNatPerToken": 0.001,
                }
            )
            baselines.append(
                {
                    "exactRebuildMaxAbsLogitDifference": 0.0,
                    "exactRebuildTop1Identical": True,
                    "layoutRebuildMaxAbsLogitDifference": 0.0,
                    "layoutRebuildTop1Identical": True,
                }
            )
        producer_aggregate = aggregate_candidate_records(configuration, records)
        verifier_aggregate = verifier._aggregate_records(
            configuration, records, registration["gates"]
        )
        self.assertEqual(producer_aggregate, verifier_aggregate)
        producer_confidence = beacon_evaluation.compute_confidence_and_verdict(
            records, baselines, producer_aggregate, registration["gates"]
        )
        verifier_confidence = verifier._confidence_and_verdict(
            records, baselines, verifier_aggregate, registration["gates"]
        )
        self.assertEqual(producer_confidence, verifier_confidence)

    def test_real_nist_known_answer_signature_and_output_verify(self):
        pulse, certificate = self._fixture()
        verified = verify_nist_pulse(
            pulse,
            certificate,
            expected_timestamp="2026-07-31T23:20:00.000Z",
        )
        self.assertTrue(verified["signatureVerified"])
        self.assertTrue(verified["outputValueVerified"])
        self.assertEqual(verified["chainIndex"], 2)
        self.assertEqual(verified["pulseIndex"], 1_884_240)
        self.assertEqual(
            verified["certificateDER_SHA512"], pulse["certificateId"].lower()
        )
        self.assertEqual(verified["outputValue"], pulse["outputValue"])

    def test_nist_tampering_fails_closed(self):
        pulse, certificate = self._fixture()
        mutations = []
        wrong_output = copy.deepcopy(pulse)
        wrong_output["outputValue"] = "00" * 64
        mutations.append(wrong_output)
        wrong_signature = copy.deepcopy(pulse)
        wrong_signature["signatureValue"] = (
            "00" + wrong_signature["signatureValue"][2:]
        )
        mutations.append(wrong_signature)
        wrong_timestamp = copy.deepcopy(pulse)
        wrong_timestamp["timeStamp"] = "2026-07-31T23:21:00.000Z"
        mutations.append(wrong_timestamp)
        for mutation in mutations:
            with self.subTest(field=next(
                key for key in mutation if mutation[key] != pulse[key]
            )):
                with self.assertRaises(ValueError):
                    verify_nist_pulse(
                        mutation,
                        certificate,
                        expected_timestamp="2026-07-31T23:20:00.000Z",
                    )
        damaged_certificate = bytearray(certificate)
        damaged_certificate[len(damaged_certificate) // 2] ^= 1
        with self.assertRaises(ValueError):
            verify_nist_pulse(
                pulse,
                bytes(damaged_certificate),
                expected_timestamp="2026-07-31T23:20:00.000Z",
            )

    def test_selection_known_answer(self):
        pulse, _ = self._fixture()
        selection = select_window(
            REGISTRATION_PATH.read_bytes(),
            pulse["outputValue"],
            load_ledger()["eligibleWindows"],
        )
        self.assertEqual(selection["counter"], 0)
        self.assertEqual(selection["candidateIndex"], 3)
        self.assertEqual(selection["selectedWindow"]["id"], "test-112-143")
        self.assertEqual(
            selection["seedDigestSHA512"],
            "bb03cd92e2c2486a7e2dd452b83b1825e6ebef9b978b218b7e309e218abfbe7c7717aceb55c94d342f29544594141202e7b07bdfabc398658087d49b987e88b1",
        )

    def test_selection_commits_exact_registration_bytes(self):
        pulse, _ = self._fixture()
        windows = load_ledger()["eligibleWindows"]
        original = REGISTRATION_PATH.read_bytes()
        first = select_window(original, pulse["outputValue"], windows)
        second = select_window(original + b" ", pulse["outputValue"], windows)
        self.assertNotEqual(
            first["seedDigestSHA512"], second["seedDigestSHA512"]
        )

    def test_rejection_sampling_rejects_out_of_range_digest(self):
        counter, index, digest, limit = map_candidate_from_digest_sequence(
            (b"\xff" * 64, b"\x00" * 64), 15
        )
        self.assertEqual(counter, 1)
        self.assertEqual(index, 0)
        self.assertEqual(digest, b"\x00" * 64)
        self.assertEqual(limit, (1 << 512) - 1)

    def test_durable_write_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attempt.json"
            durable_exclusive_write(path, b"first\n")
            with self.assertRaises(ValueError):
                durable_exclusive_write(path, b"second\n")
            self.assertEqual(path.read_bytes(), b"first\n")

    def test_one_shot_cli_has_no_source_or_gate_override(self):
        from RealLLM.run_beacon_one_shot import parse_arguments

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_arguments(["--test-start-block", "16"])
            with self.assertRaises(SystemExit):
                parse_arguments(["--minimum-top1", "0"])

    def test_marker_is_created_before_beacon_fetch(self):
        from RealLLM import beacon_evaluation
        from RealLLM import run_beacon_one_shot as runner
        from RealLLM import verify_beacon_evidence

        events: list[str] = []
        attempt = {"attemptSHA256": "a" * 64}
        resolution = {
            "resolutionSHA256": "b" * 64,
            "selection": {"selectedWindow": {"startBlock": 16}},
        }
        scientific = {
            "pass": True,
            "aggregate": {
                "compressionRatioVsBF16": 2.0,
                "deltaNLLNatPerToken": 0.0,
                "top1Agreement": 1.0,
            },
            "confidence": {"blockwiseDeltaNLLUpperOneSided95": 0.0},
        }

        def prepare_runtime():
            events.append("runtime-preflight")
            return {}

        def create_attempt(**_kwargs):
            events.append("attempt")
            return attempt

        def fetch():
            events.append("beacon")
            return {}, b"certificate"

        def evaluate(*_args, **_kwargs):
            events.append("model-data")
            return scientific

        registration = {
            "execution": {"deadline": "2026-08-04T18:00:00.000Z"}
        }
        with (
            mock.patch.multiple(
                runner,
                _require_isolated_python=mock.DEFAULT,
                _configure_frozen_process_environment=mock.DEFAULT,
                _require_mac_resource_headroom=mock.DEFAULT,
                _acquire_proof_lock=mock.Mock(return_value=object()),
                _release_proof_lock=mock.DEFAULT,
            ),
            mock.patch.object(
                runner,
                "validate_registration_and_ledger",
                return_value=(registration, {}),
            ),
            mock.patch.object(runner, "_require_time_window"),
            mock.patch.object(runner, "_require_artifacts_absent"),
            mock.patch.object(runner, "require_clean_head", return_value="c" * 40),
            mock.patch.object(
                runner,
                "require_public_freeze",
                return_value={"protocolCommit": "d" * 40},
            ),
            mock.patch.object(runner, "implementation_sha256", return_value="e" * 64),
            mock.patch.object(beacon_evaluation, "prepare_runtime", side_effect=prepare_runtime),
            mock.patch.object(beacon_evaluation, "run_selected_window", side_effect=evaluate),
            mock.patch.object(
                verify_beacon_evidence,
                "verify_scientific_result",
                return_value=[],
            ),
            mock.patch.object(runner, "_create_attempt", side_effect=create_attempt),
            mock.patch.object(runner, "fetch_nist_pulse", side_effect=fetch),
            mock.patch.object(runner, "build_resolution", return_value=resolution),
            mock.patch.object(runner, "verify_resolution", return_value=[]),
            mock.patch.object(runner, "durable_exclusive_write"),
            mock.patch.object(runner, "_assert_normative_state"),
            mock.patch.object(runner, "registration_artifact_sha256", return_value="f" * 64),
            mock.patch.object(runner, "sha256_file", return_value="0" * 64),
        ):
            outcome = runner.run_one_shot(local_files_only=True)
        self.assertEqual(
            events,
            ["runtime-preflight", "attempt", "beacon", "model-data"],
        )
        self.assertEqual(outcome["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
