import gzip
import hashlib
import io
import json
import os
from contextlib import nullcontext
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zlib
from pathlib import Path, PurePosixPath
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publication import build_portfolio_release as portfolio  # noqa: E402
from security import automated_media  # noqa: E402
from security import verify_portfolio_tag_ci as tag_ci  # noqa: E402
from Tests import test_portfolio_tag_ci as tag_ci_fixture  # noqa: E402


TAG = "corelm-portfolio-v3"
COMMIT = "1" * 40
TAG_OBJECT = "0" * 40
LAB_COMMIT = "3" * 40
LAB_TREE = "4" * 40
BLIND_COMMIT = "5" * 40
BLIND_TREE = "6" * 40
FFPROBE_VERSION = "ffprobe version 7.1.1-fixture"
FFMPEG_VERSION = "ffmpeg version 7.1.1-fixture"
HELPER_BYTES = b"compiled-window-helper-fixture\n"
FFPROBE_BYTES = (
    b"#!/bin/sh\n"
    b"if [ \"${1:-}\" = -version ]; then\n"
    b"  /bin/echo 'ffprobe version 7.1.1-fixture'\n"
    b"  exit 0\n"
    b"fi\n"
    b"/bin/echo '{\"format\":{\"duration\":\"30.0\"},"
    b"\"streams\":[{\"codec_type\":\"video\",\"codec_name\":"
    b"\"h264\",\"width\":1280,\"height\":720}]}'\n"
)
SOURCE_ARCHIVE_FILES = {
    "README.md": b"# fixture\n",
    **{
        path: path.encode("ascii")
        for path in (*portfolio.LOCKFILE_PATHS, *portfolio.VERIFIER_PATHS)
    },
}
TREE = portfolio._git_tree_oid(
    {
        path: (
            "100644",
            portfolio._git_sha1(
                b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
            ),
        )
        for path, payload in SOURCE_ARCHIVE_FILES.items()
    }
)


