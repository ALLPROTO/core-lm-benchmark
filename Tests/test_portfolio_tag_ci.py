import copy
import hashlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from security import verify_portfolio_tag_ci as tag_ci


REPOSITORY = "ALLPROTO/core-lm-benchmark"
TAG = "corelm-portfolio-v15"
TAG_OBJECT = "a" * 40
COMMIT = "b" * 40
TREE = "c" * 40
LINUX_RUN_ID = 31_320_957_015
MACOS_RUN_ID = 31_320_957_021
LINUX_SUPPLY_CHAIN_JOB_ID = 93_263_748_891
LINUX_PYTHON_JOB_ID = 93_263_748_910
MACOS_NATIVE_JOB_ID = 93_263_748_932
ROOT = Path(__file__).resolve().parents[1]


def _workflow_tag_ref_blocks(relative):
    lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
    current_job = None
    blocks = []
    for index, line in enumerate(lines):
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            current_job = line.strip()[:-1]
        if line != f"      - name: {tag_ci.TAG_REF_ASSERTION_STEP}":
            continue
        if current_job is None or lines[index + 1] != "        run: |":
            raise AssertionError("tag-ref assertion step has an unexpected YAML shape")
        body = []
        cursor = index + 2
        while cursor < len(lines) and lines[cursor].startswith("          "):
            body.append(lines[cursor][10:])
            cursor += 1
        blocks.append((current_job, "\n".join(body) + "\n"))
    return blocks


def _json(value):
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _repository():
    return {
        "full_name": REPOSITORY,
        "private": False,
        "visibility": "public",
    }


def _run(workflow_name, workflow_path, run_id):
    api_base = f"https://api.github.com/repos/{REPOSITORY}"
    return {
        "total_count": 1,
        "workflow_runs": [
            {
                "id": run_id,
                "run_number": 17,
                "run_attempt": 1,
                "name": workflow_name,
                "path": workflow_path,
                "event": "push",
                "head_branch": TAG,
                "head_sha": COMMIT,
                "status": "completed",
                "conclusion": "success",
                "url": f"{api_base}/actions/runs/{run_id}",
                "jobs_url": f"{api_base}/actions/runs/{run_id}/jobs",
                "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
                "repository": _repository(),
                "head_repository": _repository(),
                "head_commit": {"id": COMMIT, "tree_id": TREE},
            }
        ],
    }


def _job(workflow_name, run_id, job_id, name):
    api_base = f"https://api.github.com/repos/{REPOSITORY}"
    return {
        "id": job_id,
        "run_id": run_id,
        "head_sha": COMMIT,
        "name": name,
        "workflow_name": workflow_name,
        "status": "completed",
        "conclusion": "success",
        "url": f"{api_base}/actions/jobs/{job_id}",
        "run_url": f"{api_base}/actions/runs/{run_id}",
        "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}/job/{job_id}",
        "steps": [
            {
                "name": tag_ci.TAG_REF_ASSERTION_STEP,
                "number": 1,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "Check out exact source",
                "number": 2,
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "Run exact verification gate",
                "number": 3,
                "status": "completed",
                "conclusion": "success",
            },
        ],
    }


