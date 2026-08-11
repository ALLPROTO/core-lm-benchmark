import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from RealLLM import app_proof_runner as runner


SESSION_ID = "12345678-1234-4abc-8123-123456789abc"
RUNTIME_VECTOR = (
    Path(__file__).resolve().parents[1]
    / "platforms/macos/Tests/Fixtures/live-proof-event-v1-runtime.jsonl"
)
METRIC_VECTOR = (
    Path(__file__).resolve().parents[1]
    / "platforms/macos/Tests/Fixtures/live-proof-event-v1-metric.jsonl"
)


class PartialBinaryStream(io.BytesIO):
    def write(self, value):
        return super().write(value[:7])


class MachineOnlyStdout(io.TextIOBase):
    def __init__(self):
        super().__init__()
        self.buffer = io.BytesIO()

    def write(self, value):
        raise AssertionError(f"human text reached stdout: {value!r}")


def emit_prelude(
    writer: runner.LiveProofEventWriter,
    *,
    blocks: int = 1,
) -> None:
    writer.emit(
        "runtime_ready",
        {
            "device": "mps",
            "python": "3.12.13",
            "torch": "2.13.0",
            "transformers": "5.14.1",
        },
    )
    writer.emit(
        "assets_verified",
        {
            "model_repository": "Qwen/Qwen2.5-0.5B",
            "model_revision": "1" * 40,
            "model_weights_sha256": "2" * 64,
            "dataset_repository": "Salesforce/wikitext",
            "dataset_revision": "3" * 40,
            "dataset_sha256": "4" * 64,
            "split": "validation",
        },
    )
    writer.emit("model_load_started", {})
    writer.emit(
        "model_loaded_mps",
        {
            "model_repository": "Qwen/Qwen2.5-0.5B",
            "model_revision": "1" * 40,
            "device": "mps",
            "parameter_count": 494_032_768,
        },
    )
    writer.emit(
        "token_slice_selected_and_hashed",
        {
            "start_block": 64,
            "blocks": blocks,
            "tokens_per_block": 512,
            "selected_token_ids_sha256": "5" * 64,
        },
    )


def emit_block(
    writer: runner.LiveProofEventWriter,
    *,
    block_index: int,
    ordinal: int,
    total: int,
) -> int:
    writer.emit(
        "block_started",
        {
            "block_index": block_index,
            "ordinal": ordinal,
            "total": total,
        },
    )
    total_bytes = 0
    for layer_index in range(24):
        container_bytes = 90_000 + layer_index
        total_bytes += container_bytes
        writer.emit(
            "codec_roundtrip_written",
            {
                "block_index": block_index,
                "layer_index": layer_index,
                "bits": 9 if layer_index in {0, 8} else 8,
                "container_bytes": container_bytes,
                "container_sha256": f"{layer_index + 1:064x}",
            },
        )
    dense_bytes = 4_706_304
    writer.emit(
        "block_metrics_measured",
        {
            "block_index": block_index,
            "dense_bf16_bytes": dense_bytes,
            "encoded_file_bytes": total_bytes,
            "compression_ratio_vs_bf16": dense_bytes / total_bytes,
            "delta_nll_nat_per_token": -0.00001,
            "top1_agreement": 0.9921875,
            "prediction_tokens": 128,
        },
    )
    return total_bytes