def _canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PortfolioReleaseTests(unittest.TestCase):
    def _release_input(self):
        return {
            "schema_version": 2,
            "tag": TAG,
            "release_date": "2026-08-09",
            "source": {"commit": COMMIT, "tag_object": TAG_OBJECT, "tree": TREE},
            "continuous_integration": {
                "linux_x86_64": {
                    "commit": COMMIT,
                    "conclusion": "success",
                    "required": True,
                    "url": "https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/101",
                },
                "macos_arm64": {
                    "commit": COMMIT,
                    "conclusion": "success",
                    "required": True,
                    "url": "https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/102",
                },
            },
            "related_sources": {
                "cross_model_lab": {"commit": LAB_COMMIT, "tree": LAB_TREE},
                "blind_v1_draft": {
                    "commit": BLIND_COMMIT,
                    "tree": BLIND_TREE,
                    "lifecycle_state": "CHECKPOINT_MISSED_TERMINAL_DRAFT",
                    "pull_request": "https://github.com/ALLPROTO/core-lm-cross-model-lab/pull/5",
                },
            },
            "local_assets": {
                "demo_video": "/private/tmp/video.mp4",
                "demo_poster": "/private/tmp/poster.png",
                "demo_provenance": "/private/tmp/provenance.json",
                "demo_evidence": "/private/tmp/evidence.tar.gz",
                "runtime_assets": "/private/tmp/runtime.json",
            },
            "presentation": dict(portfolio.PRESENTATION_CONTRACT),
        }

    def _tar_gzip(self, members, *, comment=None):
        raw = io.BytesIO()
        keywords = {"format": tarfile.PAX_FORMAT}
        if comment is not None:
            keywords["pax_headers"] = {"comment": comment}
        with tarfile.open(fileobj=raw, mode="w", **keywords) as archive:
            ordered = (
                sorted(members, key=lambda item: item[0].encode("utf-8"))
                if comment is None
                else members
            )
            for name, payload in ordered:
                entry = tarfile.TarInfo(name)
                if payload is None:
                    entry.type = tarfile.DIRTYPE
                    entry.size = 0
                    entry.mode = 0o775
                    entry.mtime = 0
                    archive.addfile(entry)
                    continue
                entry.size = len(payload)
                entry.mode = 0o600 if comment is None else 0o664
                entry.uid = 0
                entry.gid = 0
                entry.uname = ""
                entry.gname = ""
                entry.mtime = 0
                archive.addfile(entry, io.BytesIO(payload))
        target = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=target, mtime=0) as compressed:
            compressed.write(raw.getvalue())
        return target.getvalue()

    def _capture_tools(self, helper_sha256=None):
        if helper_sha256 is None:
            helper_sha256 = hashlib.sha256(HELPER_BYTES).hexdigest()
        return {
            "window_helper": {
                "source_sha256": "4" * 64,
                "executable_sha256": helper_sha256,
                "swift_version": "Apple Swift version 6.3.3 fixture",
            },
            "screencapture": {
                "executable_sha256": "6" * 64,
                "codesign_identifier": "com.apple.screencapture",
            },
            "ffmpeg": {
                "executable_sha256": "7" * 64,
                "version": FFMPEG_VERSION,
            },
            "ffprobe": {
                "executable_sha256": hashlib.sha256(FFPROBE_BYTES).hexdigest(),
                "version": FFPROBE_VERSION,
            },
        }

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

    def _automation_report(
        self,
        receipt,
        result,
        *,
        raw_sha256,
        helper_sha256,
        tag_ci_sha256,
        local_tag_trust_sha256,
    ):
        receipt_value = json.loads(receipt)
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
            "source": {"tag": TAG, "commit": COMMIT, "tree": TREE},
            "run": {
                "identifier": "12345678-1234-4234-8234-123456789abc",
                "challenge_sha256": automated_media.challenge_sha256(
                    receipt_value["challengeNonce"]
                ),
                "receipt_sha256": hashlib.sha256(receipt).hexdigest(),
                "result_sha256": hashlib.sha256(result).hexdigest(),
                "application_executable_sha256": "7" * 64,
                "metric_verdict": "PASS",
                "terminal_outcome": "END-TO-END PROOF PASS",
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
                    "preflight", 99, 199,
                    automated_media.PREFLIGHT_SEGMENT_SECONDS, raw_sha256,
                ),
                "segments": [
                    self._segment(
                        "live_presentation", 100, 200,
                        automated_media.LIVE_SEGMENT_SECONDS, raw_sha256,
                    ),
                    self._segment(
                        "same_run_result", 101, 201,
                        automated_media.RESULT_SEGMENT_SECONDS, raw_sha256,
                    ),
                ],
            },
            "tools": self._capture_tools(helper_sha256),
            "output": {
                "video_sha256": hashlib.sha256(self._mp4()).hexdigest(),
                "poster_sha256": hashlib.sha256(self._png()).hexdigest(),
                "poster_frame_timestamp_seconds": automated_media.POSTER_TIMESTAMP_SECONDS,
                "duration_seconds": 30.0,
                "width": 1280,
                "height": 720,
                "frame_count": 900,
                "pts_sha256": "a" * 64,
                "decoded_frames_sha256": "b" * 64,
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
                "state_log_sha256": "c" * 64,
                "tag_ci_receipt_sha256": tag_ci_sha256,
                "local_tag_trust_receipt_sha256": local_tag_trust_sha256,
            },
        }

    def _attempt_state(self, report):
        preflight = report["capture"]["preflight_segment"]
        live, result = report["capture"]["segments"]
        common = {"schema_version": 1, "tag": report["source"]["tag"]}
        events = [
            {**common, "event": "ATTEMPT_STARTED", "proof_invocation_count": 0,
             "source_commit": report["source"]["commit"], "source_tree": report["source"]["tree"],
             "preflight_segment_sha256": preflight["sha256"],
             "preflight_owner_pid": preflight["owner_pid"], "preflight_window_id": preflight["window_id"],
             "window_helper_sha256": report["tools"]["window_helper"]["executable_sha256"],
             "tag_ci_receipt_sha256": report["attempt"]["tag_ci_receipt_sha256"],
             "local_tag_trust_receipt_sha256": report["attempt"]["local_tag_trust_receipt_sha256"]},
            {**common, "event": "LIVE_SURFACE_READY", "proof_invocation_count": 0,
             "executable_sha256": report["run"]["application_executable_sha256"],
             "owner_pid": live["owner_pid"], "window_id": live["window_id"]},
            {**common, "event": "PROOF_INVOKED", "proof_invocation_count": 1,
             "challenge_sha256": report["run"]["challenge_sha256"]},
            {**common, "event": "LIVE_CAPTURED", "proof_invocation_count": 1,
             "segment_sha256": live["sha256"], "window_id": live["window_id"]},
            {**common, "event": "PROOF_TERMINAL", "proof_invocation_count": 1,
             "metric_verdict": report["run"]["metric_verdict"],
             "run_identifier": report["run"]["identifier"],
             "terminal_outcome": report["run"]["terminal_outcome"]},
            {**common, "event": "REPLAY_VERIFIED", "proof_invocation_count": 1,
             "replay_verdict": report["run"]["replay_verdict"],
             "run_identifier": report["run"]["identifier"]},
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

    def _evidence(self, *, nested_directories=False, build_document=None):
        if build_document is None:
            build_document = {}
        runtime_manifest_sha256 = "9" * 64
        runtime = _canonical(
            {
                "schema_version": 1,
                "source_manifest": {
                    "schema_version": "corelm-python-runtime-manifest-v1",
                    "sha256": runtime_manifest_sha256,
                    "file_count": 10,
                    "symlink_count": 1,
                    "total_bytes": 1000,
                    "entries_sha256": "8" * 64,
                },
                "python": {
                    "version": "3.12.13",
                    "executable_sha256": "a" * 64,
                },
            }
        )
        result = _canonical(
            {
                "aggregates": [{"pass": True}],
                "environment": {"python": "3.12.13"},
                "resultSHA256": "d" * 64,
                "schemaVersion": "corelm-voidtoken-v5-validation-development-v3",
            }
        )
        result_digest = hashlib.sha256(result).hexdigest()
        receipt = _canonical(
            {
                "application": {"executableSHA256": "7" * 64},
                "buildProvenance": {"document": build_document},
                "challengeNonce": "e" * 64,
                "error": None,
                "result": {
                    "compressionRatioVsBF16": 2.0,
                    "deltaNLLNatPerToken": 0.001,
                    "metricVerdict": "PASS",
                    "path": "validation-064-071.json",
                    "resultFileSHA256": result_digest,
                    "resultRole": "PUBLIC_VALIDATION_REGRESSION",
                    "resultSHA256": "d" * 64,
                    "swiftStructuralVerification": "PASS",
                    "top1Agreement": 0.999,
                },
                "schemaVersion": "corelm-macos-app-real-llm-run-v5",
                "worker": {
                    "pythonExecutableSHA256": "a" * 64,
                    "runtimeManifestSHA256": runtime_manifest_sha256,
                },
            }
        )
        receipt_digest = hashlib.sha256(receipt).hexdigest()
        readiness = _canonical(
            {
                "schema_version": 1,
                "status": "CAPTURE_RESULT_READY",
                "run_identifier": "12345678-1234-4234-8234-123456789abc",
                "receipt_sha256": receipt_digest,
                "result_sha256": result_digest,
                "application_executable_sha256": "7" * 64,
                "metric_verdict": "PASS",
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
        )
        raw_segment = self._mp4()
        raw_segment_sha256 = hashlib.sha256(raw_segment).hexdigest()
        helper_bytes = HELPER_BYTES
        helper_sha256 = hashlib.sha256(helper_bytes).hexdigest()
        tag_ci_responses = {
            role: raw.replace(("a" * 40).encode(), TAG_OBJECT.encode())
            .replace(("b" * 40).encode(), COMMIT.encode())
            .replace(("c" * 40).encode(), TREE.encode())
            for role, raw in tag_ci_fixture._fixture_responses().items()
        }
        tag_ci_receipt_value = tag_ci.validate_saved_tag_ci(
            tag_ci_responses,
            repository=tag_ci.DEFAULT_REPOSITORY,
            expected_tag=TAG,
            expected_commit=COMMIT,
            expected_tree=TREE,
        )
        tag_ci_receipt = tag_ci.canonical_receipt_bytes(tag_ci_receipt_value)
        local_tag_trust_receipt = tag_ci.canonical_receipt_bytes(
            {
                "schema_version": 1,
                "artifact_kind": "corelm_portfolio_local_tag_trust_receipt",
                "status": "PASS",
                "tag": TAG,
                "tag_object": TAG_OBJECT,
                "commit": COMMIT,
                "tree": TREE,
                "principal": tag_ci.EXPECTED_SIGNING_PRINCIPAL,
                "fingerprint": tag_ci.EXPECTED_FINGERPRINT,
                "public_key_sha256": tag_ci.EXPECTED_PUBLIC_KEY_SHA256,
                "allowed_signers_sha256": tag_ci.EXPECTED_ALLOWED_SIGNERS_SHA256,
                "git_binary": tag_ci.GIT,
                "ssh_keygen_binary": tag_ci.SSH_KEYGEN,
                "verification": "PINNED_SSH_GIT_NAMESPACE_PASS",
            }
        )
        automation_report = self._automation_report(
            receipt,
            result,
            raw_sha256=raw_segment_sha256,
            helper_sha256=helper_sha256,
            tag_ci_sha256=hashlib.sha256(tag_ci_receipt).hexdigest(),
            local_tag_trust_sha256=hashlib.sha256(
                local_tag_trust_receipt
            ).hexdigest(),
        )
        automation_report["capture"]["result_readiness_sha256"] = (
            hashlib.sha256(readiness).hexdigest()
        )
        attempt_state = self._attempt_state(automation_report)
        automation_report["attempt"]["state_log_sha256"] = hashlib.sha256(
            attempt_state
        ).hexdigest()
        base_report = {
            "schema_version": 1,
            "verdict": "PASS",
            "metric_verdict": "PASS",
            "source": {"commit": COMMIT, "tree": TREE},
            "receipt_sha256": receipt_digest,
            "result_sha256": result_digest,
            "workload_classification": "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION",
            "synthetic_data": False,
        }
        structural = {**base_report, "report_kind": "structural_verifier"}
        replay = {
            **base_report,
            "report_kind": "fresh_model_replay",
            "verdict": "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS",
            "execution_scope": (
                "AUTHOR_RECORDED_NOT_INDEPENDENTLY_REEXECUTED_BY_RELEASE_VERIFIER"
            ),
            "model": {
                "repository": portfolio.EXPECTED_MODEL,
                "revision": portfolio.EXPECTED_MODEL_REVISION,
            },
            "replay": {
                "decisions": 1024,
                "lossAbsoluteTolerance": 2e-5,
                "lossRelativeTolerance": 2e-6,
                "maximumBaselineLossDifference": 1e-7,
                "maximumCandidateLossDifference": 2e-7,
                "maximumAllowedBaselineDifference": 2e-5,
                "maximumAllowedCandidateDifference": 2e-5,
                "primaryManifestSHA256": "1" * 64,
                "tokenMetricsSHA256": "2" * 64,
                "perDecisionEvidenceSHA256": "3" * 64,
            },
        }
        members = [
            ("run/app-run-receipt.json", receipt),
            ("run/validation-064-071.json", result),
            ("run/build-provenance.json", _canonical(build_document)),
            ("run/runtime-provenance.json", runtime),
            ("run/primary-evidence/manifest.json", b"{}\n"),
            ("reports/structural-verifier.json", _canonical(structural)),
            ("reports/fresh-model-replay.json", _canonical(replay)),
            ("reports/automated-media.json", _canonical(automation_report)),
            ("reports/result-readiness.json", readiness),
            ("reports/tag-ci-receipt.json", tag_ci_receipt),
            ("reports/local-tag-trust-receipt.json", local_tag_trust_receipt),
            ("session/attempt-state.jsonl", attempt_state),
            ("session/preflight-window.mov", raw_segment),
            ("session/live-presentation.mov", raw_segment),
            ("session/same-run-result.mov", raw_segment),
            ("session/find-proof-window", helper_bytes),
            ("logs/terminal.log", b"END-TO-END PROOF PASS\n"),
        ]
        members.extend(
            (
                f"tag-ci-responses/{tag_ci.RESPONSE_FILENAMES[role]}",
                tag_ci_responses[role],
            )
            for role in tag_ci.RESPONSE_ROLES
        )
        members.append(
            (
                f"tag-ci-responses/{tag_ci.PUBLIC_RECEIPT_FILENAME}",
                tag_ci_receipt,
            )
        )
        if nested_directories:
            members.extend(
                [
                    ("run/primary-evidence/containers", None),
                    ("run/primary-evidence/containers/block-064", None),
                    (
                        "run/primary-evidence/containers/block-064/container.json",
                        b"{}\n",
                    ),
                ]
            )
        return self._tar_gzip(members)

    def _png(self, width=1280, height=720):
        def chunk(kind, payload):
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        pixels = (b"\x00" + b"\x00" * (width * 3)) * height
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(pixels, 9))
            + chunk(b"IEND", b"")
        )

    def _mp4(self):
        def atom(kind, payload):
            return struct.pack(">I4s", 8 + len(payload), kind) + payload

        visual_sample_entry = (
            b"\x00" * 6
            + struct.pack(">H", 1)
            + b"\x00" * 16
            + struct.pack(">HH", 1280, 720)
            + struct.pack(">II", 0x00480000, 0x00480000)
            + b"\x00" * 4
            + struct.pack(">H", 1)
            + b"\x00" * 32
            + struct.pack(">Hh", 24, -1)
        )
        avcc = atom(b"avcC", b"\x01\x64\x00\x1f\xff\xe1\x00")
        avc1 = atom(b"avc1", visual_sample_entry + avcc)
        stsd = atom(b"stsd", b"\x00" * 4 + struct.pack(">I", 1) + avc1)
        moov = atom(
            b"moov",
            atom(b"trak", atom(b"mdia", atom(b"minf", atom(b"stbl", stsd)))),
        )
        return (
            atom(b"ftyp", b"isom\x00\x00\x02\x00isomiso2")
            + moov
            + atom(b"mdat", b"\x00" * 1024)
        )

    def _ffprobe(self, root):
        target = root / "ffprobe-fixture"
        target.write_bytes(FFPROBE_BYTES)
        target.chmod(0o700)
        return target

    def _source_archive(self, files=None):
        files = SOURCE_ARCHIVE_FILES if files is None else files
        directories = {"core-lm-benchmark"}
        for relative in files:
            parts = PurePosixPath(relative).parts
            directories.update(
                "core-lm-benchmark/" + PurePosixPath(*parts[:index]).as_posix()
                for index in range(1, len(parts))
            )
        return self._tar_gzip(
            [(name, None) for name in sorted(directories)]
            + [
                (f"core-lm-benchmark/{name}", payload)
                for name, payload in sorted(files.items())
            ],
            comment=COMMIT,
        )

    def _provenance(self, video, poster, evidence):
        with tarfile.open(evidence, "r:gz") as archive:
            receipt = archive.extractfile("run/app-run-receipt.json").read()
            result = archive.extractfile("run/validation-064-071.json").read()
            automation_receipt = archive.extractfile(
                "reports/automated-media.json"
            ).read()
            result_readiness = archive.extractfile(
                "reports/result-readiness.json"
            ).read()
        return {
            "schema_version": 2,
            "tag": TAG,
            "source": {"commit": COMMIT, "tree": TREE},
            "video": {
                "sha256": _sha256(video),
                "duration_seconds": 30.0,
                "width": 1280,
                "height": 720,
                "codec": "h264",
                "audio_codec": "silent",
                "evidence_role": portfolio.MEDIA_CLASSIFICATION,
            },
            "poster": {
                "sha256": _sha256(poster),
                "width": 1280,
                "height": 720,
                "frame_timestamp_seconds": automated_media.POSTER_TIMESTAMP_SECONDS,
                "evidence_role": portfolio.MEDIA_CLASSIFICATION,
            },
            "capture": {
                "platform": "macOS",
                "architecture": "arm64",
                "automation_contract": automated_media.AUTOMATION_CONTRACT,
                "mode": automated_media.CAPTURE_MODE,
                "automation_only": True,
                "human_reviewed": False,
                "manual_edits": False,
                "machine_evidence": False,
                "pixel_semantics_verified": False,
                "automation_receipt_sha256": hashlib.sha256(
                    automation_receipt
                ).hexdigest(),
                "result_readiness_sha256": hashlib.sha256(
                    result_readiness
                ).hexdigest(),
            },
            "application_executable_sha256": "7" * 64,
            "result_sha256": hashlib.sha256(result).hexdigest(),
            "receipt_sha256": hashlib.sha256(receipt).hexdigest(),
            "evidence_sha256": _sha256(evidence),
            "workload_classification": "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION",
            "synthetic_data": False,
        }

    def _runtime(self, provenance):
        return {
            "schema_version": 2,
            "tag": TAG,
            "source": {"commit": COMMIT, "tree": TREE},
            "platform": {"system": "macOS", "architecture": "arm64"},
            "python": {"version": "3.12.13", "executable_sha256": "a" * 64},
            "toolchain": {
                "developerTools": {
                    "buildVersion": None,
                    "identifier": "com.apple.pkg.CLTools_Executables",
                    "kind": "command-line-tools",
                    "version": "26.6.0.0.1781586589",
                },
                "macOS": {
                    "architecture": "arm64",
                    "buildVersion": "25D125",
                    "productName": "macOS",
                    "productVersion": "26.3",
                },
                "sdk": {
                    "buildVersion": "25F70",
                    "canonicalName": "macosx",
                    "version": "26.5",
                },
                "swift": {
                    "compiler": "swift-frontend",
                    "compilerSHA256": "e" * 64,
                    "target": "arm64-apple-macosx26.0",
                    "version": (
                        "Apple Swift version 6.3.3 "
                        "(swiftlang-6.3.3.1.3)"
                    ),
                },
            },
            "ffprobe": {
                "executable_sha256": hashlib.sha256(FFPROBE_BYTES).hexdigest(),
                "version": FFPROBE_VERSION,
            },
            "capture_tools": self._capture_tools(),
            "lockfiles": [
                {"path": path, "sha256": hashlib.sha256(path.encode()).hexdigest()}
                for path in portfolio.LOCKFILE_PATHS
            ],
            "model": {
                "repository": portfolio.PINNED_RELEASE_ASSETS["model"]["repository"],
                "revision": portfolio.PINNED_RELEASE_ASSETS["model"]["revision"],
                "license": portfolio.PINNED_RELEASE_ASSETS["model"]["license"],
                "files": [
                    {
                        "path": path,
                        "sha256": asset["sha256"],
                        "size_bytes": asset["bytes"],
                    }
                    for path, asset in sorted(
                        portfolio.PINNED_RELEASE_ASSETS["model"]["files"].items()
                    )
                ],
            },
            "corpus": {
                "repository": portfolio.PINNED_RELEASE_ASSETS["corpus"]["repository"],
                "revision": portfolio.PINNED_RELEASE_ASSETS["corpus"]["revision"],
                "path": portfolio.PINNED_RELEASE_ASSETS["corpus"]["path"],
                "size_bytes": portfolio.PINNED_RELEASE_ASSETS["corpus"]["bytes"],
                "sha256": portfolio.PINNED_RELEASE_ASSETS["corpus"]["sha256"],
                "license": portfolio.PINNED_RELEASE_ASSETS["corpus"]["license"],
                "source_url": portfolio.PINNED_RELEASE_ASSETS["corpus"]["source_url"],
            },
            "application": {
                "executable_sha256": provenance["application_executable_sha256"]
            },
            "proof": {
                "receipt_sha256": provenance["receipt_sha256"],
                "result_sha256": provenance["result_sha256"],
                "evidence_sha256": provenance["evidence_sha256"],
            },
            "verifiers": [
                {"path": path, "sha256": hashlib.sha256(path.encode()).hexdigest()}
                for path in portfolio.VERIFIER_PATHS
            ],
        }

    def _write_fixture_bundle(self, root):
        video = root / f"{TAG}-demo.mp4"
        video.write_bytes(self._mp4())
        poster = root / f"{TAG}-demo-poster.png"
        poster.write_bytes(self._png())
        evidence = root / f"{TAG}-demo-evidence.tar.gz"
        evidence.write_bytes(self._evidence())
        provenance = self._provenance(video, poster, evidence)
        (root / f"{TAG}-demo-provenance.json").write_bytes(_canonical(provenance))
        (root / f"{TAG}-runtime-assets.json").write_bytes(
            _canonical(self._runtime(provenance))
        )
        shutil.copyfile(
            ROOT / "signing" / "corelm-codec-signing.pub",
            root / "corelm-portfolio-signing.pub",
        )
        shutil.copyfile(
            ROOT / "signing" / "allowed_signers", root / "allowed_signers"
        )
        release_input = self._release_input()
        identity = portfolio._source_identity(release_input, provenance)
        (root / f"{TAG}-source-identity.json").write_bytes(_canonical(identity))
        (root / f"{TAG}-source-identity.json.sig").write_text(
            "fixture signature\n", encoding="ascii"
        )
        (root / f"{TAG}-source.tar.gz").write_bytes(self._source_archive())
        sbom = {
            "bomFormat": "CycloneDX",
            "components": [{"type": "library", "name": "jsonschema"}],
            "dependencies": [],
            "metadata": {
                "component": {"version": TAG},
                "properties": [
                    {
                        "name": "corelm:sbom-scope",
                        "value": "direct-python-dependencies-only",
                    }
                ],
            },
            "specVersion": "1.5",
            "version": 1,
        }
        (root / f"{TAG}-direct-dependencies.cdx.json").write_text(
            json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (root / f"REPRODUCE-{TAG}.md").write_bytes(
            portfolio.reproduce_document(TAG, COMMIT, TREE, TAG_OBJECT)
        )
        portfolio._write_checksums(root, TAG)
        (root / "SHA256SUMS.sig").write_text(
            "fixture signature\n", encoding="ascii"
        )

    def test_schemas_are_valid_and_release_input_is_exact(self):
        release_input = self._release_input()
        portfolio._validate_schema(
            release_input, portfolio.INPUT_SCHEMA, "release input"
        )
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence.tar.gz"
            evidence.write_bytes(self._evidence())
            receipt = portfolio._tag_ci_receipt_from_evidence(
                evidence,
                tag=TAG,
                source=release_input["source"],
            )
        portfolio._validate_ci_bindings(release_input, receipt)
        forged_url = json.loads(json.dumps(release_input))
        forged_url["continuous_integration"]["linux_x86_64"]["url"] = (
            "https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/999"
        )
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError, "recomputed tag-CI"
        ):
            portfolio._validate_ci_bindings(forged_url, receipt)
        release_input["unexpected"] = True
        with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "schema failure"):
            portfolio._validate_schema(
                release_input, portfolio.INPUT_SCHEMA, "release input"
            )

    def test_tag_ci_raw_object_must_equal_release_source_tag_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence.tar.gz"
            evidence.write_bytes(self._evidence())
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "cannot be independently recomputed"
            ):
                portfolio._tag_ci_receipt_from_evidence(
                    evidence,
                    tag=TAG,
                    source={
                        "commit": COMMIT,
                        "tree": TREE,
                        "tag_object": "f" * 40,
                    },
                )

    def test_release_input_rejects_pre_terminal_blind_v1_lifecycle(self):
        release_input = self._release_input()
        release_input["related_sources"]["blind_v1_draft"][
            "lifecycle_state"
        ] = "DRAFT_NOT_PREREGISTERED"
        with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "schema failure"):
            portfolio._validate_schema(
                release_input, portfolio.INPUT_SCHEMA, "release input"
            )

    def test_canonical_json_rejects_unknown_encoding_and_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            value = self._release_input()
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "canonical compact"):
                portfolio._read_canonical_json(path)
            value["local_assets"]["demo_video"] = "/tmp/@DEMO@.mp4"
            path.write_bytes(_canonical(value))
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "placeholder"):
                portfolio._read_canonical_json(path)

    def test_runtime_toolchain_supports_clt_and_xcode_without_fabrication(self):
        provenance = {
            "application_executable_sha256": "7" * 64,
            "receipt_sha256": "8" * 64,
            "result_sha256": "9" * 64,
            "evidence_sha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            runtime = self._runtime(provenance)
            path.write_bytes(_canonical(runtime))
            observed = portfolio._validate_runtime_assets(
                path,
                tag=TAG,
                commit=COMMIT,
                tree=TREE,
                provenance=provenance,
                repository=None,
            )
            self.assertEqual(
                observed["toolchain"]["developerTools"]["kind"],
                "command-line-tools",
            )
            self.assertIsNone(
                observed["toolchain"]["developerTools"]["buildVersion"]
            )
            self.assertNotIn("xcode_version", observed["toolchain"])

            xcode = self._runtime(provenance)
            xcode["toolchain"]["developerTools"] = {
                "buildVersion": "16F6",
                "identifier": "com.apple.dt.Xcode",
                "kind": "xcode",
                "version": "16.4",
            }
            path.write_bytes(_canonical(xcode))
            portfolio._validate_runtime_assets(
                path,
                tag=TAG,
                commit=COMMIT,
                tree=TREE,
                provenance=provenance,
                repository=None,
            )

            fabricated = self._runtime(provenance)
            fabricated["toolchain"]["developerTools"]["buildVersion"] = "16F6"
            path.write_bytes(_canonical(fabricated))
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError,
                "runtime-assets manifest schema failure|runtime toolchain identity is not canonical",
            ):
                portfolio._validate_runtime_assets(
                    path,
                    tag=TAG,
                    commit=COMMIT,
                    tree=TREE,
                    provenance=provenance,
                    repository=None,
                )

    def test_product_evidence_resolves_symlinked_temporary_root(self):
        from security import proof_reports

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(strict=True)
            real_temporary = base / "canonical-temporary"
            real_temporary.mkdir(mode=0o700)
            alias = base / "temporary-alias"
            alias.symlink_to(real_temporary, target_is_directory=True)
            build_document = {"source": {"commit": COMMIT, "tree": TREE}}
            observed_kinds = []
            verified_result = {"environment": {"python": "3.12.13"}}

            def verify_report(path, run, kind):
                self.assertEqual(
                    proof_reports.validated_run_directory(run), run
                )
                self.assertTrue(path.is_file())
                observed_kinds.append(kind)
                return {}

            verifiers = (
                lambda value: _canonical(value),
                lambda value: None,
                lambda *args, **kwargs: verified_result,
            )
            with (
                tarfile.open(
                    fileobj=io.BytesIO(
                        self._evidence(build_document=build_document)
                    ),
                    mode="r:gz",
                ) as archive,
                patch.object(
                    portfolio.tempfile,
                    "TemporaryDirectory",
                    return_value=nullcontext(str(alias)),
                ),
                patch.object(
                    portfolio,
                    "_load_product_evidence_verifiers",
                    return_value=verifiers,
                ),
                patch.object(
                    portfolio,
                    "_validate_evidence_toolchain_binding",
                    return_value=None,
                ),
                patch.object(
                    portfolio,
                    "_validate_public_runtime_provenance",
                    return_value=None,
                ),
                patch.object(
                    proof_reports,
                    "verify_report",
                    side_effect=verify_report,
                ),
            ):
                observed = portfolio._extract_and_verify_product_evidence(
                    archive,
                    {"commit": COMMIT, "tree": TREE},
                )
            self.assertIs(observed, verified_result)
            self.assertEqual(
                observed_kinds,
                ["structural_verifier", "fresh_model_replay"],
            )

    def test_runtime_assets_require_exact_seven_model_and_validation_assets(self):
        provenance = {
            "application_executable_sha256": "7" * 64,
            "receipt_sha256": "8" * 64,
            "result_sha256": "9" * 64,
            "evidence_sha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            mutations = []
            omitted = self._runtime(provenance)
            omitted["model"]["files"].pop()
            mutations.append(("omitted", omitted))
            extra = self._runtime(provenance)
            extra["model"]["files"].append(
                {"path": "extra.json", "sha256": "f" * 64, "size_bytes": 1}
            )
            extra["model"]["files"].sort(key=lambda row: row["path"])
            mutations.append(("extra", extra))
            mutated = self._runtime(provenance)
            mutated["model"]["files"][0]["size_bytes"] += 1
            mutations.append(("mutated", mutated))
            corpus = self._runtime(provenance)
            corpus["corpus"]["path"] = "wikitext-2-raw-v1/test-00000-of-00001.parquet"
            mutations.append(("corpus", corpus))
            for label, runtime in mutations:
                with self.subTest(label=label):
                    path.write_bytes(_canonical(runtime))
                    with self.assertRaises(portfolio.PortfolioReleaseError):
                        portfolio._validate_runtime_assets(
                            path,
                            tag=TAG,
                            commit=COMMIT,
                            tree=TREE,
                            provenance=provenance,
                            repository=None,
                        )

    def test_release_asset_identity_matches_frozen_benchmark_constants(self):
        from RealLLM import benchmark_real_llm as benchmark

        pinned = portfolio.PINNED_RELEASE_ASSETS
        self.assertEqual(pinned["model"]["repository"], benchmark.MODEL_REPOSITORY)
        self.assertEqual(pinned["model"]["revision"], benchmark.MODEL_REVISION)
        expected_model_files = {
            "model.safetensors": {
                "bytes": benchmark.MODEL_WEIGHTS_BYTES,
                "sha256": benchmark.MODEL_WEIGHTS_SHA256,
            },
            **benchmark.MODEL_ASSET_FILES,
        }
        self.assertEqual(pinned["model"]["files"], expected_model_files)
        validation = benchmark.DATASET_FILES["validation"]
        self.assertEqual(
            {
                key: pinned["corpus"][key]
                for key in ("repository", "revision", "path", "bytes", "sha256")
            },
            {
                "repository": benchmark.DATASET_REPOSITORY,
                "revision": benchmark.DATASET_REVISION,
                "path": validation["path"],
                "bytes": validation["bytes"],
                "sha256": validation["sha256"],
            },
        )

    def test_runtime_python_is_cross_bound_to_receipt_result_and_assets(self):
        runtime = {
            "schema_version": 1,
            "source_manifest": {
                "schema_version": "corelm-python-runtime-manifest-v1",
                "sha256": "1" * 64,
                "file_count": 2,
                "symlink_count": 0,
                "total_bytes": 20,
                "entries_sha256": "2" * 64,
            },
            "python": {
                "version": "3.12.13",
                "executable_sha256": "3" * 64,
            },
        }
        receipt = {
            "worker": {
                "runtimeManifestSHA256": "1" * 64,
                "pythonExecutableSHA256": "3" * 64,
            }
        }
        result = {"environment": {"python": "3.12.13"}}
        portfolio._validate_public_runtime_provenance(
            runtime, receipt, result, runtime["python"]
        )
        wrong_assets = dict(runtime["python"])
        wrong_assets["executable_sha256"] = "4" * 64
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError, "runtime-assets Python differs"
        ):
            portfolio._validate_public_runtime_provenance(
                runtime, receipt, result, wrong_assets
            )
        wrong_result = {"environment": {"python": "3.12.12"}}
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError, "Python identities differ"
        ):
            portfolio._validate_public_runtime_provenance(
                runtime, receipt, wrong_result, runtime["python"]
            )

    def test_citation_rejects_duplicate_yaml_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "CITATION.cff").write_text(
                "cff-version: 1.2.0\n"
                "version: corelm-portfolio-v3\n"
                "version: corelm-portfolio-v3\n"
                "date-released: 2026-08-09\n"
                "license: MIT\n"
                "repository-code: https://github.com/ALLPROTO/core-lm-benchmark\n"
                "url: https://github.com/ALLPROTO/core-lm-benchmark\n"
                "authors:\n"
                "  - given-names: Ivan\n"
                "    family-names: Tyshchenko\n"
                "    orcid: https://orcid.org/0009-0000-7935-6090\n",
                encoding="utf-8",
            )
            with self.assertRaises(portfolio.PortfolioReleaseError):
                portfolio._validate_citation(root, TAG, "2026-08-09")

    def test_asset_contract_is_exact_and_checksum_is_sorted_over_twelve(self):
        names = portfolio.asset_names(TAG)
        self.assertEqual(len(names), 14)
        self.assertEqual(names[-2:], ("SHA256SUMS", "SHA256SUMS.sig"))
        self.assertEqual(len(portfolio.covered_asset_names(TAG)), 12)
        for unsafe in (
            "corelm-portfolio-v0",
            "corelm-portfolio-v01",
            "corelm-portfolio-v1-rc1",
            "voidtoken-v5-paper-v1",
        ):
            with self.subTest(tag=unsafe), self.assertRaises(
                portfolio.PortfolioReleaseError
            ):
                portfolio.asset_names(unsafe)

    def test_generated_reproduction_uses_asset_policy_and_locked_runtime(self):
        document = portfolio.reproduce_document(
            TAG, COMMIT, TREE, TAG_OBJECT
        ).decode("utf-8")
        self.assertIn(
            'gpg.ssh.allowedSignersFile="$asset_directory/allowed_signers"',
            document,
        )
        self.assertNotIn('gpg.ssh.allowedSignersFile="../allowed_signers"', document)
        self.assertIn(
            'locked_python="$HOME/.cache/corelm/macos/runtime/bin/python"',
            document,
        )
        self.assertIn(
            'locked_python="$HOME/.cache/corelm/linux/runtime/bin/python"',
            document,
        )
        self.assertIn("publication/run_portfolio_python.sh", document)
        self.assertIn(
            '"$locked_python" build_portfolio_release.py',
            document,
        )
        self.assertNotIn(
            '"$locked_python" -I -B publication/build_portfolio_release.py',
            document,
        )
        self.assertIn('PYTHON_BIN="$locked_python" ./corelm verify', document)
        self.assertNotIn("python3 -I -B publication/build_portfolio_release.py", document)

    def test_builder_repository_must_contain_the_running_tool(self):
        with patch.object(
            portfolio, "_resolve_exact_root", return_value=Path("/tmp/other-repository")
        ):
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "containing this builder"
            ):
                portfolio._require_builder_repository(Path("/tmp/other-repository"))

    def test_public_verifier_accepts_exact_bundle_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            ffprobe = self._ffprobe(root.parent)
            with (
                patch.object(portfolio, "_verify_detached_signature", return_value=None),
                patch.object(portfolio, "_extract_and_verify_product_evidence", return_value={}),
            ):
                result = portfolio.verify_release(root, ffprobe=ffprobe)
                self.assertEqual(result["status"], "OFFLINE_ARTIFACT_PASS")
                self.assertEqual(result["asset_count"], 14)
                target = root / f"{TAG}-demo.mp4"
                target.write_bytes(target.read_bytes() + b"tamper")
                with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "checksum mismatch"):
                    portfolio.verify_release(root, ffprobe=ffprobe)
            ffprobe.unlink()

    def test_public_verifier_rejects_asset_replacement_during_snapshot_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            ffprobe = self._ffprobe(root.parent)
            source_archive = root / f"{TAG}-source.tar.gz"
            replacement = root.parent / f"{root.name}-replacement.tar.gz"
            original_verify = portfolio._verify_release_snapshot

            def replace_public_asset(snapshot, *, ffprobe=None):
                result = original_verify(snapshot, ffprobe=ffprobe)
                replacement.write_bytes(source_archive.read_bytes() + b"replacement")
                os.replace(replacement, source_archive)
                return result

            try:
                with (
                    patch.object(
                        portfolio, "_verify_detached_signature", return_value=None
                    ),
                    patch.object(
                        portfolio,
                        "_extract_and_verify_product_evidence",
                        return_value={},
                    ),
                    patch.object(
                        portfolio,
                        "_verify_release_snapshot",
                        side_effect=replace_public_asset,
                    ),
                ):
                    with self.assertRaisesRegex(
                        portfolio.PortfolioReleaseError,
                        "changed during verification",
                    ):
                        portfolio.verify_release(root, ffprobe=ffprobe)
            finally:
                ffprobe.unlink()
                replacement.unlink(missing_ok=True)

    def test_archive_paths_are_not_reopened_after_checksum_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            ffprobe = self._ffprobe(root.parent)
            original_evidence = portfolio._validate_evidence_archive
            original_source_tree = portfolio._validate_source_archive_tree
            replacements = []

            def replace_path(path):
                replacement = path.with_name(f"{path.name}.replacement")
                replacement.write_bytes(b"not the signed gzip archive\n")
                os.replace(replacement, path)
                replacements.append(path.name)

            def validate_evidence(
                path,
                *,
                provenance,
                source,
                captured_source=None,
                expected_toolchain=None,
                expected_python=None,
            ):
                self.assertIsNotNone(captured_source)
                with self.assertRaises(OSError):
                    os.write(captured_source.fileno(), b"mutation")
                replace_path(path)
                return original_evidence(
                    path,
                    provenance=provenance,
                    source=source,
                    captured_source=captured_source,
                    expected_toolchain=expected_toolchain,
                    expected_python=expected_python,
                )

            def validate_source_tree(
                path,
                expected_tree,
                expected_commit,
                *,
                captured_source=None,
            ):
                self.assertIsNotNone(captured_source)
                replace_path(path)
                return original_source_tree(
                    path,
                    expected_tree,
                    expected_commit,
                    captured_source=captured_source,
                )

            try:
                with (
                    patch.object(
                        portfolio, "_verify_detached_signature", return_value=None
                    ),
                    patch.object(
                        portfolio,
                        "_extract_and_verify_product_evidence",
                        return_value={},
                    ),
                    patch.object(
                        portfolio,
                        "_validate_evidence_archive",
                        side_effect=validate_evidence,
                    ),
                    patch.object(
                        portfolio,
                        "_validate_source_archive_tree",
                        side_effect=validate_source_tree,
                    ),
                ):
                    with self.assertRaisesRegex(
                        portfolio.PortfolioReleaseError,
                        "checksum-bound release snapshot changed",
                    ):
                        portfolio.verify_release(root, ffprobe=ffprobe)
                self.assertCountEqual(
                    replacements,
                    [
                        f"{TAG}-demo-evidence.tar.gz",
                        f"{TAG}-source.tar.gz",
                    ],
                )
            finally:
                ffprobe.unlink()

    def test_nonarchive_replacement_after_checksum_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            ffprobe = self._ffprobe(root.parent)
            original_sbom = portfolio._validate_sbom

            def replace_sbom(path, tag):
                replacement = path.with_name(f"{path.name}.replacement")
                replacement.write_bytes(path.read_bytes())
                os.replace(replacement, path)
                return original_sbom(path, tag)

            try:
                with (
                    patch.object(
                        portfolio, "_verify_detached_signature", return_value=None
                    ),
                    patch.object(
                        portfolio,
                        "_extract_and_verify_product_evidence",
                        return_value={},
                    ),
                    patch.object(
                        portfolio, "_validate_sbom", side_effect=replace_sbom
                    ),
                ):
                    with self.assertRaisesRegex(
                        portfolio.PortfolioReleaseError,
                        "checksum-bound release snapshot changed",
                    ):
                        portfolio.verify_release(root, ffprobe=ffprobe)
            finally:
                ffprobe.unlink()

    def test_nonarchive_in_place_mutation_after_checksum_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            ffprobe = self._ffprobe(root.parent)
            original_sbom = portfolio._validate_sbom

            def mutate_sbom(path, tag):
                payload = path.read_bytes()
                status = path.stat()
                with path.open("r+b") as target:
                    target.write(payload)
                    target.flush()
                    os.fsync(target.fileno())
                os.utime(
                    path,
                    ns=(status.st_atime_ns, status.st_mtime_ns),
                    follow_symlinks=False,
                )
                return original_sbom(path, tag)

            try:
                with (
                    patch.object(
                        portfolio, "_verify_detached_signature", return_value=None
                    ),
                    patch.object(
                        portfolio,
                        "_extract_and_verify_product_evidence",
                        return_value={},
                    ),
                    patch.object(
                        portfolio, "_validate_sbom", side_effect=mutate_sbom
                    ),
                ):
                    with self.assertRaisesRegex(
                        portfolio.PortfolioReleaseError,
                        "checksum-bound asset changed",
                    ):
                        portfolio.verify_release(root, ffprobe=ffprobe)
            finally:
                ffprobe.unlink()

    def test_public_verifier_rejects_missing_extra_and_symlink_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            target = root / f"{TAG}-demo.mp4"
            target.unlink()
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "file set is not exact"):
                portfolio.verify_release(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            (root / "extra.txt").write_text("extra\n", encoding="ascii")
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "file set is not exact"):
                portfolio.verify_release(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            target = root / f"{TAG}-demo.mp4"
            outside = root.parent / (root.name + "-outside.mp4")
            outside.write_bytes(target.read_bytes())
            target.unlink()
            target.symlink_to(outside)
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "regular and not a symlink"):
                portfolio.verify_release(root)
            outside.unlink()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            target = root / f"{TAG}-demo.mp4"
            outside = root.parent / (root.name + "-hardlink.mp4")
            os.link(target, outside)
            try:
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "must not be hard-linked"
                ):
                    portfolio.verify_release(root)
            finally:
                outside.unlink()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            oversized = root / f"{TAG}-runtime-assets.json"
            with oversized.open("wb") as handle:
                handle.truncate(portfolio.MAX_JSON_BYTES + 1)
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "too large"):
                portfolio.verify_release(root)

    def test_local_release_inputs_reject_hardlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {}
            for key in (
                "demo_video",
                "demo_poster",
                "demo_provenance",
                "demo_evidence",
                "runtime_assets",
            ):
                target = root / key
                target.write_bytes(b"fixture")
                paths[key] = str(target)
            alias = root / "video-alias"
            os.link(root / "demo_video", alias)
            release_input = self._release_input()
            release_input["local_assets"] = paths
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "must not be hard-linked"
            ):
                portfolio._asset_paths(release_input)

    def test_all_nonarchive_assets_receive_strict_secret_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture_bundle(root)
            sbom_path = root / f"{TAG}-direct-dependencies.cdx.json"
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            sbom["components"][0]["description"] = (
                "Authorization" + ": Bearer " + "release-secret-value"
            )
            sbom_path.write_text(
                json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            portfolio._write_checksums(root, TAG)
            ffprobe = self._ffprobe(root.parent)
            try:
                with (
                    patch.object(
                        portfolio, "_verify_detached_signature", return_value=None
                    ),
                    patch.object(
                        portfolio,
                        "_extract_and_verify_product_evidence",
                        return_value={},
                    ),
                ):
                    with self.assertRaisesRegex(
                        portfolio.PortfolioReleaseError,
                        "authorization credential",
                    ):
                        portfolio.verify_release(root, ffprobe=ffprobe)
            finally:
                ffprobe.unlink()
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError, "authorization credential"
        ):
            portfolio._assert_public_bytes(
                b"https://" + b"user:secret@example.invalid/path",
                "metadata",
                strict_credentials=True,
            )

    def test_evidence_archive_rejects_links_and_missing_real_evidence_categories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incomplete = root / "incomplete.tar.gz"
            incomplete.write_bytes(self._tar_gzip([("receipt.json", b"{}\n")]))
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "missing"):
                portfolio._validate_evidence_archive(
                    incomplete,
                    provenance={"receipt_sha256": "1" * 64, "result_sha256": "2" * 64},
                    source={"commit": COMMIT, "tree": TREE},
                )

    def test_evidence_requires_exact_terminal_and_canonical_gzip_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.mp4"
            video.write_bytes(self._mp4())
            poster = root / "poster.png"
            poster.write_bytes(self._png())
            canonical = root / "canonical.tar.gz"
            canonical.write_bytes(self._evidence())
            with tarfile.open(canonical, "r:gz") as archive:
                members = [
                    (member.name, archive.extractfile(member).read())
                    for member in archive.getmembers()
                    if member.isfile()
                ]
            changed_terminal = [
                (
                    name,
                    b"prefix\nEND-TO-END PROOF PASS\n"
                    if name == "logs/terminal.log"
                    else payload,
                )
                for name, payload in members
            ]
            terminal_archive = root / "terminal.tar.gz"
            terminal_archive.write_bytes(self._tar_gzip(changed_terminal))
            provenance = self._provenance(video, poster, terminal_archive)
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "exact outcome"
            ):
                portfolio._validate_evidence_archive(
                    terminal_archive,
                    provenance=provenance,
                    source={"commit": COMMIT, "tree": TREE},
                )

            noncanonical = root / "noncanonical.tar.gz"
            payload = gzip.decompress(canonical.read_bytes())
            target = io.BytesIO()
            with gzip.GzipFile(
                filename="", mode="wb", compresslevel=1, fileobj=target, mtime=0
            ) as compressed:
                compressed.write(payload)
            noncanonical.write_bytes(target.getvalue())
            provenance = self._provenance(video, poster, noncanonical)
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "canonical tar.gz bytes"
            ):
                portfolio._validate_evidence_archive(
                    noncanonical,
                    provenance=provenance,
                    source={"commit": COMMIT, "tree": TREE},
                )

            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w:gz") as archive:
                link = tarfile.TarInfo("run/link")
                link.type = tarfile.SYMTYPE
                link.linkname = "/etc/passwd"
                archive.addfile(link)
            linked = root / "linked.tar.gz"
            linked.write_bytes(raw.getvalue())
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "link or special"):
                portfolio._validate_tar(
                    linked,
                    label="demo evidence archive",
                    source_commit=None,
                    source_prefix=None,
                )

            evidence = root / "valid-topology.tar.gz"
            evidence.write_bytes(self._evidence())
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "does not bind"):
                portfolio._validate_evidence_archive(
                    evidence,
                    provenance={
                        "receipt_sha256": "1" * 64,
                        "result_sha256": "2" * 64,
                        "application_executable_sha256": "7" * 64,
                    },
                    source={"commit": COMMIT, "tree": TREE},
                )

    def test_session_evidence_rejects_report_raw_state_helper_and_trust_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            video = root / "video.mp4"
            poster = root / "poster.png"
            video.write_bytes(self._mp4())
            poster.write_bytes(self._png())
            canonical = root / "canonical.tar.gz"
            canonical.write_bytes(self._evidence())
            with tarfile.open(canonical, "r:gz") as archive:
                base = {
                    member.name: archive.extractfile(member).read()
                    for member in archive.getmembers()
                    if member.isfile()
                }

            def json_mutation(payload, key, value):
                document = json.loads(payload)
                document[key] = value
                return _canonical(document)

            cases = {
                "reports/automated-media.json": lambda payload: json_mutation(
                    payload, "automation_only", False
                ),
                "session/live-presentation.mov": lambda payload: payload[:-1]
                + bytes([payload[-1] ^ 1]),
                "session/attempt-state.jsonl": lambda payload: payload.replace(
                    b'"event":"LIVE_CAPTURED"',
                    b'"event":"LIVE_CAPTURFd"',
                    1,
                ),
                "session/find-proof-window": lambda payload: payload + b"tamper\n",
                "reports/local-tag-trust-receipt.json": lambda payload: json_mutation(
                    payload, "status", "FAIL"
                ),
                f"tag-ci-responses/{tag_ci.RESPONSE_FILENAMES['main_ref']}": (
                    lambda payload: payload + b" "
                ),
            }
            for index, (member_name, mutate) in enumerate(cases.items()):
                with self.subTest(member=member_name):
                    members = dict(base)
                    members[member_name] = mutate(members[member_name])
                    path = root / f"tampered-{index}.tar.gz"
                    path.write_bytes(self._tar_gzip(list(members.items())))
                    provenance = self._provenance(video, poster, path)
                    with patch.object(
                        portfolio,
                        "_extract_and_verify_product_evidence",
                        return_value={},
                    ), self.assertRaises(portfolio.PortfolioReleaseError):
                        portfolio._validate_evidence_archive(
                            path,
                            provenance=provenance,
                            source={"commit": COMMIT, "tree": TREE},
                        )

    def test_evidence_archive_rejects_explicit_directory_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.mp4"
            video.write_bytes(self._mp4())
            poster = root / "poster.png"
            poster.write_bytes(self._png())
            evidence = root / "evidence.tar.gz"
            evidence.write_bytes(self._evidence(nested_directories=True))
            provenance = self._provenance(video, poster, evidence)
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "metadata is not canonical"
            ):
                portfolio._validate_evidence_archive(
                    evidence,
                    provenance=provenance,
                    source={"commit": COMMIT, "tree": TREE},
                )
            self.assertTrue(
                portfolio._evidence_directory_allowed(
                    "run/primary-evidence/containers/block-064"
                )
            )
            self.assertFalse(portfolio._evidence_directory_allowed("run/unbound"))

    def test_evidence_build_toolchain_must_equal_runtime_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "video.mp4"
            video.write_bytes(self._mp4())
            poster = root / "poster.png"
            poster.write_bytes(self._png())
            placeholder = root / "placeholder.tar.gz"
            placeholder.write_bytes(self._evidence())
            placeholder_provenance = self._provenance(
                video, poster, placeholder
            )
            runtime_toolchain = self._runtime(placeholder_provenance)["toolchain"]
            build_toolchain = json.loads(json.dumps(runtime_toolchain))
            build_toolchain["developerTools"]["version"] = "26.5.0.0.1"
            build_document = {
                "schemaVersion": "corelm-build-provenance-v1",
                "source": {
                    "archiveManifestSHA256": None,
                    "commit": COMMIT,
                    "dirty": False,
                    "exactTag": TAG,
                    "mode": "git",
                    "remote": portfolio.CANONICAL_REMOTE,
                    "tree": TREE,
                },
                "toolchain": build_toolchain,
            }
            evidence = root / "evidence.tar.gz"
            evidence.write_bytes(
                self._evidence(build_document=build_document)
            )
            provenance = self._provenance(video, poster, evidence)
            canonical, validate, _product_verifier = (
                portfolio._load_product_evidence_verifiers()
            )
            with patch.object(
                portfolio,
                "_load_product_evidence_verifiers",
                return_value=(
                    canonical,
                    validate,
                    lambda *_args, **_kwargs: {"aggregates": [{"pass": True}]},
                ),
            ):
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError,
                    "toolchain differs from demo build provenance",
                ):
                    portfolio._validate_evidence_archive(
                        evidence,
                        provenance=provenance,
                        source={"commit": COMMIT, "tree": TREE},
                        expected_toolchain=runtime_toolchain,
                    )

    def test_isolated_tool_loads_tracked_product_verifiers(self):
        program = (
            "import runpy,sys\n"
            "namespace=runpy.run_path(sys.argv[1],run_name='portfolio_isolated')\n"
            "namespace['_load_product_evidence_verifiers']()\n"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                program,
                str(ROOT / "publication" / "build_portfolio_release.py"),
            ],
            cwd=Path("/"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_source_private_path_exception_is_hash_exact_and_streaming(self):
        if (ROOT / ".git").exists():
            tracked = subprocess.check_output(
                ["/usr/bin/git", "ls-files", "-z"], cwd=ROOT
            ).decode("utf-8").split("\0")
            candidates = {relative for relative in tracked if relative}
            candidates.update(portfolio.LEGACY_PRIVATE_PATH_ALLOWLIST)
            candidates.update(
                {
                    "Tests/test_portfolio_release.py",
                    "publication/build_portfolio_release.py",
                    "publication/PORTFOLIO_RELEASE.md",
                    "schemas/portfolio-release-input.schema.json",
                    "schemas/portfolio-source-identity.schema.json",
                }
            )
            paths = [ROOT / relative for relative in candidates]
        else:
            paths = [
                path
                for path in ROOT.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            ]
        observed = {}
        for path in paths:
            if not path.is_file():
                continue
            payload = path.read_bytes()
            if any(
                pattern.search(payload) is not None
                for pattern in portfolio.ABSOLUTE_PRIVATE_PATHS
            ):
                observed[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
                    payload
                ).hexdigest()
        self.assertEqual(observed, portfolio.LEGACY_PRIVATE_PATH_ALLOWLIST)

        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "source.tar.gz"
            archive.write_bytes(
                self._tar_gzip(
                    [
                        (
                            "core-lm-benchmark/evil.txt",
                            b"/" + b"Users/private/new-secret\n",
                        )
                    ],
                    comment=COMMIT,
                )
            )
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "not hard-allowlisted"):
                portfolio._validate_tar(
                    archive,
                    label="source archive",
                    source_commit=COMMIT,
                    source_prefix="core-lm-benchmark/",
                    reject_absolute_paths=False,
                )

        class LargeStream:
            def __init__(self):
                self.remaining = 65

            def read(self, _size):
                if self.remaining:
                    self.remaining -= 1
                    return b"x" * (1024 * 1024)
                if self.remaining == 0:
                    self.remaining = -1
                    return b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----"
                return b""

        with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "private key"):
            portfolio._assert_public_stream(
                LargeStream(), "large member", reject_absolute_paths=True
            )

    def test_source_archive_reconstructs_exact_git_tree_and_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tar.gz"
            source.write_bytes(self._source_archive())
            portfolio._validate_source_archive_tree(source, TREE, COMMIT)

            changed = dict(SOURCE_ARCHIVE_FILES)
            changed["README.md"] = b"# changed fixture\n"
            mutated = root / "mutated.tar.gz"
            mutated.write_bytes(self._source_archive(changed))
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "signed source tree"
            ):
                portfolio._validate_source_archive_tree(mutated, TREE, COMMIT)

            removed = dict(SOURCE_ARCHIVE_FILES)
            removed.pop("README.md")
            incomplete = root / "incomplete.tar.gz"
            incomplete.write_bytes(self._source_archive(removed))
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "signed source tree"
            ):
                portfolio._validate_source_archive_tree(incomplete, TREE, COMMIT)

    def test_gzip_expansion_limit_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large.gz"
            path.write_bytes(gzip.compress(b"x" * 4096, mtime=0))
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "expands beyond"
            ):
                portfolio._validate_bounded_gzip(path, 1024, "fixture archive")
            concatenated = Path(temporary) / "concatenated.gz"
            concatenated.write_bytes(
                gzip.compress(b"first", mtime=0) + gzip.compress(b"second", mtime=0)
            )
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "trailing or concatenated"
            ):
                portfolio._validate_bounded_gzip(
                    concatenated, 1024, "fixture archive"
                )

    def test_tar_rejects_nonzero_bytes_after_end_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hidden-tail.tar.gz"
            valid = gzip.decompress(
                self._tar_gzip([("safe.txt", b"safe\n")])
            )
            hidden = b"gh" + b"p_" + b"A" * 32 + b" /" + b"Users/private/secret"
            path.write_bytes(gzip.compress(valid + hidden, mtime=0))
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError,
                "non-zero data after the tar end marker",
            ):
                portfolio._validate_tar(
                    path,
                    label="fixture archive",
                    source_commit=None,
                    source_prefix=None,
                )

    def test_public_media_verification_rejects_fake_mp4_and_truncated_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_mp4 = root / "fake.mp4"
            fake_mp4.write_bytes(struct.pack(">I", 24) + b"ftypisom" + b"\x00" * 24)
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "implausibly small"):
                portfolio._validate_mp4_atoms(fake_mp4)

            truncated_png = root / "truncated.png"
            truncated_png.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + struct.pack(">II", 1280, 720)
            )
            with self.assertRaises(portfolio.PortfolioReleaseError):
                portfolio._png_dimensions(truncated_png)

            def chunk(kind, payload):
                return (
                    struct.pack(">I", len(payload))
                    + kind
                    + payload
                    + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
                )

            clean = self._png()
            metadata_png = root / "metadata.png"
            metadata_png.write_bytes(clean[:33] + chunk(b"tEXt", b"Author\x00private") + clean[33:])
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "forbidden metadata"
            ):
                portfolio._png_dimensions(metadata_png)

    def test_video_free_text_metadata_is_rejected(self):
        base = {
            "format": {"duration": "20.0"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720,
                }
            ],
        }
        portfolio._validate_ffprobe_metadata(base)
        tagged = json.loads(json.dumps(base))
        tagged["format"]["tags"] = {
            "comment": (b"/" + b"Users/private/demo").decode("ascii")
        }
        with self.assertRaisesRegex(
            portfolio.PortfolioReleaseError, "free-text format metadata"
        ):
            portfolio._validate_ffprobe_metadata(tagged)

    def test_public_video_verification_requires_ffprobe(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "demo.mp4"
            path.write_bytes(self._mp4())
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "ffprobe is required"):
                portfolio._validate_video(
                    path,
                    {"video": {}},
                    None,
                    {},
                    require_recorded_ffprobe=False,
                )

    def test_build_ffprobe_must_match_recorded_executable_and_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "demo.mp4"
            path.write_bytes(self._mp4())
            ffprobe = self._ffprobe(root)
            provenance = {
                "video": {
                    "width": 1280,
                    "height": 720,
                    "audio_codec": "silent",
                    "duration_seconds": 20.0,
                }
            }
            runtime = {
                "ffprobe": {
                    "executable_sha256": "0" * 64,
                    "version": FFPROBE_VERSION,
                }
            }
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "differs from runtime assets"
            ):
                portfolio._validate_video(
                    path,
                    provenance,
                    ffprobe,
                    runtime,
                    require_recorded_ffprobe=True,
                )

    def test_ephemeral_detached_ssh_signature_round_trip_and_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "ephemeral"
            completed = subprocess.run(
                [
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "test only",
                    "-f",
                    str(key),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            key.chmod(0o600)
            public = root / "signing.pub"
            fields = (root / "ephemeral.pub").read_text(encoding="ascii").split()
            public.write_text(" ".join(fields[:2]) + " test\n", encoding="ascii")
            principal = "portfolio-test@example.invalid"
            policy = root / "allowed_signers"
            policy.write_text(
                principal + " " + " ".join(fields[:2]) + "\n", encoding="ascii"
            )
            fingerprint_output = subprocess.check_output(
                ["/usr/bin/ssh-keygen", "-E", "sha256", "-lf", str(public)],
                text=True,
            )
            fingerprint = next(
                token for token in fingerprint_output.split() if token.startswith("SHA256:")
            )
            payload = root / "payload.json"
            payload.write_bytes(_canonical({"test": True}))
            with (
                patch.object(portfolio, "EXPECTED_PUBLIC_KEY_SHA256", _sha256(public)),
                patch.object(portfolio, "EXPECTED_ALLOWED_SIGNERS_SHA256", _sha256(policy)),
                patch.object(portfolio, "EXPECTED_FINGERPRINT", fingerprint),
                patch.object(portfolio, "EXPECTED_SIGNING_PRINCIPAL", principal),
            ):
                portfolio._validate_trust(public, policy)
                signature = portfolio._sign_file(payload, key, policy, public)
                portfolio._verify_detached_signature(payload, signature, policy, public)
                payload.write_bytes(_canonical({"test": False}))
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "signature failed"
                ):
                    portfolio._verify_detached_signature(
                        payload, signature, policy, public
                    )

    def test_source_regression_contains_no_tag_creation_or_network_client(self):
        source = (ROOT / "publication" / "build_portfolio_release.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"tag", "-s"', source)
        self.assertNotIn("ls-remote", source)
        self.assertNotIn("urllib.request", source)
        self.assertIn("CORELM_PORTFOLIO_SIGNING_KEY", source)
        self.assertNotIn("--ci-api-preflight-confirmed", source)
        self.assertIn("_tag_ci_receipt_from_evidence", source)
        self.assertIn("refs/remotes/origin/main", source)
        self.assertIn("refs/remotes/origin/pull/5/head", source)


if __name__ == "__main__":
    unittest.main()