def _fixture_documents():
    api_base = f"https://api.github.com/repos/{REPOSITORY}"
    linux_run_id = LINUX_RUN_ID
    macos_run_id = MACOS_RUN_ID
    return {
        "tag_ref": {
            "ref": f"refs/tags/{TAG}",
            "url": f"{api_base}/git/refs/tags/{TAG}",
            "object": {
                "type": "tag",
                "sha": TAG_OBJECT,
                "url": f"{api_base}/git/tags/{TAG_OBJECT}",
            },
        },
        "tag_object": {
            "sha": TAG_OBJECT,
            "tag": TAG,
            "url": f"{api_base}/git/tags/{TAG_OBJECT}",
            "object": {
                "type": "commit",
                "sha": COMMIT,
                "url": f"{api_base}/git/commits/{COMMIT}",
            },
            "verification": {
                "verified": True,
                "reason": "valid",
                "signature": "-----BEGIN SSH SIGNATURE----- fixture",
                "payload": "object fixture",
            },
        },
        "commit": {
            "sha": COMMIT,
            "url": f"{api_base}/git/commits/{COMMIT}",
            "tree": {
                "sha": TREE,
                "url": f"{api_base}/git/trees/{TREE}",
            },
            "verification": {
                "verified": True,
                "reason": "valid",
                "signature": "-----BEGIN SSH SIGNATURE----- fixture",
                "payload": "tree fixture",
            },
        },
        "main_ref": {
            "ref": "refs/heads/main",
            "url": f"{api_base}/git/refs/heads/main",
            "object": {
                "type": "commit",
                "sha": COMMIT,
                "url": f"{api_base}/git/commits/{COMMIT}",
            },
        },
        "linux_runs": _run(
            "Verify Linux", ".github/workflows/verify-linux.yml", linux_run_id
        ),
        "linux_jobs": {
            "total_count": 2,
            "jobs": [
                _job(
                    "Verify Linux",
                    linux_run_id,
                    LINUX_SUPPLY_CHAIN_JOB_ID,
                    "supply-chain",
                ),
                _job(
                    "Verify Linux",
                    linux_run_id,
                    LINUX_PYTHON_JOB_ID,
                    "python-and-publication",
                ),
            ],
        },
        "macos_runs": _run(
            "Verify macOS", ".github/workflows/verify-macos.yml", macos_run_id
        ),
        "macos_jobs": {
            "total_count": 1,
            "jobs": [
                _job(
                    "Verify macOS",
                    macos_run_id,
                    MACOS_NATIVE_JOB_ID,
                    "native-application",
                )
            ],
        },
    }


