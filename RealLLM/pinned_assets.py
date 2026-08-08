"""Dependency-free canonical identity of the public real-model inputs.

The scientific benchmark file is already hash-frozen and cannot import a new
module.  Release tests compare every value here with those immutable benchmark
constants, so publication code has one lightweight identity without mutating
the frozen implementation boundary.
"""

MODEL_REPOSITORY = "Qwen/Qwen2.5-0.5B"
MODEL_REVISION = "060db6499f32faf8b98477b0a26969ef7d8b9987"
MODEL_WEIGHTS_SHA256 = (
    "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342"
)
MODEL_WEIGHTS_BYTES = 988_097_824
MODEL_ASSET_FILES = {
    "config.json": {
        "bytes": 681,
        "sha256": "479dcf0c5286339e41ad3992cd08ae88a467c4187587936248e2b7c96283484b",
    },
    "generation_config.json": {
        "bytes": 138,
        "sha256": "8c970692323e3ea0e9b8b0a4dca79388d31226e41f83c9fd6014804280ebf6e8",
    },
    "merges.txt": {
        "bytes": 1_671_839,
        "sha256": "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3",
    },
    "tokenizer.json": {
        "bytes": 7_031_645,
        "sha256": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    },
    "tokenizer_config.json": {
        "bytes": 7_228,
        "sha256": "c91efca15ceff6e9ee9424db58a6f59cd41294e550a86cbd07e3c1fb500b34f9",
    },
    "vocab.json": {
        "bytes": 2_776_833,
        "sha256": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
    },
}
MODEL_LICENSE = "Apache-2.0"
DATASET_REPOSITORY = "Salesforce/wikitext"
DATASET_REVISION = "b08601e04326c79dfdd32d625aee71d232d685c3"
DATASET_CONFIGURATION = "wikitext-2-raw-v1"
DATASET_FILES = {
    "validation": {
        "path": "wikitext-2-raw-v1/validation-00000-of-00001.parquet",
        "sha256": "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c",
        "bytes": 657_209,
    },
    "test": {
        "path": "wikitext-2-raw-v1/test-00000-of-00001.parquet",
        "sha256": "5f1bea067869d04849c0f975a2b29c4ff47d867f484f5010ea5e861eab246d91",
        "bytes": 732_610,
    },
}
DATASET_LICENSE = "CC BY-SA 3.0 and GFDL"
DATASET_SOURCE_URL = "https://huggingface.co/datasets/Salesforce/wikitext"

PINNED_RELEASE_ASSETS = {
    "model": {
        "repository": MODEL_REPOSITORY,
        "revision": MODEL_REVISION,
        "license": MODEL_LICENSE,
        "files": {
            "model.safetensors": {
                "bytes": MODEL_WEIGHTS_BYTES,
                "sha256": MODEL_WEIGHTS_SHA256,
            },
            **MODEL_ASSET_FILES,
        },
    },
    "corpus": {
        "repository": DATASET_REPOSITORY,
        "revision": DATASET_REVISION,
        "path": DATASET_FILES["validation"]["path"],
        "bytes": DATASET_FILES["validation"]["bytes"],
        "sha256": DATASET_FILES["validation"]["sha256"],
        "license": DATASET_LICENSE,
        "source_url": DATASET_SOURCE_URL,
    },
}
