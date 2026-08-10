import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAPER_TEST_TAG = "voidtoken-v5-paper-v5"
MISMATCHED_PAPER_TEST_TAG = "voidtoken-v5-paper-v9"

import publication.build_archives as archives  # noqa: E402
from security import generate_build_provenance as build_provenance  # noqa: E402


def _completed(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["git"],
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class PublicationArchiveTests(unittest.TestCase):
    def test_current_portfolio_schemas_pin_automation_only_v13_identity(self):
        release_input = json.loads(
            (ROOT / "schemas/portfolio-release-input.schema.json").read_text(
                encoding="utf-8"
            )
        )
        source_identity = json.loads(
            (ROOT / "schemas/portfolio-source-identity.schema.json").read_text(
                encoding="utf-8"
            )
        )
        demo_provenance = json.loads(
            (ROOT / "schemas/portfolio-demo-provenance.schema.json").read_text(
                encoding="utf-8"
            )
        )
        runtime_assets = json.loads(
            (ROOT / "schemas/portfolio-runtime-assets.schema.json").read_text(
                encoding="utf-8"
            )
        )

        for schema in (
            release_input,
            source_identity,
            demo_provenance,
            runtime_assets,
        ):
            self.assertEqual(schema["properties"]["schema_version"]["const"], 2)

        presentation = release_input["properties"]["presentation"]
        self.assertFalse(presentation["additionalProperties"])
        self.assertEqual(
            set(presentation["required"]), set(presentation["properties"])
        )
        expected_contract = {
            "automation_contract": "corelm-automated-presentation-v2",
            "classification": "AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE",
            "automation_only": True,
            "human_reviewed": False,
            "manual_edits": False,
            "machine_evidence": False,
            "pixel_semantics_verified": False,
            "independent_human_replication": False,
        }
        self.assertEqual(
            {
                key: descriptor["const"]
                for key, descriptor in presentation["properties"].items()
            },
            expected_contract,
        )

        demo = source_identity["properties"]["demo"]
        self.assertFalse(demo["additionalProperties"])
        self.assertIn("provenance_sha256", demo["required"])
        self.assertEqual(
            demo["properties"]["media_classification"]["const"],
            expected_contract["classification"],
        )
        self.assertEqual(
            demo["properties"]["automation_contract"]["const"],
            expected_contract["automation_contract"],
        )

        capture = demo_provenance["properties"]["capture"]
        self.assertFalse(capture["additionalProperties"])
        self.assertEqual(set(capture["required"]), set(capture["properties"]))
        self.assertEqual(
            capture["properties"]["mode"]["const"],
            "MACOS_SINGLE_WINDOW_ID_V1",
        )
        self.assertEqual(
            capture["properties"]["automation_receipt_sha256"]["$ref"],
            "#/$defs/sha256",
        )
        self.assertEqual(
            capture["properties"]["result_readiness_sha256"]["$ref"],
            "#/$defs/sha256",
        )
        self.assertEqual(
            demo_provenance["properties"]["video"]["properties"][
                "audio_codec"
            ]["const"],
            "silent",
        )

        capture_tools = runtime_assets["properties"]["capture_tools"]
        self.assertFalse(capture_tools["additionalProperties"])
        self.assertEqual(
            set(capture_tools["required"]), set(capture_tools["properties"])
        )
        self.assertEqual(
            capture_tools["properties"]["screencapture"]["properties"][
                "codesign_identifier"
            ]["const"],
            "com.apple.screencapture",
        )
        self.assertEqual(
            capture_tools["properties"]["window_helper"]["properties"][
                "source_sha256"
            ]["$ref"],
            "#/$defs/sha256",
        )
        self.assertIn("capture_tools", runtime_assets["required"])

    def test_archive_output_rejects_symlink_directory_and_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir(mode=0o700)
            linked_output = root / "linked-output"
            linked_output.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "output directory"):
                archives._safe_output_directory(linked_output)

            output = root / "output"
            output.mkdir(mode=0o700)
            outside_file = outside / "do-not-overwrite"
            outside_file.write_bytes(b"preserve me")
            linked_target = output / "SHA256SUMS"
            linked_target.symlink_to(outside_file)
            with self.assertRaisesRegex(ValueError, "target is unsafe"):
                with archives._atomic_output_path(linked_target):
                    pass
            self.assertEqual(outside_file.read_bytes(), b"preserve me")

    def test_current_software_and_historical_paper_identities_are_separate(self):
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version: "([^"]+)"$', citation)
        self.assertIsNotNone(match)
        release_tag = match.group(1)
        self.assertEqual(release_tag, "corelm-portfolio-v13")
        self.assertRegex(citation, r"(?m)^date-released: 2026-08-10$")

        for relative in (
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(f"RELEASE_TAG={PAPER_TEST_TAG}", text)

        manuscript = (
            ROOT / "publication/arxiv-v5/main.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(rf"\path{{{PAPER_TEST_TAG}}}", manuscript)

        sbom = json.loads(
            (
                ROOT / "security/direct-dependencies.cdx.json"
            ).read_text(encoding="utf-8")
        )
        component = sbom["metadata"]["component"]
        self.assertEqual(component["version"], release_tag)
        self.assertTrue(component["purl"].endswith(f"@{release_tag}"))
        self.assertEqual(sbom["dependencies"][0]["ref"], component["bom-ref"])

        identifiers = (
            ROOT / "docs/development/SCIENTIFIC_IDENTIFIERS.md"
        ).read_text(encoding="utf-8")
        self.assertIn("corelm-automated-presentation-v2", identifiers)
        self.assertIn("AUTOMATED_PRESENTATION_NOT_MACHINE_EVIDENCE", identifiers)
        self.assertIn("G10", identifiers)
        self.assertIn("**OPEN**", identifiers)

        with self.assertRaisesRegex(ValueError, "outside the historical paper contour"):
            archives._citation_release_tag()

    def test_v4_pre_model_failure_is_preserved_without_consuming_attempt(self):
        for relative in (
            "docs/DEMO.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v3", text)
                self.assertIn("corelm-portfolio-v4", text)
                self.assertIn("FFprobe frame-PTS", normalized)
                self.assertIn("AttemptLog.reserve", text)
                self.assertRegex(
                    normalized,
                    r"no (?:V4 )?model attempt (?:was )?(?:invoked or )?consumed",
                )
                self.assertIn("never", normalized.lower())

    def test_v5_github_id_failure_is_preserved_without_consuming_attempt(self):
        for relative in (
            "docs/DEMO.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v5", text)
                self.assertIn("corelm-portfolio-v13", text)
                self.assertIn("HTTP 403", normalized)
                self.assertIn("AttemptLog.reserve", text)
                self.assertRegex(normalized, r"(?:signed 32-bit|above `2\^31`)")
                self.assertRegex(
                    normalized,
                    r"no V5 model attempt was invoked or consumed",
                )
                self.assertIn("never", normalized.lower())

    def test_v6_pass_and_post_proof_executable_failure_are_preserved(self):
        for relative in (
            "docs/DEMO.md",
            "docs/ENGINEERING_CASE_STUDY.md",
            "docs/LIMITATIONS.md",
            "docs/PORTFOLIO_READINESS.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
            "publication/PORTFOLIO_RELEASE.md",
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v6", text)
                self.assertIn("corelm-portfolio-v13", text)
                self.assertIn("first-attempt tag CI", normalized)
                self.assertIn("2.052384x", normalized)
                self.assertIn("-0.00000846", normalized)
                self.assertIn("99.5117%", normalized)
                self.assertIn("1,024", normalized)
                self.assertIn("zero maximum loss error", normalized)
                self.assertIn("ATTEMPT_FAILED", text)
                self.assertIn("REPLAY_VERIFIED", text)
                self.assertIn("preflight-built", normalized)
                self.assertRegex(normalized, r"proof-(?:driver's )?rebuilt verified app")
                self.assertIn("same-run result", normalized.lower())
                self.assertIn("media sealing", normalized)
                self.assertIn("collection", normalized)
                self.assertIn("never", normalized.lower())

    def test_v7_through_v12_history_and_v13_fix_are_preserved(self):
        historical_documents = (
            "docs/DEMO.md",
            "docs/ENGINEERING_CASE_STUDY.md",
            "docs/LIMITATIONS.md",
            "docs/PORTFOLIO_READINESS.md",
            "docs/development/RELEASE_PROCESS.md",
            "docs/development/SCIENTIFIC_IDENTIFIERS.md",
            "publication/PORTFOLIO_RELEASE.md",
            "publication/README.md",
            "publication/reproducibility/README.md",
        )
        for relative in historical_documents:
            with self.subTest(document=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("corelm-portfolio-v7", text)
                self.assertIn("corelm-portfolio-v8", text)
                self.assertIn("corelm-portfolio-v9", text)
                self.assertIn("corelm-portfolio-v10", text)
                self.assertIn("corelm-portfolio-v11", text)
                self.assertIn("corelm-portfolio-v12", text)
                self.assertIn("three V7 runner invocations", normalized)
                self.assertIn("two", normalized.lower())
                self.assertIn("50%", normalized)
                self.assertIn("parallel Swift", normalized)
                self.assertIn(
                    "transient pre-marker public tag-CI admission failure",
                    normalized,
                )
                self.assertIn("8-response validation subsequently passed", normalized)
                self.assertIn("AttemptLog.reserve", text)
                self.assertIn("durable state and session remained absent", normalized)
                self.assertIn("no proof or model attempt was consumed", normalized)
                self.assertIn("Exactly one local V8 runner invocation", normalized)
                self.assertIn("first resource admission passed", normalized)
                self.assertIn("top-level `--jobs 1`", normalized)
                self.assertIn(
                    "observed Swift frontend argv",
                    normalized,
                )
                self.assertIn("retained `-num-threads 8`", normalized)
                self.assertIn(
                    "does not establish that the frontend setting caused",
                    normalized,
                )
                self.assertIn(
                    "second unchanged >=50% available-memory admission",
                    normalized,
                )
                self.assertIn(
                    "AUTOMATED PORTFOLIO DEMO FAIL: at least 50% available "
                    "memory is required",
                    normalized,
                )
                self.assertIn(
                    "durable state, session, and staging directory were absent",
                    normalized,
                )
                self.assertRegex(
                    normalized,
                    r"AttemptLog\.reserve` was never reached",
                )
                self.assertIn(
                    "no proof or model attempt was invoked or consumed",
                    normalized,
                )
                self.assertIn("no portfolio media was retained", normalized)
                self.assertIn("`-num-threads 1` pin", normalized)
                self.assertIn("without weakening the 50%", normalized)
                self.assertIn("exact produced app SHA", normalized)
                self.assertIn("does not claim byte-deterministic", normalized)
                self.assertIn("never", normalized.lower())
                for identity in (
                    "b1fc746e7f8a5bd1bf826d9f5219779d568fa0c4",
                    "3c9c5d64530e7c706dc1c9b9cf91d00c81a08a3d",
                    "64c9d84ddd8aa04b01459447b7c9f3f16f8f6db3",
                ):
                    self.assertIn(identity, text)
                for identity in (
                    "33d99db9a8cb239732910d96fc18dcaa43b78e3e",
                    "8fb25db8c54fc248e3b6c1b119fc06fb06be300f",
                    "ac69a22fef383f78634cda5e7256bca37e914acf",
                    "31335135716",
                    "31335135699",
                    "57a75c79-f37f-44b0-adc0-ba0762d200b0",
                    "eff033376bb6cc026c11c8a421da3a8834d78b1a4a7ab34580304c86d0646fce",
                    "5814eac71b5d2fb9ecd940a2aef09bfec9722a6d86a85a95ec230f7334c5514a",
                ):
                    self.assertIn(identity, text)
                self.assertIn("Exactly one V9 attempt was consumed", normalized)
                self.assertIn("Proof and replay passed", normalized)
                for metric in (
                    "2.0523837550538349x",
                    "-8.4598101111055257e-06",
                    "0.9951171875",
                    "1,024/1,024",
                    "maximum errors 0",
                ):
                    self.assertIn(metric, normalized)
                self.assertIn(
                    "ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → "
                    "REPLAY_VERIFIED PASS → POST_PROOF_PRESENTATION_SURFACE_READY "
                    "→ ATTEMPT_FAILED",
                    normalized,
                )
                self.assertIn(
                    "The exact terminal PTY line was `AUTOMATED PORTFOLIO DEMO "
                    "FAIL: post-proof presentation capture failed: raw capture "
                    "segment duration/topology is invalid`",
                    normalized,
                )
                self.assertIn("partial MOV SHA-256", normalized)
                self.assertIn("one frame, 0.028333 seconds, 2400x1540", normalized)
                for cause in (
                    "display off at 23:00:00",
                    "idle sleep at 23:00:30",
                    "DarkWake at 23:01:36",
                    "maintenance sleep at 23:01:42",
                    "human wake at 23:09:18",
                    "finalization at 23:09:19",
                    "app remained alive",
                    "launcher lacked a display/system-sleep assertion",
                ):
                    self.assertIn(cause, normalized)
                self.assertIn(
                    "No result capture/readiness asset, final media, automation "
                    "receipt, or release was produced",
                    normalized,
                )
                for identity in (
                    "bb53cd81d9e9ece92a078d823e6bf07474ff762b",
                    "d840e2a2112fc5ee0cdae0c1f0bf1e5fb2c875da",
                    "27419a0b91934bd76d430ac7c0eadf073389e26c",
                    "31338205386",
                    "31338205397",
                    "7cad5bc5-57dd-4778-b00f-528ae3ba7936",
                    "2fe562b4026bbbda3944d194e05f9ce20a4ebfebbccf58c769a53a198e13cd24",
                    "2183f16f2f81584a7c13a05a2509df4f1b7bbc2a445edcb34fa77d532ace7ee2",
                    "3d6e2cda34e5c0a044c93a28d41160161920cdc75b887e16e7718968760ae22e",
                    "e761c829f153411f6cd2f7b28cbed2d7a6770da24c4450c18c0a110f07c3dc10",
                    "07c076d38fe3500011526df2a19441fd771b98875fb42f1e76a164881931cdca",
                    "e353625bbc923916a07746a9cc7cdfca0579f06e5baae36088c09b37b255dc6a",
                    "10222e090bb6fa9d10a5443b3879337141ce225dc666ae5dcbc4c159705b0646",
                    "9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153",
                    "d47be9cb975767b5a6f89c0e54d66f5182675c3a0e871245f2838170e8708a61",
                ):
                    self.assertIn(identity, text)
                self.assertIn("Exactly one V10 attempt was consumed", normalized)
                self.assertIn("sole proof and heavy replay passed", normalized)
                for metric in (
                    "2.0523837550538349x",
                    "-8.4598101111055257e-06",
                    "0.9951171875",
                    "1,024/1,024",
                    "maximum errors 0",
                ):
                    self.assertIn(metric, normalized)
                self.assertIn(
                    "ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → "
                    "REPLAY_VERIFIED PASS → POST_PROOF_PRESENTATION_SURFACE_READY "
                    "→ POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → "
                    "RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION",
                    normalized,
                )
                self.assertIn("All three raw", normalized)
                self.assertIn("bound in the automation receipt", normalized)
                self.assertIn("independent ffprobe", normalized.lower())
                self.assertIn("full decode passed", normalized)
                self.assertIn("30-second, 900-frame 1280x720", normalized)
                self.assertIn(
                    "PORTFOLIO DEMO COLLECTION FAIL: demo MP4 has a truncated "
                    "atom header",
                    normalized,
                )
                self.assertIn("false reject", normalized)
                self.assertIn("valid nonempty `avcC`", normalized)
                self.assertIn("exactly four NUL padding bytes", normalized)
                self.assertIn("generic", normalized.lower())
                self.assertIn("Top-level atoms ended exactly at EOF", normalized)
                self.assertIn("cannot be remuxed, trimmed, or replaced", normalized)
                self.assertIn(
                    "V10 inputs directory, fourteen-asset directory, and GitHub "
                    "Release remained absent",
                    normalized,
                )
                self.assertIn("V11", normalized)
                self.assertIn("only at the end of an `avc1` child region", normalized)
                self.assertIn("nonzero", normalized)
                self.assertIn("wrong-length", normalized)
                self.assertIn("missing-`avcC`", normalized)
                self.assertIn("sole proof", normalized)
                self.assertIn("/usr/bin/caffeinate -dis", text)
                self.assertIn("full sterile runner lifetime", normalized)
                for forbidden_option in ("`-u`", "`-t`", "`-w`"):
                    self.assertIn(forbidden_option, text)
                self.assertIn("unavailable wrapper failed before the attempt marker", normalized)
                self.assertIn("corelm-automated-presentation-v2", text)
                for identity in (
                    "0071b1c9cbfffdb591a103fcc836a250d3d405e1",
                    "4fb72d1dd73b8824f77f562620c16aa6481fc6a4",
                    "2bddc12667f3fac6901f982969003b38abcc3d3e",
                    "31371667051",
                    "31371667048",
                    "6bc357a8-4fc6-4f7c-b73f-0718af818952",
                    "9c24a9c629f43b114ddc3766718079a0ba6b7160ff98e0d2c8339a6b53d6d61c",
                    "635a1347ae93365ab5c03e14c56f329938d4164e353fe5b65690ccdd9a6f4675",
                    "0192341765bf5e30f9a103e5b2b39d46d3eb35278a942b51d1747055ebf3b9fb",
                    "a569802b3a7c76a5ca7283b56227b0730c5f420b80c4d8f2cfb49b727ab78805",
                    "ca671a98c4476de5db1927bf2114693e9901aa96335642b227e55024924dd80d",
                    "f99b32ce5e47cf26c1abe784c7b992fc448aa3f8faadbfe8432d7baca17def20",
                    "6d9363fee0a84967a4b9ba474743d8d1a5501f3ce7c53fecf57eb0fd65fd6241",
                    "356b96e96d2310cb561ed96bc0246428e30bdcd7ac32ac49e47d0d4d7a014169",
                    "1661a2c7e087087de3848518eae9c95809c3ea5b10361a50f7817061844ef848",
                    "bb7caa9c0874ac17d259de25ac952f13c9cd832b8dd83bceba94d30772ffe744",
                    "7270ca303e891bdd6aaac18a50a518209c7365f794869bb5a974cc5e111f784d",
                    "9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153",
                    "6e5c774b9f6adba9cd5fe68681a246f01a3f7163aac428f36dff29affb9c5919",
                    "6e64ff46721b81f8c45e1dfbbac41a6b7595ec8d5b4e101128bbc2f27860ee91",
                    "131953d94a53bd26e5b8d624267df7c88ee96c96cf86671511eaedd07e597ecc",
                ):
                    self.assertIn(identity, text)
                for exact_fact in (
                    "2.0523837550538349x",
                    "-8.4598101111055257e-06",
                    "0.9951171875",
                    "1,024/1,024",
                    "maximum errors 0",
                    "PORTFOLIO DEMO COLLECTION FAIL: final video bytes are not "
                    "the exact raw composition",
                    "byte-distinct",
                    "user_data_unregistered",
                    "decoded framemd5",
                ):
                    self.assertIn(exact_fact, normalized)
                self.assertIn(
                    "ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL PASS → "
                    "REPLAY_VERIFIED PASS → POST_PROOF_PRESENTATION_SURFACE_READY "
                    "→ POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → "
                    "RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION",
                    normalized,
                )
                self.assertRegex(normalized, r"inputs(?: directory)?(?:,|/)?.*assets")
                self.assertRegex(normalized, r"(?:GitHub Release|release absent)")
                self.assertIn("exact frame count", normalized)
                self.assertIn("PTS", normalized)
                self.assertIn(
                    "strict per-frame SHA-256 framemd5 manifest",
                    normalized,
                )
                self.assertIn("MD5", normalized)
                self.assertIn("malformed manifests are rejected", normalized)
                self.assertRegex(normalized, r"decoded(?:-frame| frames)")
                self.assertIn("poster", normalized)
                self.assertIn("V12", normalized)
                self.assertIn("corelm-portfolio-v13", text)
                for identity in (
                    "6e49fc14244230227ed08820cdd295c28bf0e7ca",
                    "9c6c4e5cf050d3a882faeaf8dfc55e7b94c70ee6",
                    "f6166661047cb753e3a63230311fdd69bf357b80",
                    "31379694116",
                    "31379694145",
                    "c42fdea1-d0d5-49b9-aed3-f44e0549c061",
                    "014485f16de4f6ca2d7fd9f9b8472a6ee58fcd7338fee6953b91f272d1cad93a",
                    "12ab1cbdd6a18b3dc0245d17c52eb2ebe925ebebfbef156d198f1c210afb3f44",
                    "76d0f757faacbd92a20eda265a363ebcb7d5bf1f633951c4f46ab2922b5e50a4",
                    "3aec174dfbc1f40a5176cf8b021346dc9045baad6450812ea1858b1fd6a02f9c",
                    "cc59a374376c2562d0c76db10ebf055671033fbcf88ea5043efb171d34537d50",
                    "4346bf3a8a9037481d6a99ef27180f81f6bad6b836e44b82a7bf8f68b543933e",
                    "70fc0f97b3a4e0317667728deaa23e4758390c93617d9185caa534bf28a41654",
                    "268013e6ac671b85ebac2d39fe9dce3b52d96f81378b8512c0a347560e633538",
                    "2d3f0c00d2e7122b2d5b02c99e45be7e94e7332a588caf488df9266501446a40",
                    "526130332ee358c52980cc339530ad1e67dc2e2e144d0b26779ae1b582f80dea",
                    "f4217d69b4b715e61e4f2e5c3fca937a61117dbb1daf26a0f3b919da3a450a4f",
                    "a311d0b25102d5eb1ce00e56ba98976f95071653e9ef97661ca43ae056244c04",
                    "9a5c0b20f1042d8a05df930c927b87b3676b0ec932474807356c140b5d36c153",
                    "96f940fed8d0470dae697133a8f191322a590798de4fd78bfa6b7a8980c2ddde",
                    "1e648042f78433a7c952dd266d3e07480ce0a2a966eab346c21897e47f82b469",
                    "accb52ae54b4e5ec279cc3c9456de0fdd1a665750c4e495e559d10c6e5915216",
                    "bdf6c6d6e961b863d4b38df866e3b673cae5476cea6196df0f3875535bbae919",
                    "479d7547b455adecaf8fa42ec47e04581994f13096346b82f40429b3fa5b2e5f",
                    "c337cb166b44d567937d88bfebeaedb2dadaf18e5b5d1ab4a4a0a9492ae9305c",
                    "dc1cb5436e87816a357c8cb88c3a8a590bcfdf2861af2df4fdc0dfeb2b85c5ce",
                ):
                    self.assertIn(identity, text)
                for exact_fact in (
                    "first local V12 runner invocation failed at tag-CI admission",
                    "Exactly one later V12 attempt was consumed",
                    "END-TO-END PROOF PASS",
                    "2.0523837550538349x",
                    "-8.4598101111055257e-06",
                    "0.9951171875",
                    "1,024/1,024",
                    "zero maximum baseline/candidate loss error",
                    "57 frames",
                    "681 frames",
                    "1,024 frames",
                    "exactly fourteen signed local assets",
                    "HTTP 422: Cannot upload assets to an immutable release.",
                    "There was no partial upload, retry, deletion, metadata edit, retag, rerun, reuse, or relabel",
                    "V12 GitHub Release contract is a terminal FAIL",
                    "public V12 release remains empty and immutable",
                    "No conforming fourteen-asset GitHub release receipt was produced.",
                    "prepare-draft",
                    "verify-policy",
                    "verify-empty-draft",
                    "verify-draft",
                    "precreate",
                    "prepublish",
                    "logged-out final verification binds by-ID, by-tag, latest, and all downloads",
                    "there is no delete/recreate, retry, retag, or V12 relabel",
                ):
                    self.assertIn(exact_fact, normalized)
                self.assertNotIn("seven-stage", normalized)
                self.assertIn(
                    "ATTEMPT_STARTED → PROOF_INVOKED → PROOF_TERMINAL → "
                    "REPLAY_VERIFIED → POST_PROOF_PRESENTATION_SURFACE_READY → "
                    "POST_PROOF_PRESENTATION_CAPTURED → SAME_RUN_REOPENED → "
                    "RESULT_CAPTURED → MEDIA_SEALED_FOR_COLLECTION",
                    normalized,
                )
                self.assertIn("`draft:true`", text)
                self.assertIn("`prerelease:false`", text)
                self.assertIn("`immutable:false`", text)
                self.assertIn("`published_at:null`", text)
                self.assertIn("`make_latest:\"true\"`", text)
                self.assertIn(
                    "A separate authenticated `/releases/latest` GET then returned "
                    "the same ID `367936819`",
                    normalized,
                )

        exact_documents = (
            "docs/DEMO.md",
            "docs/development/RELEASE_PROCESS.md",
            "publication/PORTFOLIO_RELEASE.md",
        )
        for relative in exact_documents:
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(exact_identity_document=relative):
                for identity in (
                    "8d53e43208f76141a01bb2c0914459fbc101e7d5",
                    "ea82aa490c008d8560a6d44a70407d8d5e33bdbc",
                    "2c82497617173e3dfd965502860082ab5bf98130",
                    "31328178519",
                    "31328178525",
                ):
                    self.assertIn(identity, text)

    def test_v13_github_runbook_has_disjoint_fail_closed_path_topology(self):
        text = (ROOT / "publication/PORTFOLIO_RELEASE.md").read_text(
            encoding="utf-8"
        )
        section = text.split("## Exact GitHub publication contract", 1)[1]
        section = section.split("## Presentation successor after publication", 1)[0]

        required = (
            'REQUESTS="$PUBLICATION_ROOT/requests"',
            'API_INPUTS="$PUBLICATION_ROOT/api-inputs"',
            'RECEIPTS="$PUBLICATION_ROOT/receipts"',
            'DOWNLOADED="$PUBLICATION_ROOT/downloaded-assets"',
            'CREATE_REQUEST="$REQUESTS/create-draft.json"',
            'CREATE_RESPONSE="$API_INPUTS/create-response.json"',
            'EMPTY_DRAFT_RECEIPT="$RECEIPTS/empty-draft.json"',
            'POPULATED_DRAFT_RECEIPT="$RECEIPTS/populated-draft.json"',
            'PRECREATE_IMMUTABLE_POLICY="$API_INPUTS/precreate-immutable-policy.json"',
            'PRECREATE_POLICY_RECEIPT="$RECEIPTS/precreate-policy.json"',
            'PREPUBLISH_IMMUTABLE_POLICY="$API_INPUTS/prepublish-immutable-policy.json"',
            'PUBLISH_REQUEST="$REQUESTS/publish.json"',
            'gh release upload "$TAG" "$asset"',
            '--repo ALLPROTO/core-lm-benchmark',
            '> "$API_INPUTS/draft-by-id.json"',
            '> "$API_INPUTS/release-publish-response.json"',
            'RECEIPT="$RECEIPTS/final-public-release.json"',
            '--receipt "$POPULATED_DRAFT_RECEIPT"',
            'verify_portfolio_github_release.py verify-policy',
            '--immutable-policy-json "$PRECREATE_IMMUTABLE_POLICY"',
            '--receipt "$PRECREATE_POLICY_RECEIPT"',
            '--immutable-policy-json "$PREPUBLISH_IMMUTABLE_POLICY"',
            '--release-id-json "$API_INPUTS/public-release-by-id.json"',
            '--release-tag-json "$API_INPUTS/public-release-by-tag.json"',
            '`immutable:true`; `immutable:false`, a missing value, or disagreement is a hard',
        )
        for exact in required:
            with self.subTest(exact=exact):
                self.assertIn(exact, section)
        self.assertGreaterEqual(section.count("set -eu"), 4)
        self.assertNotIn("/absolute/operator-log", section)
        self.assertNotIn("--hostname uploads.github.com", section)
        self.assertNotIn("$UPLOAD_RESPONSES", section)
        self.assertEqual(section.count('gh release upload "$TAG" "$asset"'), 1)
        self.assertLess(
            section.index('> "$PRECREATE_IMMUTABLE_POLICY"'),
            section.index('gh api --method POST'),
        )
        self.assertLess(
            section.index('> "$PREPUBLISH_IMMUTABLE_POLICY"'),
            section.index('verify_portfolio_github_release.py verify-draft'),
        )
        self.assertLess(
            section.index('verify_portfolio_github_release.py verify-draft'),
            section.index('gh api --method PATCH'),
        )
        self.assertLess(section.index("TAG_OBJECT=$("), section.index("draft-tag-object.json"))
        self.assertLess(
            section.index("SOURCE_COMMIT=$("),
            section.index("draft-commit-object.json"),
        )
        self.assertIn(
            'empty <= 0 or populated != empty',
            section,
        )
        self.assertNotIn('${RELEASE_ID:?', section)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parents = {
                "requests": root / "requests",
                "api_inputs": root / "api-inputs",
                "receipts": root / "receipts",
                "downloaded": root / "downloaded-assets",
                "assets": root / "signed-assets",
            }
            self.assertEqual(len(set(parents.values())), len(parents))
            for path in parents.values():
                path.mkdir()
            self.assertTrue(all(path.is_dir() for path in parents.values()))

        shell_blocks = re.findall(r"```sh\n(.*?)\n```", section, flags=re.DOTALL)
        self.assertGreaterEqual(len(shell_blocks), 4)
        self.assertNotIn("--clobber", "\n".join(shell_blocks))
        for index, block in enumerate(shell_blocks):
            with self.subTest(shell_block=index):
                parsed = subprocess.run(
                    ["/bin/zsh", "-n"],
                    input=block,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(parsed.returncode, 0, parsed.stderr)

    def test_current_publication_readmes_close_beacon_without_overclaim(self):
        evidence_commit = "85c2add1799652a818873a04310b75821728da11"
        for relative in (
            "real-llm-beacon-results/README.md",
            "publication/README.md",
            "publication/reproducibility/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            normalized = " ".join(text.split())
            self.assertIn(evidence_commit, text)
            self.assertIn("terminal **PASS**", text)
            self.assertIn("suite is consumed", normalized.lower())
            self.assertNotIn("suite has no result yet", normalized.lower())
            self.assertNotIn(
                "target pulse has not produced a checked-in result",
                normalized.lower(),
            )
            self.assertNotIn(
                "exactly one recorded execution is permitted",
                normalized.lower(),
            )

    def _phase_paths(self, root: Path) -> dict[str, Path]:
        return {
            "selectionAttempt": root / "selection.attempt.json",
            "selectionResult": root / "selection.json",
            "holdoutAttempt": root / "holdout.attempt.json",
            "holdoutResult": root / "holdout.json",
        }

    def _write_json(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_submission_metadata_discloses_historical_accounting_limit(self):
        metadata = (
            ROOT / "publication/arxiv-v5/submission_metadata.md"
        ).read_text(encoding="utf-8")
        self.assertIn("73,346,513 runner-recorded bytes", metadata)
        self.assertIn("not independently reconstructible", metadata)
        self.assertNotIn("73,346,513 bytes (2.05329x", metadata)

    def test_v5_evidence_state_accepts_every_terminal_or_pending_state(self):
        cases = [
            ("registration-only", {}),
            ("selection-consumed-incomplete", {"selectionAttempt": {}}),
            (
                "selection-fail-terminal",
                {"selectionAttempt": {}, "selectionResult": {"pass": False}},
            ),
            (
                "selection-pass-awaiting-holdout",
                {"selectionAttempt": {}, "selectionResult": {"pass": True}},
            ),
            (
                "holdout-consumed-incomplete",
                {
                    "selectionAttempt": {},
                    "selectionResult": {"pass": True},
                    "holdoutAttempt": {},
                },
            ),
            (
                "holdout-pass",
                {
                    "selectionAttempt": {},
                    "selectionResult": {"pass": True},
                    "holdoutAttempt": {},
                    "holdoutResult": {"pass": True},
                },
            ),
            (
                "holdout-fail",
                {
                    "selectionAttempt": {},
                    "selectionResult": {"pass": True},
                    "holdoutAttempt": {},
                    "holdoutResult": {"pass": False},
                },
            ),
        ]
        for expected, files in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as temporary:
                    paths = self._phase_paths(Path(temporary))
                    for name, value in files.items():
                        self._write_json(paths[name], value)
                    with patch.object(
                        archives, "V5_PHASE_PATHS", paths
                    ):
                        state, included = archives._v5_evidence_state()
                    self.assertEqual(state, expected)
                    self.assertEqual(len(included), len(files))

    def test_v5_evidence_state_rejects_invalid_permutations(self):
        cases = [
            {"selectionResult": {"pass": True}},
            {"holdoutAttempt": {}},
            {
                "selectionAttempt": {},
                "selectionResult": {"pass": False},
                "holdoutAttempt": {},
            },
            {
                "selectionAttempt": {},
                "selectionResult": {"pass": True},
                "holdoutResult": {"pass": True},
            },
        ]
        for files in cases:
            with self.subTest(files=tuple(files)):
                with tempfile.TemporaryDirectory() as temporary:
                    paths = self._phase_paths(Path(temporary))
                    for name, value in files.items():
                        self._write_json(paths[name], value)
                    with (
                        patch.object(archives, "V5_PHASE_PATHS", paths),
                        self.assertRaises(ValueError),
                    ):
                        archives._v5_evidence_state()

    def _fake_git(self, responses):
        def invoke(*arguments, check=True):
            response = responses.get(tuple(arguments))
            if response is None:
                self.fail(f"unexpected git call: {arguments}")
            if check and response.returncode:
                raise ValueError("simulated git failure")
            return response

        return invoke

    def _base_release_responses(self, *, dirty: bool = False):
        return {
            ("rev-parse", "--show-toplevel"): _completed(f"{ROOT}\n"),
            ("rev-parse", "HEAD"): _completed("a" * 40 + "\n"),
            ("rev-parse", "HEAD^{tree}"): _completed("b" * 40 + "\n"),
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=no",
            ): _completed(" M README.md\n" if dirty else ""),
            ("ls-files", "-z"): _completed("README.md\0"),
        }

    def test_release_preflight_rejects_dirty_worktree(self):
        responses = self._base_release_responses(dirty=True)
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "clean worktree"),
        ):
            archives._build_context(PAPER_TEST_TAG)

    def test_release_preflight_rejects_portfolio_tag_as_wrong_contour(self):
        responses = self._base_release_responses()
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            self.assertRaisesRegex(ValueError, "SSH-signed replication contour"),
        ):
            archives._build_context("corelm-portfolio-v2")

    def test_release_preflight_rejects_arbitrary_lightweight_tag_name(self):
        responses = self._base_release_responses()
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            self.assertRaisesRegex(ValueError, "historical paper contour"),
        ):
            archives._build_context("v0.4.0")

    def test_release_preflight_rejects_tag_that_disagrees_with_citation(self):
        responses = self._base_release_responses()
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "CITATION.cff version"),
        ):
            archives._build_context(MISMATCHED_PAPER_TEST_TAG)

    def test_release_preflight_rejects_annotated_tag(self):
        responses = self._base_release_responses()
        responses[("cat-file", "-t", f"refs/tags/{PAPER_TEST_TAG}")] = _completed(
            "tag\n"
        )
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "lightweight"),
        ):
            archives._build_context(PAPER_TEST_TAG)

    def test_release_preflight_checks_origin_and_remote_tag(self):
        responses = self._base_release_responses()
        reference = f"refs/tags/{PAPER_TEST_TAG}"
        responses[("cat-file", "-t", reference)] = _completed("commit\n")
        responses[
            ("rev-parse", "--verify", f"{reference}^{{commit}}")
        ] = _completed("a" * 40 + "\n")
        responses[("remote", "get-url", "origin")] = _completed(
            archives.PUBLIC_ORIGIN + ".git\n"
        )
        responses[
            ("ls-remote", "--exit-code", "origin", reference)
        ] = _completed(f"{'a' * 40}\t{reference}\n")
        with (
            patch.object(archives, "_git", side_effect=self._fake_git(responses)),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
        ):
            context = archives._build_context(PAPER_TEST_TAG)
        self.assertEqual(context["buildMode"], "clean-public-tag-release")
        self.assertTrue(context["remoteTagVerified"])
        self.assertEqual(
            context["releaseContour"],
            archives.HISTORICAL_PAPER_ARCHIVE_CONTOUR,
        )

        wrong_origin = dict(responses)
        wrong_origin[("remote", "get-url", "origin")] = _completed(
            "https://github.com/example/wrong.git\n"
        )
        with (
            patch.object(
                archives,
                "_git",
                side_effect=self._fake_git(wrong_origin),
            ),
            patch.object(
                archives, "_citation_release_tag", return_value=PAPER_TEST_TAG
            ),
            self.assertRaisesRegex(ValueError, "origin"),
        ):
            archives._build_context(PAPER_TEST_TAG)

    def test_release_documentation_separates_paper_and_portfolio_tags(self):
        publication = (ROOT / "publication/README.md").read_text(
            encoding="utf-8"
        )
        replication = (ROOT / "docs/INDEPENDENT_REPLICATION.md").read_text(
            encoding="utf-8"
        )
        release_process = (
            ROOT / "docs/development/RELEASE_PROCESS.md"
        ).read_text(encoding="utf-8")
        for document in (publication, replication, release_process):
            self.assertIn("voidtoken-v5-paper-vN", document)
            self.assertIn("corelm-portfolio-vN", document)
        self.assertIn("lightweight historical paper", publication)
        self.assertIn("SSH-signed annotated portfolio", publication)
        self.assertIn("historical `CITATION.cff` names the same paper tag", publication)
        self.assertIn("current default branch", publication)
        self.assertIn("differs from `CITATION.cff`", publication)
        self.assertIn("must not be passed to", replication)
        self.assertIn("SSH-signed annotated", release_process)
        self.assertIn("never pass a portfolio tag", release_process)
        self.assertIn("presentation-only C1", release_process)
        self.assertIn("signed linear C2", release_process)
        self.assertIn("new tagged regression proof", release_process)
        self.assertIn("canonical `TMPDIR`", release_process)

    def test_release_source_must_be_tracked(self):
        context = {
            "releaseTag": PAPER_TEST_TAG,
            "trackedFiles": set(),
        }
        with self.assertRaisesRegex(ValueError, "not tracked"):
            archives._assert_release_source(ROOT / "README.md", context)

    def test_reproducibility_archive_contains_v5_evidence_and_provenance(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            archive = archives.build_reproducibility(
                Path(temporary), context
            )
            with tarfile.open(archive, "r:gz") as bundle:
                names = set(bundle.getnames())
                prefix = "corelm_reproducibility"
                self.assertIn(f"{prefix}/PROVENANCE.json", names)
                self.assertIn(
                    f"{prefix}/SOURCE_ARCHIVE_PROVENANCE.json", names
                )
                archive_provenance_member = bundle.extractfile(
                    f"{prefix}/SOURCE_ARCHIVE_PROVENANCE.json"
                )
                self.assertIsNotNone(archive_provenance_member)
                archive_provenance_raw = archive_provenance_member.read()
                archive_provenance = json.loads(archive_provenance_raw)
                self.assertEqual(
                    archive_provenance_raw,
                    archives.canonical_json_bytes(archive_provenance),
                )
                self.assertEqual(
                    archive_provenance["schemaVersion"],
                    "corelm-source-archive-manifest-v1",
                )
                archived_source_paths = {
                    entry["path"] for entry in archive_provenance["files"]
                }
                self.assertIn(
                    "platforms/macos/scripts/package-app.sh",
                    archived_source_paths,
                )
                self.assertIn(
                    "RealLLM/legacy_voidtoken_adapter.py",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/generate_build_provenance.py",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/validate_python_bootstrap_archive.py",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/proof_process_groups.sh",
                    archived_source_paths,
                )
                self.assertIn(
                    "security/run_process_group_tests.sh",
                    archived_source_paths,
                )
                self.assertIn("signing/allowed_signers", archived_source_paths)
                self.assertIn(
                    "signing/corelm-codec-signing.pub",
                    archived_source_paths,
                )
                provenance_member = bundle.extractfile(
                    f"{prefix}/PROVENANCE.json"
                )
                self.assertIsNotNone(provenance_member)
                provenance = json.load(provenance_member)
                evidence_paths = {
                    entry["path"] for entry in provenance["evidenceFiles"]
                }
                self.assertTrue(
                    {
                        "app-real-llm-evidence/validation-064-071.json",
                        "app-real-llm-evidence/app-run-receipt.json",
                        "app-real-llm-evidence/SHA256SUMS",
                    }.issubset(evidence_paths)
                )
                self.assertIn(
                    f"{prefix}/real-llm-v5-development/manifest.json",
                    names,
                )
                self.assertIn(
                    f"{prefix}/RealLLM/verify_voidtoken_v5_development.py",
                    names,
                )
                self.assertIn(
                    f"{prefix}/publication/arxiv-v5/generate_figures.py",
                    names,
                )
                for relative in (
                    "corelm",
                    "platforms/README.md",
                    "platforms/beacon/README.md",
                    "platforms/beacon/scripts/verify-frozen-tag.py",
                    "platforms/macos/scripts/build-app.sh",
                    "platforms/macos/scripts/bootstrap-python.sh",
                    "platforms/macos/scripts/doctor.sh",
                    "platforms/macos/scripts/prepare-offline.sh",
                    "platforms/macos/scripts/find-proof-window.swift",
                    "platforms/macos/scripts/run-automated-portfolio-demo.py",
                    "platforms/macos/scripts/run-proof.sh",
                    "platforms/macos/BUILD_AND_VERIFY.md",
                    "platforms/linux/scripts/bootstrap-python.sh",
                    "platforms/linux/scripts/doctor.sh",
                    "platforms/linux/scripts/find-python312.sh",
                    "platforms/linux/scripts/build-runtime.sh",
                    "platforms/linux/scripts/runtime_safety.py",
                    "platforms/linux/scripts/run-regression.sh",
                    "platforms/linux/RECORDED_RUN_2026-08-01.md",
                    "scripts/verify-python.sh",
                    "requirements.lock",
                    "RealLLM/requirements.lock",
                    "RealLLM/prepare_app_assets.py",
                    "docs/README.md",
                    "docs/DEMO.md",
                    "docs/ENGINEERING_CASE_STUDY.md",
                    "docs/INDEPENDENT_REPLICATION.md",
                    "docs/PORTFOLIO_READINESS.md",
                    "docs/RESULTS.md",
                    "docs/LIMITATIONS.md",
                    "docs/independent-replication-attestation.template.json",
                    "docs/development/BEACON_V1_AUDIT_AND_V2.md",
                    "docs/development/HISTORY.md",
                    "docs/development/SCIENTIFIC_IDENTIFIERS.md",
                    "docs/development/RELEASE_PROCESS.md",
                    "SECURITY.md",
                    "platforms/macos/App/Sources/PrimaryEvidenceValidation.swift",
                    "platforms/macos/App/Sources/PythonRuntimeManifest.swift",
                    "platforms/macos/App/Sources/SecurityValidation.swift",
                    "platforms/macos/Tests/SecurityValidationTests.swift",
                    "Tests/test_platform_boundaries.py",
                    "Tests/test_automated_media.py",
                    "Tests/test_automated_portfolio_demo.py",
                    "Tests/test_automated_window_capture.py",
                    "Tests/test_strict_git_checkout.py",
                    "Tests/test_portfolio_demo_collector.py",
                    "Tests/test_portfolio_python_launcher.py",
                    "Tests/test_portfolio_release.py",
                    "Tests/test_portfolio_tag_ci.py",
                    "security/generate_python_runtime_manifest.py",
                    "security/generate_build_provenance.py",
                    "security/find_python312.sh",
                    "security/manage_local_runtime.py",
                    "security/proof_reports.py",
                    "security/automated_media.py",
                    "security/verify_git_checkout.py",
                    "security/verify_portfolio_tag_ci.py",
                    "security/validate_proof_challenge.sh",
                    "security/verify_app_run_evidence.py",
                    "security/verify_primary_evidence.py",
                    "security/verify_primary_replay.py",
                    "security/verify_local_app_run.py",
                    "security/verify_locked_environment.py",
                    "security/verify_supply_chain.py",
                    "security/verify_app_bundle.sh",
                    "publication/run_portfolio_python.sh",
                    "Tests/test_build_provenance.py",
                    "Tests/test_independent_replication.py",
                    "Tests/test_beacon_protocol.py",
                    "Tests/test_linux_runtime_hardening.py",
                    "Tests/test_swift_security_gate.py",
                    "Tests/fixtures/nist-beacon-certificate-528943a5.pem",
                    "Tests/fixtures/nist-beacon-chain-2-pulse-1884240.json",
                    "schemas/beacon-attempt.schema.json",
                    "schemas/beacon-freeze.schema.json",
                    "schemas/beacon-outcome.schema.json",
                    "schemas/beacon-registration.schema.json",
                    "schemas/beacon-resolution.schema.json",
                    "schemas/beacon-window-ledger.schema.json",
                    "schemas/portfolio-release-input.schema.json",
                    "schemas/portfolio-source-identity.schema.json",
                    "schemas/portfolio-demo-provenance.schema.json",
                    "schemas/portfolio-runtime-assets.schema.json",
                    "RealLLM/BEACON_HELDOUT_PROTOCOL.md",
                    "RealLLM/beacon_evaluation.py",
                    "RealLLM/beacon_protocol.py",
                    "RealLLM/beacon_registration.json",
                    "RealLLM/beacon_window_ledger.json",
                    "RealLLM/prepare_beacon_assets.py",
                    "RealLLM/prepare_beacon_freeze.py",
                    "RealLLM/run_beacon_one_shot.py",
                    "RealLLM/run_beacon_regression.py",
                    "RealLLM/verify_beacon_evidence.py",
                    "real-llm-beacon-results/README.md",
                    "app-real-llm-evidence/README.md",
                    "app-real-llm-evidence/SHA256SUMS",
                    "app-real-llm-evidence/app-run-receipt.json",
                    "app-real-llm-evidence/validation-064-071.json",
                    "publication/arxiv-v5/submission_metadata.md",
                    "signing/allowed_signers",
                    "signing/corelm-codec-signing.pub",
                    "tools/independent_replication.py",
                    "publication/build_portfolio_release.py",
                    "publication/collect_portfolio_demo.py",
                    "RealLLM/pinned_assets.py",
                    "publication/PORTFOLIO_RELEASE.md",
                ):
                    self.assertIn(f"{prefix}/{relative}", names)
                for relative in archives.V5_ARXIV_SOURCE_FILES:
                    self.assertIn(
                        f"{prefix}/publication/arxiv-v5/{relative}",
                        names,
                    )

    def test_reproducibility_archive_can_run_normal_test_gate(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = archives.build_reproducibility(root, context)
            extract_root = root / "extracted"
            extract_root.mkdir()
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extract_root, filter="data")
            extracted = extract_root / "corelm_reproducibility"
            completed = subprocess.run(
                [
                    "/bin/sh",
                    str(extracted / "scripts/verify-python.sh"),
                ],
                cwd=extracted,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHON_BIN": sys.executable},
                timeout=180,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=completed.stdout + completed.stderr,
            )

    def test_post_freeze_reproducibility_archive_includes_freeze_manifest(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_freeze = root / "beacon_freeze.json"
            frozen_bytes = b'{"schemaVersion":"corelm-beacon-freeze-v1"}\n'
            fake_freeze.write_bytes(frozen_bytes)
            with patch.object(archives, "BEACON_FREEZE_PATH", fake_freeze):
                archive = archives.build_reproducibility(root, context)
            with tarfile.open(archive, "r:gz") as bundle:
                member = bundle.extractfile(
                    "corelm_reproducibility/RealLLM/beacon_freeze.json"
                )
                self.assertIsNotNone(member)
                self.assertEqual(member.read(), frozen_bytes)

    def test_clean_reproducibility_archive_is_accepted_without_git(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": True,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            validation_result = archives._v5_evidence_state()
            with patch.object(
                archives,
                "_validate_v5_evidence",
                return_value=validation_result,
            ):
                archive = archives.build_reproducibility(root, context)
            extracted_root = root / "extracted"
            extracted_root.mkdir()
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted_root, filter="data")
            extracted = extracted_root / "corelm_reproducibility"
            self.assertFalse((extracted / ".git").exists())
            source = build_provenance.inspect_source_archive(
                extracted,
                extracted / build_provenance.DEFAULT_ARCHIVE_MANIFEST,
            )
            self.assertEqual(source["mode"], "archive")
            self.assertFalse(source["dirty"])
            self.assertEqual(source["commit"], "a" * 40)
            self.assertEqual(source["tree"], "b" * 40)

    def test_v5_arxiv_archive_contains_only_current_submission_sources(self):
        context = {
            "buildMode": "preview-working-tree",
            "builtFromCleanHead": False,
            "gitHeadCommit": "a" * 40,
            "gitHeadTree": "b" * 40,
            "releaseTag": None,
            "remoteTagVerified": False,
            "trackedFiles": set(),
        }
        expected = {
            "main.tex",
            "author.tex",
            "references.bib",
            "main.bbl",
            "results_table.tex",
            "figures/block_metrics.pdf",
            "figures/codec_pipeline.pdf",
            "figures/protocol_timeline.pdf",
        }
        with tempfile.TemporaryDirectory() as temporary:
            archive = archives.build_arxiv_v5(
                Path(temporary), context
            )
            self.assertEqual(
                archive.name,
                "corelm_voidtoken_v5_arxiv_source.tar.gz",
            )
            with tarfile.open(archive, "r:gz") as bundle:
                self.assertEqual(set(bundle.getnames()), expected)
                main = bundle.extractfile("main.tex")
                results = bundle.extractfile("results_table.tex")
                self.assertIsNotNone(main)
                self.assertIsNotNone(results)
                main_text = main.read().decode("ascii")
                results_text = results.read().decode("ascii")
            self.assertIn(
                "VoidToken v5: Prospectively Frozen Evidence",
                main_text,
            )
            self.assertIn("voidtoken-v5-evidence-v1", main_text)
            self.assertIn(
                "d1c16e88655c1fbc9884324742dee3f",
                main_text,
            )
            self.assertIn("Holdout", results_text)
            self.assertIn("2.053291", results_text)
            self.assertNotIn("metrics_by_dimension.pdf", main_text)
            self.assertNotIn("error_feedback.pdf", main_text)

    def test_determinism_flag_also_writes_requested_output(self):
        context = {"buildMode": "preview-working-tree"}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            artifacts = [
                output / "corelm_voidtoken_v5_arxiv_source.tar.gz",
                output / "corelm_reproducibility.tar.gz",
            ]
            arguments = types.SimpleNamespace(
                output=output,
                verify_determinism=True,
                release_tag=None,
            )
            with (
                patch.object(
                    archives,
                    "parse_arguments",
                    return_value=arguments,
                ),
                patch.object(
                    archives,
                    "_build_context",
                    return_value=context,
                ),
                patch.object(
                    archives,
                    "verify_determinism",
                    return_value=True,
                ) as determinism,
                patch.object(
                    archives,
                    "build_all",
                    return_value=artifacts,
                ) as build,
                patch.object(
                    archives,
                    "write_checksums",
                    return_value=output / "SHA256SUMS",
                ) as checksums,
            ):
                self.assertEqual(archives.main(), 0)
            determinism.assert_called_once_with(context)
            build.assert_called_once_with(output, context)
            checksums.assert_called_once_with(artifacts, output)


if __name__ == "__main__":
    unittest.main()