class PortfolioTagWorkflowSourceTests(unittest.TestCase):
    def test_exact_tag_ref_assertion_is_v15_tag_only_in_every_required_job(self):
        for relative, expected_jobs in (
            (
                ".github/workflows/verify-linux.yml",
                {"supply-chain", "python-and-publication"},
            ),
            (".github/workflows/verify-macos.yml", {"native-application"}),
        ):
            with self.subTest(workflow=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                blocks = _workflow_tag_ref_blocks(relative)
                self.assertEqual(
                    {job for job, _body in blocks}, expected_jobs
                )
                self.assertEqual(len(blocks), len(expected_jobs))
                self.assertEqual(
                    source.count("expected_tag=corelm-portfolio-v15"),
                    len(expected_jobs),
                )
                self.assertEqual(
                    source.count(
                        "expected_citation_line='version: \"corelm-portfolio-v15\"'"
                    ),
                    len(expected_jobs),
                )
                self.assertEqual(
                    source.count(
                        'if [ "$GITHUB_REF_NAME" != "$expected_tag" ]; then'
                    ),
                    len(expected_jobs),
                )
                for command in (
                    'test "$GITHUB_EVENT_NAME" = push',
                    'test "$GITHUB_REF_TYPE" = tag',
                    'test "$GITHUB_REF" = "$tag_ref"',
                    'test "$GITHUB_REF_NAME" = "$expected_tag"',
                    'test "$GITHUB_RUN_ATTEMPT" = 1',
                    'grep -Fxc -- "$expected_citation_line" CITATION.cff',
                    'git cat-file -t "$tag_ref"',
                    'git rev-parse "$tag_ref^{commit}"',
                    "git rev-parse HEAD^{commit}",
                ):
                    with self.subTest(workflow=relative, command=command):
                        self.assertEqual(source.count(command), len(expected_jobs))
                self.assertNotIn('version: \\\"corelm-portfolio-v15\\\"', source)
                self.assertEqual(
                    source.count(
                        "Not the V15 portfolio tag; exact tag assertion is not applicable."
                    ),
                    len(expected_jobs),
                )
                self.assertNotIn("Not the V12 portfolio tag", source)
                self.assertNotIn("if: ${{", source)

    def test_each_tag_ref_assertion_executes_fail_closed(self):
        blocks = (
            _workflow_tag_ref_blocks(".github/workflows/verify-linux.yml")
            + _workflow_tag_ref_blocks(".github/workflows/verify-macos.yml")
        )
        self.assertEqual(len(blocks), 3)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "config", "user.name", "Fixture"], cwd=root, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.invalid"],
                cwd=root,
                check=True,
            )
            citation = root / "CITATION.cff"
            citation.write_text('version: "corelm-portfolio-v15"\n', encoding="utf-8")
            subprocess.run(["git", "add", "CITATION.cff"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True
            )
            subprocess.run(
                ["git", "tag", "-a", TAG, "-m", "fixture tag"],
                cwd=root,
                check=True,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD^{commit}"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            def execute(body, **overrides):
                environment = os.environ.copy()
                environment.update(
                    {
                        "GITHUB_EVENT_NAME": "push",
                        "GITHUB_REF_TYPE": "tag",
                        "GITHUB_REF": f"refs/tags/{TAG}",
                        "GITHUB_REF_NAME": TAG,
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SHA": commit,
                    }
                )
                environment.update(overrides)
                return subprocess.run(
                    ["/bin/sh", "-c", body],
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    check=False,
                    text=True,
                )

            for job, body in blocks:
                with self.subTest(job=job, case="exact-tag"):
                    self.assertEqual(execute(body).returncode, 0)
                with self.subTest(job=job, case="same-name-branch"):
                    self.assertNotEqual(
                        execute(
                            body,
                            GITHUB_REF_TYPE="branch",
                            GITHUB_REF=f"refs/heads/{TAG}",
                        ).returncode,
                        0,
                    )
                with self.subTest(job=job, case="rerun"):
                    self.assertNotEqual(
                        execute(body, GITHUB_RUN_ATTEMPT="2").returncode, 0
                    )
                with self.subTest(job=job, case="unrelated-main"):
                    self.assertEqual(
                        execute(
                            body,
                            GITHUB_REF_TYPE="branch",
                            GITHUB_REF="refs/heads/main",
                            GITHUB_REF_NAME="main",
                        ).returncode,
                        0,
                    )
                for label, text in (
                    ("escaped-citation", 'version: \\\"corelm-portfolio-v15\\\"\n'),
                    ("missing-citation", 'version: "different"\n'),
                    (
                        "duplicate-citation",
                        'version: "corelm-portfolio-v15"\n'
                        'version: "corelm-portfolio-v15"\n',
                    ),
                ):
                    citation.write_text(text, encoding="utf-8")
                    with self.subTest(job=job, case=label):
                        self.assertNotEqual(execute(body).returncode, 0)
                citation.write_text(
                    'version: "corelm-portfolio-v15"\n', encoding="utf-8"
                )


def _fixture_responses():
    return {role: _json(value) for role, value in _fixture_documents().items()}


def _validate(responses):
    return tag_ci.validate_saved_tag_ci(
        responses,
        repository=REPOSITORY,
        expected_tag=TAG,
        expected_commit=COMMIT,
        expected_tree=TREE,
    )


class SavedTagCIAdmissionTests(unittest.TestCase):
    def test_valid_saved_responses_produce_canonical_hash_bound_receipt(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(receipt["automation_only"])
        self.assertFalse(receipt["human_reviewed"])
        self.assertEqual(receipt["source"]["annotated_tag_object"], TAG_OBJECT)
        self.assertEqual(receipt["source"]["commit"], COMMIT)
        self.assertEqual(receipt["source"]["tree"], TREE)
        self.assertEqual(
            [item["workflow_name"] for item in receipt["workflows"]],
            ["Verify Linux", "Verify macOS"],
        )
        self.assertEqual(
            [job["name"] for job in receipt["workflows"][0]["jobs"]],
            ["python-and-publication", "supply-chain"],
        )
        self.assertTrue(
            all(
                job["tag_ref_assertion"] == "PASS"
                for workflow in receipt["workflows"]
                for job in workflow["jobs"]
            )
        )
        descriptors = {item["role"]: item for item in receipt["responses"]}
        for role, raw in responses.items():
            self.assertEqual(descriptors[role]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(descriptors[role]["size_bytes"], len(raw))
        encoded = tag_ci.canonical_receipt_bytes(receipt)
        self.assertEqual(encoded, tag_ci.canonical_receipt_bytes(copy.deepcopy(receipt)))
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertNotIn(b": ", encoded)
        self.assertNotIn(b", ", encoded)

    def test_response_byte_change_is_visible_even_when_json_semantics_match(self):
        compact = _fixture_responses()
        spaced = dict(compact)
        value = json.loads(spaced["main_ref"])
        spaced["main_ref"] = json.dumps(value, indent=2).encode("ascii") + b"\n"
        compact_receipt = _validate(compact)
        spaced_receipt = _validate(spaced)
        self.assertNotEqual(
            compact_receipt["responses"][3]["sha256"],
            spaced_receipt["responses"][3]["sha256"],
        )

    def test_lightweight_or_wrong_tag_ref_is_rejected(self):
        documents = _fixture_documents()
        documents["tag_ref"]["object"]["type"] = "commit"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "object type"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        documents["tag_ref"]["ref"] = "refs/tags/other"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "tag ref"):
            _validate({role: _json(value) for role, value in documents.items()})

    def test_tag_object_commit_and_tree_must_be_exact(self):
        documents = _fixture_documents()
        documents["tag_object"]["object"]["sha"] = "d" * 40
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "target SHA"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        documents["commit"]["tree"]["sha"] = "d" * 40
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "tree SHA"):
            _validate({role: _json(value) for role, value in documents.items()})

    def test_tag_and_commit_github_verification_must_be_verified_valid(self):
        for role, field, value in (
            ("tag_object", "verified", False),
            ("tag_object", "reason", "unsigned"),
            ("commit", "verified", False),
            ("commit", "reason", "unknown_key"),
        ):
            with self.subTest(role=role, field=field):
                documents = _fixture_documents()
                documents[role]["verification"][field] = value
                with self.assertRaises(tag_ci.TagCIAdmissionError):
                    _validate({name: _json(item) for name, item in documents.items()})

    def test_main_must_publicly_equal_exact_commit(self):
        documents = _fixture_documents()
        documents["main_ref"]["object"]["sha"] = "d" * 40
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "main ref SHA"):
            _validate({role: _json(value) for role, value in documents.items()})

    def test_workflow_identity_tag_push_and_first_attempt_are_exact(self):
        cases = (
            ("name", "Other"),
            ("path", ".github/workflows/other.yml"),
            ("event", "workflow_dispatch"),
            ("head_branch", "main"),
            ("head_sha", "d" * 40),
            ("run_attempt", 2),
            ("status", "in_progress"),
            ("conclusion", "failure"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                documents = _fixture_documents()
                documents["linux_runs"]["workflow_runs"][0][field] = value
                with self.assertRaises(tag_ci.TagCIAdmissionError):
                    _validate({name: _json(item) for name, item in documents.items()})

    def test_workflow_head_commit_tree_and_public_repository_are_exact(self):
        documents = _fixture_documents()
        documents["macos_runs"]["workflow_runs"][0]["head_commit"]["tree_id"] = "d" * 40
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "head tree"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        documents["linux_runs"]["workflow_runs"][0]["repository"]["private"] = True
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "private"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        documents["linux_runs"]["workflow_runs"][0]["head_repository"]["full_name"] = "evil/fork"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "full_name"):
            _validate({role: _json(value) for role, value in documents.items()})

    def test_zero_ambiguous_or_paginated_workflow_runs_are_rejected(self):
        for total_count, runs in ((0, []), (2, []), (2, [{}, {}])):
            with self.subTest(total_count=total_count, run_count=len(runs)):
                documents = _fixture_documents()
                documents["linux_runs"] = {
                    "total_count": total_count,
                    "workflow_runs": runs,
                }
                with self.assertRaises(tag_ci.TagCIAdmissionError):
                    _validate({name: _json(item) for name, item in documents.items()})

    def test_job_set_and_job_identity_are_exact(self):
        documents = _fixture_documents()
        documents["linux_jobs"]["jobs"].pop()
        documents["linux_jobs"]["total_count"] = 1
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "job count"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        documents["linux_jobs"]["jobs"][0]["name"] = "unexpected"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "unexpected job"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        documents["linux_jobs"]["jobs"][0]["run_id"] = 999
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "run id"):
            _validate({role: _json(value) for role, value in documents.items()})

    def test_realistic_github_ids_above_signed_32_bit_are_valid_64_bit_ids(self):
        receipt = _validate(_fixture_responses())
        self.assertEqual(
            [workflow["run_id"] for workflow in receipt["workflows"]],
            [LINUX_RUN_ID, MACOS_RUN_ID],
        )
        self.assertTrue(
            all(
                job["job_id"] > 2**31 - 1
                for workflow in receipt["workflows"]
                for job in workflow["jobs"]
            )
        )
        self.assertEqual(
            tag_ci._github_identifier(tag_ci.MAX_GITHUB_ID, "GitHub id"),
            tag_ci.MAX_GITHUB_ID,
        )
        for invalid in (True, 0, tag_ci.MAX_GITHUB_ID + 1):
            with self.subTest(invalid=invalid), self.assertRaises(
                tag_ci.TagCIAdmissionError
            ):
                tag_ci._github_identifier(invalid, "GitHub id")

    def test_every_job_and_step_must_complete_success_without_skips(self):
        mutations = (
            ("job status", lambda job: job.__setitem__("status", "queued")),
            ("job conclusion", lambda job: job.__setitem__("conclusion", "neutral")),
            (
                "step status",
                lambda job: job["steps"][0].__setitem__("status", "in_progress"),
            ),
            (
                "step skipped",
                lambda job: job["steps"][0].__setitem__("conclusion", "skipped"),
            ),
            ("no steps", lambda job: job.__setitem__("steps", [])),
        )
        for label, mutation in mutations:
            with self.subTest(label=label):
                documents = _fixture_documents()
                mutation(documents["macos_jobs"]["jobs"][0])
                with self.assertRaises(tag_ci.TagCIAdmissionError):
                    _validate({name: _json(item) for name, item in documents.items()})

    def test_every_job_requires_one_successful_exact_tag_ref_assertion_step(self):
        documents = _fixture_documents()
        documents["linux_jobs"]["jobs"][0]["steps"][0]["name"] = "Generic ref check"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "tag-ref assertion"):
            _validate({role: _json(value) for role, value in documents.items()})
        documents = _fixture_documents()
        duplicate = copy.deepcopy(documents["macos_jobs"]["jobs"][0]["steps"][0])
        duplicate["number"] = 4
        documents["macos_jobs"]["jobs"][0]["steps"].append(duplicate)
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "tag-ref assertion"):
            _validate({role: _json(value) for role, value in documents.items()})

    def test_strict_json_and_exact_response_roles_are_required(self):
        responses = _fixture_responses()
        responses["tag_ref"] = b'{"ref":"one","ref":"two"}\n'
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "duplicate JSON key"):
            _validate(responses)
        responses = _fixture_responses()
        responses["tag_ref"] = b"\xef\xbb\xbf{}\n"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "BOM"):
            _validate(responses)
        responses = _fixture_responses()
        responses["tag_ref"] = b'{"value":NaN}\n'
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "non-finite"):
            _validate(responses)
        responses = _fixture_responses()
        responses["extra"] = b"{}\n"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "roles are not exact"):
            _validate(responses)
        responses = _fixture_responses()
        responses["tag_ref"] = bytearray(responses["tag_ref"])
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "immutable bytes"):
            _validate(responses)

    def test_response_and_input_bounds_fail_closed(self):
        responses = _fixture_responses()
        responses["tag_ref"] = b"{" + b" " * tag_ci.MAX_RESPONSE_BYTES + b"}"
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "byte limit"):
            _validate(responses)
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "safe single"):
            tag_ci.validate_saved_tag_ci(
                _fixture_responses(),
                expected_tag="refs/tags/escape",
                expected_commit=COMMIT,
                expected_tree=TREE,
            )
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "active V15 contour"):
            tag_ci.validate_saved_tag_ci(
                _fixture_responses(),
                expected_tag="corelm-portfolio-v16",
                expected_commit=COMMIT,
                expected_tree=TREE,
            )
        with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "lowercase 40-hex"):
            tag_ci.validate_saved_tag_ci(
                _fixture_responses(),
                expected_tag=TAG,
                expected_commit=COMMIT.upper(),
                expected_tree=TREE,
            )


