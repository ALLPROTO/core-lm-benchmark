#!/bin/sh
set -eu

umask 077
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd -P)
RUNTIME_DIR=${CORELM_LINUX_RUNTIME:-"$HOME/.cache/corelm/linux/runtime"}
HF_CACHE=${CORELM_LINUX_HF_HOME:-"$HOME/.cache/corelm/linux/model-assets"}
RUN_ROOT=${CORELM_LINUX_RUN_ROOT:-"$HOME/.cache/corelm/linux/runs"}
RUN_DIR=${CORELM_RUN_DIR:-"$RUN_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"}

fail() {
    printf 'LINUX REAL-QWEN REGRESSION FAIL: %s\n' "$*" >&2
    exit 1
}

case "$RUN_DIR" in /*) ;; *) fail "CORELM_RUN_DIR must be absolute" ;; esac
[ ! -e "$RUN_DIR" ] || fail "run directory already exists: $RUN_DIR"

git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "run from a Git clone so source identity can be recorded"
[ -z "$(git -C "$PROJECT_DIR" status --porcelain=v1 \
    --untracked-files=all --ignored=no)" ] \
    || fail "the source checkout must be completely clean"
[ ! -e "$PROJECT_DIR/real-llm-beacon-results/attempt.json" ] \
    || fail "beacon attempt state is present; this command is regression-only"

CORELM_RUN_DIR="$RUN_DIR" \
    "$PROJECT_DIR/platforms/linux/scripts/build-runtime.sh"
run_parent=$(dirname -- "$RUN_DIR")
if [ ! -e "$run_parent" ]; then
    /bin/mkdir -p "$run_parent"
    /bin/chmod 700 "$run_parent"
fi
/bin/mkdir "$RUN_DIR"
/bin/chmod 700 "$RUN_DIR"

source_commit=$(git -C "$PROJECT_DIR" rev-parse HEAD)
source_tree=$(git -C "$PROJECT_DIR" rev-parse 'HEAD^{tree}')
runtime_python="$RUNTIME_DIR/bin/python"

"$runtime_python" -I -B - "$RUN_DIR" "$source_commit" "$source_tree" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
contract = {
    "schemaVersion": "corelm-real-qwen-linux-regression-contract-v1",
    "evidenceClass": "regression-only",
    "countsTowardScientificVerdict": False,
    "dataClass": "real-public-validation",
    "modelExecutionRequested": True,
    "modelRepository": "Qwen/Qwen2.5-0.5B",
    "modelRevision": "060db6499f32faf8b98477b0a26969ef7d8b9987",
    "datasetRepository": "Salesforce/wikitext",
    "datasetSplit": "validation",
    "validationStartBlock": 64,
    "validationBlocks": 8,
    "candidateIndex": 32,
    "device": "cpu",
    "testDataAccessAllowed": False,
    "beaconExecutionAllowed": False,
    "sourceCommit": sys.argv[2],
    "sourceTree": sys.argv[3],
}
(run / "pre-run-contract.json").write_text(
    json.dumps(contract, sort_keys=True, indent=2, allow_nan=False) + "\n",
    encoding="utf-8",
)
PY

{
    printf 'source commit: %s\n' "$source_commit"
    printf 'source tree: %s\n' "$source_tree"
    printf 'UTC start: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    uname -a
    "$runtime_python" -VV
    "$runtime_python" -I -B -m pip freeze --all
} > "$RUN_DIR/environment.txt"

printf '%s\n' \
    'python -I -B RealLLM/develop_voidtoken_v5.py --device cpu --validation-start-block 64 --validation-blocks 8 --candidate-index 32 --local-files-only' \
    > "$RUN_DIR/command.txt"

set +e
HF_HOME="$HF_CACHE" \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
HF_HUB_DISABLE_TELEMETRY=1 \
TOKENIZERS_PARALLELISM=false \
OMP_NUM_THREADS=2 \
OPENBLAS_NUM_THREADS=2 \
MKL_NUM_THREADS=2 \
NUMEXPR_NUM_THREADS=2 \
/usr/bin/timeout --signal=TERM --kill-after=120s 105m \
    "$runtime_python" -I -B \
    "$PROJECT_DIR/RealLLM/develop_voidtoken_v5.py" \
    --device cpu \
    --validation-start-block 64 \
    --validation-blocks 8 \
    --candidate-index 32 \
    --local-files-only \
    --output "$RUN_DIR/validation-064-071.json" \
    --primary-evidence-directory "$RUN_DIR/primary-evidence" \
    > "$RUN_DIR/stdout.log" 2> "$RUN_DIR/stderr.log"
runner_exit=$?
set -e
printf '%s\n' "$runner_exit" > "$RUN_DIR/runner-exit-code.txt"
printf 'UTC end: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$RUN_DIR/end-time.txt"
[ "$runner_exit" -eq 0 ] || fail "Qwen process exited with $runner_exit"

"$runtime_python" -I -B "$PROJECT_DIR/security/verify_primary_evidence.py" \
    "$RUN_DIR" | tee "$RUN_DIR/verification.txt"

"$runtime_python" -I -B - "$RUN_DIR" "$source_commit" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
result = json.loads((run / "validation-064-071.json").read_text())
assert result["status"] == "validation-only-development"
assert result["testDataOpened"] is False
assert result["protocol"]["split"] == "validation"
assert result["protocol"]["validationStartBlock"] == 64
assert result["protocol"]["validationBlocks"] == 8
assert result["protocol"]["evaluatedCandidateIndices"] == [32]
assert result["environment"]["device"] == "cpu"
assert result["selectedTokenIdsSHA256"] == (
    "1bb36c91d441379596361ae779ca0542c85457e9902a290a6ab6945cb2513453"
)
assert result["primaryEvidence"]["containerCount"] == 192
assert result["primaryEvidence"]["predictionTokens"] == 1024
aggregate = result["aggregates"][0]
manifest = {
    "schemaVersion": "corelm-real-qwen-linux-regression-run-v1",
    "evidenceClass": "regression-only",
    "countsTowardScientificVerdict": False,
    "modelExecuted": True,
    "testDataOpened": False,
    "beaconExecuted": False,
    "sourceCommit": sys.argv[2],
    "resultSHA256": result["resultSHA256"],
    "selectedTokenIdsSHA256": result["selectedTokenIdsSHA256"],
    "containerCount": 192,
    "predictionTokens": 1024,
    "compressionRatioVsBF16": aggregate["compressionRatioVsBF16"],
    "deltaNLLNatPerToken": aggregate["deltaNLLNatPerToken"],
    "top1Agreement": aggregate["top1Agreement"],
    "metricVerdict": "PASS" if aggregate["pass"] else "FAIL",
}
(run / "run-manifest.json").write_text(
    json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n",
    encoding="utf-8",
)
rows = []
for path in sorted(run.rglob("*")):
    if path.is_file() and path.name != "SHA256SUMS":
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(run).as_posix()
        rows.append(f"{digest}  {relative}\n")
(run / "SHA256SUMS").write_text("".join(rows), encoding="ascii")
print(json.dumps(manifest, sort_keys=True, indent=2))
PY

(cd "$RUN_DIR" && sha256sum -c SHA256SUMS)
printf 'LINUX REAL-QWEN REGRESSION PASS: %s\n' "$RUN_DIR"
