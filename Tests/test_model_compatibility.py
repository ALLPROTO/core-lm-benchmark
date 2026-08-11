import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from RealLLM import model_compatibility, pinned_assets


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "RealLLM/model_compatibility.py"
REGISTRY = ROOT / "RealLLM/pinned_model_registry.json"
SCHEMA = ROOT / "schemas/model-compatibility-inspection.schema.json"


def standard_config(
    model_type: str,
    architecture: str,
    *,
    kv_heads: int | None = 2,
) -> dict:
    value = {
        "architectures": [architecture],
        "hidden_size": 64,
        "is_encoder_decoder": False,
        "max_position_embeddings": 4096,
        "model_type": model_type,
        "num_attention_heads": 4,
        "num_hidden_layers": 2,
        "trust_remote_code": False,
        "vocab_size": 1024,
    }
    if kv_heads is not None:
        value["num_key_value_heads"] = kv_heads
    if model_type == "mistral":
        value["sliding_window"] = 4096
    return value


class ModelCompatibilityRegistryTests(unittest.TestCase):
    def test_registry_is_hash_pinned_closed_and_matches_qwen_assets(self):
        raw = REGISTRY.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            model_compatibility.REGISTRY_SHA256,
        )
        registry, digest = model_compatibility._registry()
        self.assertEqual(digest, model_compatibility.REGISTRY_SHA256)
        self.assertEqual(
            registry["schemaVersion"], "corelm-pinned-model-registry-v1"
        )
        self.assertEqual(
            [profile["profileId"] for profile in registry["profiles"]],
            ["qwen2.5-0.5b-v15"],
        )
        profile = registry["profiles"][0]
        files = {entry["path"]: entry for entry in profile["files"]}
        self.assertEqual(len(files), 7)
        self.assertEqual(profile["repository"], pinned_assets.MODEL_REPOSITORY)
        self.assertEqual(profile["revision"], pinned_assets.MODEL_REVISION)
        self.assertEqual(profile["license"], pinned_assets.MODEL_LICENSE)
        expected_roles = {
            "config.json": "model-config",
            "generation_config.json": "generation-config",
            "merges.txt": "tokenizer-merges",
            "model.safetensors": "model-weights",
            "tokenizer.json": "tokenizer",
            "tokenizer_config.json": "tokenizer-config",
            "vocab.json": "tokenizer-vocabulary",
        }
        expected_files = {
            path: {
                "bytes": record["bytes"],
                "path": path,
                "role": expected_roles[path],
                "sha256": record["sha256"],
            }
            for path, record in pinned_assets.PINNED_RELEASE_ASSETS["model"][
                "files"
            ].items()
        }
        self.assertEqual(files, expected_files)
        self.assertEqual(
            files["model.safetensors"],
            {
                "bytes": 988_097_824,
                "path": "model.safetensors",
                "role": "model-weights",
                "sha256": (
                    "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd3"
                    "46445188a0ed342"
                ),
            },
        )
        adapter_ids = [entry["adapterId"] for entry in registry["adapters"]]
        self.assertEqual(adapter_ids, sorted(adapter_ids))
        self.assertEqual(len(adapter_ids), 7)
        self.assertTrue(
            all(
                len(adapter["modelTypes"]) == 1
                and len(adapter["architectures"]) == 1
                for adapter in registry["adapters"]
            )
        )

    def test_schema_is_strict_json_and_binds_non_evidence_classification(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["classification"]["const"],
            model_compatibility.CLASSIFICATION,
        )
        self.assertEqual(
            schema["properties"]["modelExecuted"]["const"], False
        )
        self.assertEqual(
            schema["properties"]["acceptedAsBenchmarkEvidence"]["const"],
            False,
        )
        adapter = schema["$defs"]["adapter"]["properties"]
        self.assertEqual(adapter["modelTypes"]["maxItems"], 1)
        self.assertEqual(adapter["architectures"]["maxItems"], 1)

    def test_list_report_is_canonical_and_makes_no_execution_claim(self):
        report = model_compatibility.list_report()
        self.assertEqual(report["action"], "list")
        self.assertFalse(report["modelExecuted"])
        self.assertFalse(report["acceptedAsBenchmarkEvidence"])
        self.assertFalse(report["countsTowardScientificVerdict"])
        encoded = model_compatibility.canonical_json_bytes(report)
        self.assertEqual(encoded[-1:], b"\n")
        self.assertEqual(
            encoded,
            json.dumps(
                report,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n",
        )


class ModelCompatibilityAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.registry, _ = model_compatibility._registry()

    def test_known_architecture_matrix_is_eligible_without_model_execution(self):
        gemma = standard_config("gemma", "GemmaForCausalLM")
        gemma.update(
            {
                "head_dim": 256,
                "hidden_size": 3072,
                "max_position_embeddings": 8192,
                "num_attention_heads": 16,
                "num_hidden_layers": 28,
                "num_key_value_heads": 16,
                "vocab_size": 256000,
            }
        )
        configurations = [
            standard_config("qwen2", "Qwen2ForCausalLM"),
            standard_config("llama", "LlamaForCausalLM"),
            standard_config("mistral", "MistralForCausalLM"),
            standard_config(
                "gpt_neox", "GPTNeoXForCausalLM", kv_heads=None
            ),
            {
                "architectures": ["GPT2LMHeadModel"],
                "is_encoder_decoder": False,
                "model_type": "gpt2",
                "n_embd": 64,
                "n_head": 4,
                "n_layer": 2,
                "n_positions": 4096,
                "trust_remote_code": False,
                "vocab_size": 1024,
            },
            standard_config("opt", "OPTForCausalLM", kv_heads=None),
            gemma,
        ]
        observed = []
        for configuration in configurations:
            analysis = model_compatibility.analyze_config(
                configuration, self.registry
            )
            observed.append(analysis["adapterId"])
            self.assertEqual(
                analysis["status"],
                "eligible-for-separate-pinned-admission",
            )
            self.assertIsNone(analysis["exactRegisteredConfigProfile"])
            self.assertEqual(
                analysis["cacheAdapter"],
                "transformers-dynamic-cache-kv-v1",
            )
        self.assertEqual(len(set(observed)), 7)

    def test_explicit_head_dimension_may_define_a_wider_projection(self):
        config = standard_config("gemma", "GemmaForCausalLM")
        config.update(
            {
                "head_dim": 256,
                "hidden_size": 3072,
                "num_attention_heads": 16,
                "num_key_value_heads": 16,
            }
        )
        analysis = model_compatibility.analyze_config(config, self.registry)
        self.assertEqual(analysis["geometry"]["headDimension"], 256)
        self.assertEqual(analysis["geometry"]["hiddenSize"], 3072)

    def test_smollm2_style_metadata_uses_the_llama_adapter_without_a_claim(self):
        config = standard_config("llama", "LlamaForCausalLM")
        config.update(
            {
                "hidden_size": 576,
                "max_position_embeddings": 8192,
                "num_attention_heads": 9,
                "num_hidden_layers": 30,
                "num_key_value_heads": 3,
                "vocab_size": 49152,
            }
        )
        analysis = model_compatibility.analyze_config(config, self.registry)
        self.assertEqual(analysis["adapterId"], "llama-dynamic-cache-v1")
        self.assertEqual(
            analysis["status"], "eligible-for-separate-pinned-admission"
        )
        self.assertIsNone(analysis["exactRegisteredConfigProfile"])
        self.assertIsNone(analysis["matchingRegisteredGeometryProfile"])

    def test_qwen_geometry_alone_is_not_an_exact_registered_config_match(self):
        config = {
            "architectures": ["Qwen2ForCausalLM"],
            "hidden_size": 896,
            "is_encoder_decoder": False,
            "max_position_embeddings": 32768,
            "model_type": "qwen2",
            "num_attention_heads": 14,
            "num_hidden_layers": 24,
            "num_key_value_heads": 2,
            "sliding_window": 32768,
            "trust_remote_code": False,
            "use_sliding_window": False,
            "vocab_size": 151936,
        }
        analysis = model_compatibility.analyze_config(config, self.registry)
        self.assertEqual(
            analysis["status"], "eligible-for-separate-pinned-admission"
        )
        self.assertIsNone(analysis["exactRegisteredConfigProfile"])
        self.assertEqual(
            analysis["matchingRegisteredGeometryProfile"],
            "qwen2.5-0.5b-v15",
        )
        pinned = model_compatibility.analyze_config(
            config,
            self.registry,
            config_sha256=(
                "479dcf0c5286339e41ad3992cd08ae88a467c4187587936248"
                "e2b7c96283484b"
            ),
        )
        self.assertEqual(pinned["status"], "registered-config-bytes-match")
        self.assertEqual(
            pinned["exactRegisteredConfigProfile"],
            "qwen2.5-0.5b-v15",
        )

    def test_remote_dynamic_and_noncausal_code_paths_are_rejected(self):
        mutations = {
            "remote code": {"trust_remote_code": True},
            "auto map": {"auto_map": {}},
            "quantization": {"quantization_config": {}},
            "encoder decoder": {"is_encoder_decoder": True},
            "cross attention": {"add_cross_attention": True},
            "vision": {"vision_config": {}},
            "experts": {"num_local_experts": 8},
            "experts per token": {"num_experts_per_tok": 1},
            "moe routing": {"moe_layer_freq": 0},
            "hybrid layers": {"layer_types": ["full_attention", "sliding_attention"]},
            "static cache": {"cache_implementation": "static"},
            "cache disabled": {"use_cache": False},
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                config = standard_config("qwen2", "Qwen2ForCausalLM")
                config.update(mutation)
                with self.assertRaises(model_compatibility.CompatibilityError):
                    model_compatibility.analyze_config(config, self.registry)

    def test_identifier_parser_matches_the_ascii_schema_grammar(self):
        self.assertEqual(
            model_compatibility._require_identifier("qwen2.5-v1", label="id"),
            "qwen2.5-v1",
        )
        for invalid in ("_leading", "UPPER", "\N{CYRILLIC SMALL LETTER A}", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(model_compatibility.CompatibilityError):
                    model_compatibility._require_identifier(invalid, label="id")

    def test_unknown_or_invalid_cache_geometry_is_rejected(self):
        cases = []
        unknown = standard_config("unknown", "UnknownForCausalLM")
        cases.append(unknown)
        duplicate_architecture = standard_config(
            "qwen2", "Qwen2ForCausalLM"
        )
        duplicate_architecture["architectures"].append("Qwen2ForCausalLM")
        cases.append(duplicate_architecture)
        bad_hidden = standard_config("qwen2", "Qwen2ForCausalLM")
        bad_hidden["hidden_size"] = 65
        cases.append(bad_hidden)
        bad_kv = standard_config("qwen2", "Qwen2ForCausalLM")
        bad_kv["num_key_value_heads"] = 3
        cases.append(bad_kv)
        missing_window = standard_config("mistral", "MistralForCausalLM")
        del missing_window["sliding_window"]
        cases.append(missing_window)
        unexpected_window = standard_config("llama", "LlamaForCausalLM")
        unexpected_window["sliding_window"] = 128
        cases.append(unexpected_window)
        for config in cases:
            with self.subTest(config=config):
                with self.assertRaises(model_compatibility.CompatibilityError):
                    model_compatibility.analyze_config(config, self.registry)


class ModelCompatibilityCLITests(unittest.TestCase):
    def _config(self, directory: Path, value: dict) -> Path:
        path = directory / "config.json"
        path.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        return path

    def test_cli_inspects_one_private_config_and_writes_only_stdout(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            config = self._config(
                directory,
                standard_config("llama", "LlamaForCausalLM"),
            )
            before = sorted(path.name for path in directory.iterdir())
            completed = subprocess.run(
                [sys.executable, "-I", "-B", str(SCRIPT), "inspect-config", str(config)],
                check=False,
                capture_output=True,
            )
            after = sorted(path.name for path in directory.iterdir())
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(completed.stderr, b"")
        self.assertEqual(before, after)
        report = json.loads(completed.stdout)
        self.assertEqual(
            completed.stdout,
            model_compatibility.canonical_json_bytes(report),
        )
        self.assertFalse(report["modelExecuted"])
        self.assertEqual(report["analysis"]["modelType"], "llama")

    def test_dispatcher_exposes_only_list_and_one_config_inspection(self):
        dispatcher = (ROOT / "corelm").read_text(encoding="utf-8")
        self.assertIn("models list", dispatcher)
        self.assertIn("models inspect-config ABSOLUTE_CONFIG_JSON", dispatcher)
        self.assertIn("RealLLM/model_compatibility.py", dispatcher)
        self.assertIn("model metadata inspection requires", dispatcher)
        completed = subprocess.run(
            [str(ROOT / "corelm"), "models", "list"],
            check=False,
            capture_output=True,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(completed.stderr, b"")
        report = json.loads(completed.stdout)
        self.assertEqual(report["action"], "list")
        rejected = subprocess.run(
            [str(ROOT / "corelm"), "models", "inspect-config"],
            check=False,
            capture_output=True,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, b"")

    def test_cli_rejects_duplicate_json_symlinks_hardlinks_and_unsafe_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            valid = self._config(
                directory,
                standard_config("qwen2", "Qwen2ForCausalLM"),
            )
            duplicate = directory / "duplicate.json"
            duplicate.write_text(
                '{"model_type":"qwen2","model_type":"qwen2"}\n',
                encoding="utf-8",
            )
            duplicate.chmod(0o600)
            symlink = directory / "symlink.json"
            symlink.symlink_to(valid)
            hardlink = directory / "hardlink.json"
            os.link(valid, hardlink)
            unsafe = directory / "unsafe.json"
            unsafe.write_bytes(valid.read_bytes())
            unsafe.chmod(0o666)
            paths = [duplicate, symlink, hardlink, unsafe]
            for path in paths:
                with self.subTest(path=path.name):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            str(SCRIPT),
                            "inspect-config",
                            str(path),
                        ],
                        check=False,
                        capture_output=True,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertEqual(completed.stdout, b"")
                    self.assertIn(b"MODEL COMPATIBILITY FAIL:", completed.stderr)

    def test_module_has_no_model_runtime_or_write_surface(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            {"torch", "transformers", "datasets", "huggingface_hub"}.isdisjoint(
                imports
            )
        )
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_bytes(", source)
        self.assertNotIn("urlopen", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("app_proof", source)
        self.assertNotIn("voidtoken", source)


if __name__ == "__main__":
    unittest.main()