class _FakeResponse:
    def __init__(self, url, raw, *, final_url=None, status=200, content_type="application/json"):
        self._url = final_url or url
        self._raw = raw
        self.status = status
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(raw)),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url

    def read(self, limit):
        return self._raw[:limit]


class _FakeOpener:
    def __init__(self, routes, *, redirected_url=None):
        self.routes = routes
        self.redirected_url = redirected_url
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        raw = self.routes[request.full_url]
        final_url = self.redirected_url if len(self.requests) == 1 else None
        return _FakeResponse(request.full_url, raw, final_url=final_url)


class PublicTagCIFetchTests(unittest.TestCase):
    def _routes(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        return {
            descriptor["url"]: responses[descriptor["role"]]
            for descriptor in receipt["responses"]
        }

    def test_fetch_uses_only_anonymous_bounded_https_and_validates_before_return(self):
        opener = _FakeOpener(self._routes())
        with patch.object(tag_ci, "_build_https_opener", return_value=opener):
            responses = tag_ci.fetch_public_tag_ci_responses(
                repository=REPOSITORY,
                expected_tag=TAG,
                expected_commit=COMMIT,
                expected_tree=TREE,
                timeout_seconds=7,
            )
        self.assertEqual(set(responses), set(_fixture_responses()))
        self.assertEqual(len(opener.requests), 8)
        for request, timeout in opener.requests:
            self.assertEqual(timeout, 7.0)
            self.assertTrue(request.full_url.startswith("https://api.github.com/repos/"))
            if "/actions/workflows/" in request.full_url:
                self.assertNotIn("status=", request.full_url)
            headers = {name.lower(): value for name, value in request.header_items()}
            self.assertNotIn("authorization", headers)
            self.assertEqual(headers["x-github-api-version"], tag_ci.API_VERSION)
            self.assertEqual(request.get_method(), "GET")

    def test_fetch_rejects_redirect_even_if_final_payload_is_valid(self):
        opener = _FakeOpener(
            self._routes(), redirected_url="https://api.github.com/repos/evil/repository"
        )
        with patch.object(tag_ci, "_build_https_opener", return_value=opener):
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "redirected"):
                tag_ci.fetch_public_tag_ci_responses(
                    expected_tag=TAG,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )

    def test_fetch_refuses_invalid_timeout_and_non_github_urls(self):
        for timeout in (0, 31, float("nan"), True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(tag_ci.TagCIAdmissionError):
                    tag_ci.fetch_public_tag_ci_responses(
                        expected_tag=TAG,
                        expected_commit=COMMIT,
                        expected_tree=TREE,
                        timeout_seconds=timeout,
                    )
        for url in (
            "http://api.github.com/repos/a/b",
            "https://api.github.com:443/repos/a/b",
            "https://user@api.github.com/repos/a/b",
            "https://github.com/repos/a/b",
            "https://api.github.com/repos/a/b#fragment",
        ):
            with self.subTest(url=url):
                with self.assertRaises(tag_ci.TagCIAdmissionError):
                    tag_ci._validate_api_url(url)

    def test_fetch_stops_on_invalid_public_tag_before_workflow_requests(self):
        routes = self._routes()
        first_url = f"https://api.github.com/repos/{REPOSITORY}/git/ref/tags/{TAG}"
        value = json.loads(routes[first_url])
        value["object"]["type"] = "commit"
        routes[first_url] = _json(value)
        opener = _FakeOpener(routes)
        with patch.object(tag_ci, "_build_https_opener", return_value=opener):
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "object type"):
                tag_ci.fetch_public_tag_ci_responses(
                    expected_tag=TAG,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )
        self.assertEqual(len(opener.requests), 1)