class LiveProofEventTests(unittest.TestCase):
    def test_cross_language_runtime_vector_is_exact(self):
        raw = RUNTIME_VECTOR.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "45305fd25c114e9d896846f72fdabe7af990de80af758d36ed42a93fb36a17d0",
        )
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\n", raw[:-1])
        document = json.loads(raw)
        self.assertEqual(
            runner._canonical_live_event_bytes(document),
            raw[:-1],
        )
        self.assertEqual(
            hashlib.sha256(raw[:-1]).hexdigest(),
            "4877fbdbe0c88632deec0074bfe86eef602f334400c92558f3a453ffe20ed00e",
        )

    def test_cross_language_real_metric_vector_is_exact(self):
        raw = METRIC_VECTOR.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\n", raw[:-1])
        document = json.loads(raw)
        self.assertEqual(document["event"], "block_metrics_measured")
        self.assertEqual(
            runner._canonical_live_event_bytes(document),
            raw[:-1],
        )
        self.assertEqual(
            hashlib.sha256(raw[:-1]).hexdigest(),
            "39794328c52603ab7134807b1b5813af4505305eb863447c95065363100960a2",
        )

    def test_success_stream_is_exact_canonical_jsonl_and_hash_chained(self):
        stream = PartialBinaryStream()
        writer = runner.LiveProofEventWriter(SESSION_ID, stream)
        emit_prelude(writer)
        container_bytes = emit_block(
            writer,
            block_index=64,
            ordinal=1,
            total=1,
        )
        writer.emit(
            "primary_evidence_sealed",
            {
                "container_count": 24,
                "container_bytes": container_bytes,
                "blocks": 1,
                "prediction_tokens": 128,
                "manifest_sha256": "6" * 64,
            },
        )
        writer.emit(
            "result_sealed",
            {
                "result_sha256": "7" * 64,
                "output_filename": "validation-064-064.json",
            },
        )
        writer.emit("run_complete", {"passed": True})

        lines = stream.getvalue().splitlines(keepends=True)
        self.assertEqual(len(lines), 34)
        previous = runner.LIVE_EVENT_INITIAL_SHA256
        expected_base_keys = {
            "schema_version",
            "session_id",
            "sequence",
            "producer",
            "event",
            "facts",
            "previous_event_sha256",
        }
        for sequence, raw in enumerate(lines, start=1):
            self.assertTrue(raw.endswith(b"\n"))
            document = json.loads(raw)
            self.assertEqual(set(document), expected_base_keys)
            self.assertEqual(
                raw,
                runner._canonical_live_event_bytes(document) + b"\n",
            )
            self.assertEqual(document["schema_version"], runner.LIVE_EVENT_SCHEMA)
            self.assertEqual(document["session_id"], SESSION_ID)
            self.assertEqual(document["sequence"], sequence)
            self.assertEqual(document["producer"], "app_worker")
            self.assertEqual(document["previous_event_sha256"], previous)
            self.assertEqual(
                set(document["facts"]),
                runner.LIVE_EVENT_FACT_KEYS[document["event"]],
            )
            previous = hashlib.sha256(raw[:-1]).hexdigest()
        self.assertEqual(writer.previous_event_sha256, previous)
        self.assertEqual(writer.stage, "complete")

    def test_sequence_rejects_missing_duplicate_and_early_events(self):
        stream = io.BytesIO()
        writer = runner.LiveProofEventWriter(SESSION_ID, stream)
        with self.assertRaisesRegex(ValueError, "start with runtime_ready"):
            writer.emit("model_load_started", {})
        self.assertEqual(stream.getvalue(), b"")
        self.assertEqual(writer.sequence, 0)

        emit_prelude(writer)
        writer.emit(
            "block_started",
            {"block_index": 64, "ordinal": 1, "total": 1},
        )
        with self.assertRaisesRegex(ValueError, "preceded 24"):
            writer.emit(
                "block_metrics_measured",
                {
                    "block_index": 64,
                    "dense_bf16_bytes": 4_706_304,
                    "encoded_file_bytes": 2_290_000,
                    "compression_ratio_vs_bf16": 4_706_304 / 2_290_000,
                    "delta_nll_nat_per_token": 0.0,
                    "top1_agreement": 1.0,
                    "prediction_tokens": 128,
                },
            )
        with self.assertRaisesRegex(ValueError, "order changed"):
            writer.emit(
                "codec_roundtrip_written",
                {
                    "block_index": 64,
                    "layer_index": 1,
                    "bits": 8,
                    "container_bytes": 90_000,
                    "container_sha256": "8" * 64,
                },
            )

    def test_facts_are_exact_finite_and_internally_consistent(self):
        writer = runner.LiveProofEventWriter(SESSION_ID, io.BytesIO())
        with self.assertRaisesRegex(ValueError, "facts are not exact"):
            writer.emit(
                "runtime_ready",
                {
                    "device": "mps",
                    "python": "3.12.13",
                    "torch": "2.13.0",
                    "transformers": "5.14.1",
                    "extra": True,
                },
            )

        emit_prelude(writer)
        writer.emit(
            "block_started",
            {"block_index": 64, "ordinal": 1, "total": 1},
        )
        for layer_index in range(24):
            writer.emit(
                "codec_roundtrip_written",
                {
                    "block_index": 64,
                    "layer_index": layer_index,
                    "bits": 8,
                    "container_bytes": 90_000,
                    "container_sha256": "9" * 64,
                },
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            writer.emit(
                "block_metrics_measured",
                {
                    "block_index": 64,
                    "dense_bf16_bytes": 4_706_304,
                    "encoded_file_bytes": 2_290_000,
                    "compression_ratio_vs_bf16": float("nan"),
                    "delta_nll_nat_per_token": 0.0,
                    "top1_agreement": 1.0,
                    "prediction_tokens": 128,
                },
            )

    def test_container_callback_emits_only_after_parent_write(self):
        stream = io.BytesIO()
        events = runner.LiveProofEventWriter(SESSION_ID, stream)
        emit_prelude(events)
        events.emit(
            "block_started",
            {"block_index": 64, "ordinal": 1, "total": 1},
        )

        class ParentWriter:
            def __init__(self, directory, *, result_filename):
                self.directory = directory
                self.result_filename = result_filename
                self.writes = []

            def write_container(self, *, block_index, layer_index, container):
                self.writes.append((block_index, layer_index, container))

        core = SimpleNamespace(
            APP_CONFIGURATION={"bitsByLayer": [9] + [8] * 23},
            PrimaryEvidenceWriter=ParentWriter,
            sha256_bytes=lambda value: hashlib.sha256(value).hexdigest(),
        )
        evidence = runner._live_primary_evidence_writer(
            core,
            Path("primary-evidence"),
            result_filename="validation-064-064.json",
            live_events=events,
        )
        evidence.write_container(
            block_index=64,
            layer_index=0,
            container=b"VTL5-container",
        )

        self.assertEqual(evidence.writes, [(64, 0, b"VTL5-container")])
        last = json.loads(stream.getvalue().splitlines()[-1])
        self.assertEqual(last["event"], "codec_roundtrip_written")
        self.assertEqual(last["facts"]["layer_index"], 0)
        self.assertEqual(last["facts"]["bits"], 9)
        self.assertEqual(
            last["facts"]["container_sha256"],
            hashlib.sha256(b"VTL5-container").hexdigest(),
        )

        failed_stream = io.BytesIO()
        failed_events = runner.LiveProofEventWriter(SESSION_ID, failed_stream)
        emit_prelude(failed_events)
        failed_events.emit(
            "block_started",
            {"block_index": 64, "ordinal": 1, "total": 1},
        )

        class FailingParentWriter(ParentWriter):
            def write_container(self, *, block_index, layer_index, container):
                raise OSError("retained container write failed")

        failing_core = SimpleNamespace(
            APP_CONFIGURATION={"bitsByLayer": [9] + [8] * 23},
            PrimaryEvidenceWriter=FailingParentWriter,
            sha256_bytes=lambda value: hashlib.sha256(value).hexdigest(),
        )
        failing_evidence = runner._live_primary_evidence_writer(
            failing_core,
            Path("primary-evidence"),
            result_filename="validation-064-064.json",
            live_events=failed_events,
        )
        count_before = len(failed_stream.getvalue().splitlines())
        with self.assertRaisesRegex(OSError, "write failed"):
            failing_evidence.write_container(
                block_index=64,
                layer_index=0,
                container=b"VTL5-container",
            )
        self.assertEqual(
            len(failed_stream.getvalue().splitlines()),
            count_before,
        )
        self.assertEqual(failed_events.next_layer, 0)

    def test_stream_stall_does_not_advance_chain_or_state(self):
        class StalledStream:
            def write(self, value):
                return 0

            def flush(self):
                raise AssertionError("flush must not run after a stalled write")

        writer = runner.LiveProofEventWriter(SESSION_ID, StalledStream())
        with self.assertRaisesRegex(OSError, "made no progress"):
            writer.emit(
                "runtime_ready",
                {
                    "device": "mps",
                    "python": "3.12.13",
                    "torch": "2.13.0",
                    "transformers": "5.14.1",
                },
            )
        self.assertEqual(writer.sequence, 0)
        self.assertEqual(
            writer.previous_event_sha256,
            runner.LIVE_EVENT_INITIAL_SHA256,
        )
        self.assertEqual(writer.stage, "runtime_ready")

    def test_main_keeps_stdout_machine_only_and_summary_on_stderr(self):
        captured_stdout = MachineOnlyStdout()
        captured_stderr = io.StringIO()
        arguments = SimpleNamespace(
            output=Path("/tmp/validation-064-064.json"),
            device="mps",
            validation_start_block=64,
            validation_blocks=1,
            candidate_index=32,
            local_files_only=True,
            primary_evidence_directory=Path("/tmp/primary-evidence"),
            live_session_id=SESSION_ID,
        )

        def fake_run_app_proof(*args, live_events, **kwargs):
            emit_prelude(live_events)
            container_bytes = emit_block(
                live_events,
                block_index=64,
                ordinal=1,
                total=1,
            )
            live_events.emit(
                "primary_evidence_sealed",
                {
                    "container_count": 24,
                    "container_bytes": container_bytes,
                    "blocks": 1,
                    "prediction_tokens": 128,
                    "manifest_sha256": "6" * 64,
                },
            )
            live_events.emit(
                "result_sealed",
                {
                    "result_sha256": "7" * 64,
                    "output_filename": "validation-064-064.json",
                },
            )
            live_events.emit("run_complete", {"passed": True})
            return {
                "resultSHA256": "7" * 64,
                "aggregates": [
                    {
                        "configuration": {"schedule": "registered"},
                        "compressionRatioVsBF16": 2.05,
                        "deltaNLLNatPerToken": -0.00001,
                        "top1Agreement": 0.995,
                        "pass": True,
                    }
                ],
            }

        patches = (
            mock.patch.object(runner, "establish_worker_process_group", return_value=7),
            mock.patch.object(runner, "register_worker_process_group", return_value=None),
            mock.patch.object(runner, "parse_arguments", return_value=arguments),
            mock.patch.object(runner, "run_app_proof", side_effect=fake_run_app_proof),
            mock.patch.object(runner.sys, "stdout", captured_stdout),
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            redirect_stderr(captured_stderr),
        ):
            self.assertEqual(runner.main(), 0)

        lines = captured_stdout.buffer.getvalue().splitlines()
        self.assertEqual(len(lines), 34)
        self.assertTrue(all(isinstance(json.loads(line), dict) for line in lines))
        self.assertIn("Core LM app proof complete.", captured_stderr.getvalue())
        self.assertNotIn(b"Core LM app proof complete", captured_stdout.buffer.getvalue())

    def test_parser_requires_a_canonical_nonzero_live_session_uuid(self):
        common = [
            "--output",
            "/tmp/validation-064-064.json",
            "--device",
            "mps",
            "--validation-start-block",
            "64",
            "--validation-blocks",
            "1",
            "--candidate-index",
            "32",
            "--local-files-only",
            "--primary-evidence-directory",
            "/tmp/primary-evidence",
        ]
        parsed = runner.parse_arguments(
            common + ["--live-session-id", SESSION_ID]
        )
        self.assertEqual(parsed.live_session_id, SESSION_ID)

        for invalid in (
            None,
            SESSION_ID.upper(),
            "00000000-0000-0000-0000-000000000000",
            "not-a-uuid",
        ):
            arguments = list(common)
            if invalid is not None:
                arguments.extend(["--live-session-id", invalid])
            with self.subTest(invalid=invalid), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    runner.parse_arguments(arguments)


if __name__ == "__main__":
    unittest.main()