class _CapturedStdout:
    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, value):
        return len(value)

    def flush(self):
        return None


class SavedResponseBundleTests(unittest.TestCase):
    def test_bundle_round_trip_has_fixed_names_and_owner_only_modes(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "public-tag-ci"
            written = tag_ci.write_response_bundle(destination, responses, receipt)
            self.assertEqual(written, destination.resolve())
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
            expected_names = set(tag_ci.RESPONSE_FILENAMES.values()) | {
                tag_ci.PUBLIC_RECEIPT_FILENAME
            }
            self.assertEqual({path.name for path in destination.iterdir()}, expected_names)
            for path in destination.iterdir():
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            loaded, recomputed = tag_ci.read_response_bundle(
                destination,
                expected_tag=TAG,
                expected_commit=COMMIT,
                expected_tree=TREE,
            )
        self.assertEqual(loaded, responses)
        self.assertEqual(recomputed, receipt)

    def test_writer_refuses_existing_destination_and_forged_receipt(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "public-tag-ci"
            destination.mkdir()
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "must not already exist"):
                tag_ci.write_response_bundle(destination, responses, receipt)
            forged = copy.deepcopy(receipt)
            forged["status"] = "FAIL"
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "recomputed receipt"):
                tag_ci.write_response_bundle(
                    Path(temporary) / "forged", responses, forged
                )

    def test_reader_rejects_extra_files_symlinks_and_response_tampering(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        with tempfile.TemporaryDirectory() as temporary:
            extra = tag_ci.write_response_bundle(
                Path(temporary) / "extra", responses, receipt
            )
            (extra / "unexpected.json").write_bytes(b"{}\n")
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "file set is not exact"):
                tag_ci.read_response_bundle(
                    extra,
                    expected_tag=TAG,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )

            symlinked = tag_ci.write_response_bundle(
                Path(temporary) / "symlinked", responses, receipt
            )
            victim = symlinked / tag_ci.RESPONSE_FILENAMES["tag_ref"]
            victim.unlink()
            victim.symlink_to(symlinked / tag_ci.RESPONSE_FILENAMES["main_ref"])
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "regular file"):
                tag_ci.read_response_bundle(
                    symlinked,
                    expected_tag=TAG,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )

            tampered = tag_ci.write_response_bundle(
                Path(temporary) / "tampered", responses, receipt
            )
            response_path = tampered / tag_ci.RESPONSE_FILENAMES["main_ref"]
            response_path.write_bytes(response_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "does not match recomputed"):
                tag_ci.read_response_bundle(
                    tampered,
                    expected_tag=TAG,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )

    def test_reader_requires_exact_canonical_saved_receipt(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        with tempfile.TemporaryDirectory() as temporary:
            destination = tag_ci.write_response_bundle(
                Path(temporary) / "noncanonical", responses, receipt
            )
            receipt_path = destination / tag_ci.PUBLIC_RECEIPT_FILENAME
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="ascii")
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "not canonical JSON"):
                tag_ci.read_response_bundle(
                    destination,
                    expected_tag=TAG,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )

    def test_verify_saved_cli_emits_the_canonical_recomputed_receipt(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        with tempfile.TemporaryDirectory() as temporary:
            destination = tag_ci.write_response_bundle(
                Path(temporary) / "cli", responses, receipt
            )
            captured = _CapturedStdout()
            with patch.object(tag_ci.sys, "stdout", captured):
                status = tag_ci.main(
                    [
                        "verify-saved",
                        "--tag",
                        TAG,
                        "--commit",
                        COMMIT,
                        "--tree",
                        TREE,
                        "--response-directory",
                        str(destination),
                    ]
                )
        self.assertEqual(status, 0)
        self.assertEqual(captured.buffer.getvalue(), tag_ci.canonical_receipt_bytes(receipt))

    def test_fetch_cli_uses_fixed_bundle_contract_without_live_network(self):
        responses = _fixture_responses()
        receipt = _validate(responses)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "fetched"
            captured = _CapturedStdout()
            with (
                patch.object(
                    tag_ci,
                    "fetch_public_tag_ci_responses",
                    return_value=responses,
                ),
                patch.object(tag_ci.sys, "stdout", captured),
            ):
                status = tag_ci.main(
                    [
                        "fetch",
                        "--tag",
                        TAG,
                        "--commit",
                        COMMIT,
                        "--tree",
                        TREE,
                        "--output-directory",
                        str(destination),
                    ]
                )
            loaded, recomputed = tag_ci.read_response_bundle(
                destination,
                expected_tag=TAG,
                expected_commit=COMMIT,
                expected_tree=TREE,
            )
        self.assertEqual(status, 0)
        self.assertEqual(loaded, responses)
        self.assertEqual(recomputed, receipt)
        self.assertEqual(captured.buffer.getvalue(), tag_ci.canonical_receipt_bytes(receipt))


class LocalPinnedTagTrustTests(unittest.TestCase):
    def _repository(self, temporary):
        root = Path(temporary) / "repository"
        (root / "signing").mkdir(parents=True)
        (root / ".git/info").mkdir(parents=True)
        (root / "signing/corelm-codec-signing.pub").write_bytes(
            (ROOT / "signing/corelm-codec-signing.pub").read_bytes()
        )
        (root / "signing/allowed_signers").write_bytes(
            (ROOT / "signing/allowed_signers").read_bytes()
        )
        return root

    def _command_side_effect(self, root, calls, *, valid_signature=True):
        def execute(arguments, *, cwd):
            calls.append(arguments)
            if arguments[0] == tag_ci.SSH_KEYGEN:
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    (
                        f"256 {tag_ci.EXPECTED_FINGERPRINT} "
                        "Ivan Tyshchenko core-lm-cross-model-v4 signing (ED25519)\n"
                    ).encode("ascii"),
                    b"",
                )
            if "verify-tag" in arguments:
                stderr = (
                    (
                        f'Good "git" signature for {tag_ci.EXPECTED_SIGNING_PRINCIPAL} '
                        f"with ED25519 key {tag_ci.EXPECTED_FINGERPRINT}\n"
                    ).encode("ascii")
                    if valid_signature
                    else b'Good "git" signature for attacker@example.com\n'
                )
                return subprocess.CompletedProcess(arguments, 0, b"", stderr)
            if "for-each-ref" in arguments:
                return subprocess.CompletedProcess(arguments, 0, b"", b"")
            if "cat-file" in arguments:
                return subprocess.CompletedProcess(arguments, 0, b"tag\n", b"")
            if "rev-parse" in arguments:
                target = arguments[-1]
                if target == "--absolute-git-dir":
                    stdout = f"{root / '.git'}\n".encode("ascii")
                elif target.endswith("^{commit}"):
                    stdout = f"{COMMIT}\n".encode("ascii")
                elif target.endswith("^{tree}"):
                    stdout = f"{TREE}\n".encode("ascii")
                else:
                    stdout = f"{TAG_OBJECT}\n".encode("ascii")
                return subprocess.CompletedProcess(arguments, 0, stdout, b"")
            raise AssertionError(f"unexpected command: {arguments}")

        return execute

    def test_local_tag_is_bound_to_public_object_and_hard_pinned_ssh_trust(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repository(temporary)
            calls = []
            side_effect = self._command_side_effect(root, calls)
            with patch.object(tag_ci, "_run_local_command", side_effect=side_effect):
                receipt = tag_ci.verify_local_tag_trust(
                    root,
                    expected_tag=TAG,
                    expected_tag_object=TAG_OBJECT,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["tag_object"], TAG_OBJECT)
        self.assertEqual(receipt["fingerprint"], tag_ci.EXPECTED_FINGERPRINT)
        verification = next(arguments for arguments in calls if "verify-tag" in arguments)
        self.assertIn(f"gpg.ssh.program={tag_ci.SSH_KEYGEN}", verification)
        policy_option = next(
            item for item in verification if item.startswith("gpg.ssh.allowedSignersFile=")
        )
        self.assertNotEqual(
            policy_option,
            f"gpg.ssh.allowedSignersFile={root / 'signing/allowed_signers'}",
        )

    def test_mutable_checkout_trust_cannot_replace_hard_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repository(temporary)
            (root / "signing/corelm-codec-signing.pub").write_bytes(b"attacker key\n")
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "hard pin"):
                tag_ci.verify_local_tag_trust(
                    root,
                    expected_tag=TAG,
                    expected_tag_object=TAG_OBJECT,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )

    def test_local_tag_object_must_equal_public_api_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repository(temporary)
            calls = []
            side_effect = self._command_side_effect(root, calls)
            with patch.object(tag_ci, "_run_local_command", side_effect=side_effect):
                with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "local tag object"):
                    tag_ci.verify_local_tag_trust(
                        root,
                        expected_tag=TAG,
                        expected_tag_object="d" * 40,
                        expected_commit=COMMIT,
                        expected_tree=TREE,
                    )

    def test_local_signature_output_must_bind_exact_principal_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repository(temporary)
            calls = []
            side_effect = self._command_side_effect(root, calls, valid_signature=False)
            with patch.object(tag_ci, "_run_local_command", side_effect=side_effect):
                with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "signature is invalid"):
                    tag_ci.verify_local_tag_trust(
                        root,
                        expected_tag=TAG,
                        expected_tag_object=TAG_OBJECT,
                        expected_commit=COMMIT,
                        expected_tree=TREE,
                    )

    def test_symlink_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._repository(temporary)
            link = Path(temporary) / "repository-link"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(tag_ci.TagCIAdmissionError, "not a symlink"):
                tag_ci.verify_local_tag_trust(
                    link,
                    expected_tag=TAG,
                    expected_tag_object=TAG_OBJECT,
                    expected_commit=COMMIT,
                    expected_tree=TREE,
                )


if __name__ == "__main__":
    unittest.main()
