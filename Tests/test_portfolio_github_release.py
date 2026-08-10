import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publication import build_portfolio_release as portfolio  # noqa: E402
from publication import verify_portfolio_github_release as github_release  # noqa: E402
from security import automated_media  # noqa: E402


TAG = "corelm-portfolio-v15"
FUTURE_TAG = "corelm-portfolio-v16"
DRAFT_SLUG = "untagged-0123456789abcdefabcd"
COMMIT = "1" * 40
TREE = "2" * 40
TAG_OBJECT = "3" * 40
C1_COMMIT = "7" * 40
C1_TREE = "8" * 40
EXPECTED_TITLE = (
    "Core LM Portfolio v15 — reproducible real-model KV-cache benchmark"
)
FAKE_SIGNATURE = (
    "-----BEGIN SSH SIGNATURE-----\n"
    "fixture\n"
    "-----END SSH SIGNATURE-----\n"
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


class PortfolioGitHubReleaseTests(unittest.TestCase):
    def _identity(self):
        return {
            "schema_version": 2,
            "artifact_kind": "corelm_portfolio_release",
            "claims": {
                "excluded": [
                    "model_weight_compression",
                    "universal_llm_generalization",
                    "state_of_the_art",
                    "production_serving_readiness",
                    "independent_human_replication",
                ],
                "supported": (
                    "Built and reproducibly evaluated complete-container KV-cache "
                    "compression on pinned real-model workloads."
                ),
            },
            "continuous_integration": {
                "commit": COMMIT,
                "linux_x86_64": {
                    "conclusion": "success",
                    "required": True,
                    "url": (
                        "https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/101"
                    ),
                },
                "macos_arm64": {
                    "conclusion": "success",
                    "required": True,
                    "url": (
                        "https://github.com/ALLPROTO/core-lm-benchmark/actions/runs/102"
                    ),
                },
                "validation": portfolio.CI_VALIDATION_SCOPE,
            },
            "demo": {
                "evidence_sha256": "4" * 64,
                "provenance_sha256": "7" * 64,
                "result_sha256": "5" * 64,
                "synthetic_data": False,
                "video_sha256": "6" * 64,
                "workload_classification": (
                    "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION"
                ),
                "media_classification": automated_media.MEDIA_CLASSIFICATION,
                "automation_contract": automated_media.AUTOMATION_CONTRACT,
                "automation_only": True,
                "human_reviewed": False,
                "manual_edits": False,
                "machine_evidence": False,
                "pixel_semantics_verified": False,
            },
            "related_sources": {
                "blind_v1_draft": {
                    "lifecycle_state": "CHECKPOINT_MISSED_TERMINAL_DRAFT"
                }
            },
            "release": {
                "prerelease": False,
                "scientific_status": "NOT_A_BLIND_OR_GENERALIZATION_RESULT",
                "tag": TAG,
                "url": f"{portfolio.CANONICAL_REPOSITORY}/releases/tag/{TAG}",
            },
            "source": {
                "commit": COMMIT,
                "default_branch": "main",
                "repository": portfolio.CANONICAL_REPOSITORY,
                "tag_object": TAG_OBJECT,
                "tree": TREE,
                "worktree_state": "clean",
            },
        }

    def _fixture(self, temporary):
        base = Path(temporary)
        assets = base / "assets"
        api_dir = base / "api-inputs"
        receipts = base / "receipts"
        requests = base / "requests"
        successor = base / "successor"
        for directory in (assets, api_dir, receipts, requests, successor):
            directory.mkdir()
        ffprobe = base / "ffprobe"
        ffprobe.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'ffprobe version fixture-1'\n",
            encoding="ascii",
        )
        ffprobe.chmod(0o700)

        identity = self._identity()
        for name in portfolio.asset_names(TAG):
            payload = (
                _canonical(identity)
                if name.endswith("-source-identity.json")
                else f"fixture:{name}\n".encode("utf-8")
            )
            (assets / name).write_bytes(payload)
        observed_tag, observed_identity, records = github_release._asset_records(assets)
        self.assertEqual(observed_tag, TAG)
        request = github_release.expected_create_request(observed_identity, records)
        publish_request = github_release.expected_publish_request(
            observed_identity, records
        )
        published_assets = [
            {
                "browser_download_url": (
                    f"{portfolio.CANONICAL_REPOSITORY}/releases/download/{TAG}/"
                    f"{record['name']}"
                ),
                "digest": f"sha256:{record['sha256']}",
                "id": index,
                "name": record["name"],
                "size": record["size_bytes"],
                "state": "uploaded",
            }
            for index, record in enumerate(records, start=1)
        ]
        draft_assets = copy.deepcopy(published_assets)
        for asset in draft_assets:
            asset["browser_download_url"] = (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                f"{DRAFT_SLUG}/{asset['name']}"
            )
        release = {
            "assets": published_assets,
            "assets_url": (
                "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/"
                "releases/901/assets"
            ),
            "body": request["body"],
            "draft": False,
            "html_url": f"{portfolio.CANONICAL_REPOSITORY}/releases/tag/{TAG}",
            "id": 901,
            "immutable": True,
            "name": request["name"],
            "prerelease": False,
            "published_at": "2026-08-10T12:34:56Z",
            "tag_name": TAG,
            "target_commitish": "main",
            "url": (
                "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/"
                "releases/901"
            ),
        }
        upload_url = (
            "https://uploads.github.com/repos/ALLPROTO/core-lm-benchmark/"
            "releases/901/assets{?name,label}"
        )
        create_response = {
            "assets": [],
            "assets_url": release["assets_url"],
            "body": request["body"],
            "draft": True,
            "html_url": (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/tag/{DRAFT_SLUG}"
            ),
            "id": 901,
            "immutable": False,
            "name": request["name"],
            "prerelease": False,
            "published_at": None,
            "tag_name": TAG,
            "target_commitish": "main",
            "upload_url": upload_url,
            "url": release["url"],
        }
        draft = copy.deepcopy(create_response)
        draft["assets"] = draft_assets
        release_id = copy.deepcopy(release)
        release_tag = copy.deepcopy(release)
        latest = copy.deepcopy(release)
        tag_ref = {
            "object": {"sha": TAG_OBJECT, "type": "tag"},
            "ref": f"refs/tags/{TAG}",
        }
        tag_payload = (
            f"object {COMMIT}\n"
            "type commit\n"
            f"tag {TAG}\n"
            "tagger Ivan Tyshchenko <fixture@example.invalid> 0 +0000\n\n"
            "Portfolio release\n"
        )
        tag_object = {
            "object": {"sha": COMMIT, "type": "commit"},
            "sha": TAG_OBJECT,
            "tag": TAG,
            "verification": {
                "payload": tag_payload,
                "reason": "unknown_signature_type",
                "signature": FAKE_SIGNATURE,
                "verified": False,
            },
        }
        commit_object = {
            "sha": COMMIT,
            "tree": {"sha": TREE},
            "verification": {"reason": "unsigned", "verified": False},
        }
        values = {
            "create_response": create_response,
            "draft": draft,
            "immutable_policy_precreate": {
                "enabled": True,
                "enforced_by_owner": False,
            },
            "immutable_policy_prepublish": {
                "enabled": True,
                "enforced_by_owner": True,
            },
            "release": release,
            "release_id": release_id,
            "release_tag": release_tag,
            "latest": latest,
            "tag_ref": tag_ref,
            "tag_object": tag_object,
            "commit_object": commit_object,
        }
        paths = {}
        for name, value in values.items():
            path = api_dir / f"{name}.json"
            self._replace_json(path, value)
            paths[name] = path
        return {
            "api_dir": api_dir,
            "assets": assets,
            "base": base,
            "ffprobe": ffprobe,
            "identity": identity,
            "paths": paths,
            "receipts": receipts,
            "records": records,
            "publish_request": publish_request,
            "request": request,
            "requests": requests,
            "successor": successor,
            "values": values,
        }

    def _artifact_result(self):
        return {
            "status": "OFFLINE_ARTIFACT_PASS",
            "tag": TAG,
            "commit": COMMIT,
            "tree": TREE,
            "asset_count": 14,
        }

    def _verification_patches(self, *, artifact=None):
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                github_release,
                "verify_release",
                return_value=self._artifact_result() if artifact is None else artifact,
            )
        )
        stack.enter_context(
            patch.object(
                github_release,
                "_verify_git_payload_signature",
                return_value={
                    "api_reason": "unknown_signature_type",
                    "api_verified": False,
                    "cryptographic_verification": "SSH_GIT_NAMESPACE_PASS",
                    "scope": (
                        "API_VERDICT_INFORMATIONAL_LOCAL_SSH_VERIFICATION_REQUIRED"
                    ),
                },
            )
        )
        return stack

    def _verify(self, fixture):
        paths = fixture["paths"]
        with self._verification_patches():
            return github_release.verify_saved_responses(
                assets=fixture["assets"],
                ffprobe=fixture["ffprobe"],
                release_id_json=paths["release_id"],
                release_tag_json=paths["release_tag"],
                latest_json=paths["latest"],
                tag_ref_json=paths["tag_ref"],
                tag_object_json=paths["tag_object"],
                commit_object_json=paths["commit_object"],
            )

    def _verify_empty_draft(self, fixture):
        with self._verification_patches():
            return github_release.verify_empty_draft_response(
                assets=fixture["assets"],
                ffprobe=fixture["ffprobe"],
                create_response_json=fixture["paths"]["create_response"],
            )

    def _verify_draft(self, fixture):
        paths = fixture["paths"]
        with self._verification_patches():
            return github_release.verify_draft_saved_responses(
                assets=fixture["assets"],
                ffprobe=fixture["ffprobe"],
                create_response_json=paths["create_response"],
                draft_json=paths["draft"],
                immutable_policy_json=paths["immutable_policy_prepublish"],
                tag_ref_json=paths["tag_ref"],
                tag_object_json=paths["tag_object"],
                commit_object_json=paths["commit_object"],
            )

    def _replace_json(self, path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def _verify_cli_arguments(self, fixture, receipt):
        paths = fixture["paths"]
        return [
            "verify",
            "--assets",
            str(fixture["assets"]),
            "--ffprobe",
            str(fixture["ffprobe"]),
            "--release-id-json",
            str(paths["release_id"]),
            "--release-tag-json",
            str(paths["release_tag"]),
            "--latest-json",
            str(paths["latest"]),
            "--tag-ref-json",
            str(paths["tag_ref"]),
            "--tag-object-json",
            str(paths["tag_object"]),
            "--commit-object-json",
            str(paths["commit_object"]),
            "--receipt",
            str(receipt),
        ]

    def _verify_empty_draft_cli_arguments(self, fixture, receipt):
        return [
            "verify-empty-draft",
            "--assets",
            str(fixture["assets"]),
            "--ffprobe",
            str(fixture["ffprobe"]),
            "--create-response-json",
            str(fixture["paths"]["create_response"]),
            "--receipt",
            str(receipt),
        ]

    def _verify_policy_cli_arguments(self, fixture, receipt):
        return [
            "verify-policy",
            "--immutable-policy-json",
            str(fixture["paths"]["immutable_policy_precreate"]),
            "--receipt",
            str(receipt),
        ]

    def _verify_draft_cli_arguments(self, fixture, publish_request, receipt):
        paths = fixture["paths"]
        return [
            "verify-draft",
            "--assets",
            str(fixture["assets"]),
            "--ffprobe",
            str(fixture["ffprobe"]),
            "--create-response-json",
            str(paths["create_response"]),
            "--draft-json",
            str(paths["draft"]),
            "--immutable-policy-json",
            str(paths["immutable_policy_prepublish"]),
            "--tag-ref-json",
            str(paths["tag_ref"]),
            "--tag-object-json",
            str(paths["tag_object"]),
            "--commit-object-json",
            str(paths["commit_object"]),
            "--publish-request",
            str(publish_request),
            "--receipt",
            str(receipt),
        ]

    def test_exact_title_and_request_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            request = fixture["request"]
            self.assertEqual(request["name"], EXPECTED_TITLE)
            self.assertEqual(request["tag_name"], TAG)
            self.assertEqual(request["target_commitish"], "main")
            self.assertEqual(request["make_latest"], "false")
            self.assertIs(request["draft"], True)
            self.assertIs(request["prerelease"], False)
            self.assertIn(EXPECTED_TITLE, request["body"])
            self.assertIn("NOT_A_BLIND_OR_GENERALIZATION_RESULT", request["body"])
            publish = fixture["publish_request"]
            self.assertEqual(set(publish), set(request))
            self.assertEqual(publish["name"], EXPECTED_TITLE)
            self.assertEqual(publish["tag_name"], TAG)
            self.assertEqual(publish["target_commitish"], "main")
            self.assertEqual(publish["make_latest"], "true")
            self.assertIs(publish["draft"], False)
            self.assertIs(publish["prerelease"], False)
            self.assertEqual(publish["body"], request["body"])

    def test_precreate_policy_requires_exact_two_boolean_response(self):
        cases = {
            "false": {"enabled": False, "enforced_by_owner": False},
            "missing": {},
            "missing-owner": {"enabled": True},
            "missing-enabled": {"enforced_by_owner": True},
            "extra": {
                "enabled": True,
                "enforced_by_owner": True,
                "unexpected": True,
            },
            "nonboolean-enabled-integer": {
                "enabled": 1,
                "enforced_by_owner": True,
            },
            "nonboolean-enabled-string": {
                "enabled": "true",
                "enforced_by_owner": True,
            },
            "nonboolean-owner-integer": {
                "enabled": True,
                "enforced_by_owner": 1,
            },
            "nonboolean-owner-string": {
                "enabled": True,
                "enforced_by_owner": "false",
            },
            "nonboolean-owner-null": {
                "enabled": True,
                "enforced_by_owner": None,
            },
        }
        for enforced_by_owner in (False, True):
            with self.subTest(
                enforced_by_owner=enforced_by_owner
            ), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                policy_path = fixture["paths"]["immutable_policy_precreate"]
                self._replace_json(
                    policy_path,
                    {
                        "enabled": True,
                        "enforced_by_owner": enforced_by_owner,
                    },
                )
                receipt = github_release.verify_immutable_policy_response(
                    immutable_policy_json=policy_path
                )
                self.assertEqual(
                    receipt["status"],
                    "PRECREATE_IMMUTABLE_POLICY_BOUNDARY_PASS",
                )
                self.assertEqual(receipt["schema_version"], 2)
                self.assertEqual(
                    receipt["api_snapshot"]["kind"],
                    "immutable_policy_precreate",
                )
                self.assertEqual(
                    receipt["api_snapshot"]["sha256"],
                    hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    receipt["github_immutable_releases_policy"],
                    {
                        "enabled": True,
                        "enforced_by_owner": enforced_by_owner,
                        "endpoint": github_release.IMMUTABLE_RELEASES_ENDPOINT,
                    },
                )
                self.assertNotEqual(
                    policy_path,
                    fixture["paths"]["immutable_policy_prepublish"],
                )
        for case, value in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                self._replace_json(
                    fixture["paths"]["immutable_policy_precreate"], value
                )
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError,
                    "immutable-releases policy response",
                ):
                    github_release.verify_immutable_policy_response(
                        immutable_policy_json=(
                            fixture["paths"]["immutable_policy_precreate"]
                        )
                    )

    def test_empty_and_populated_draft_boundaries_pass_exact_same_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            empty = self._verify_empty_draft(fixture)
            self.assertEqual(empty["status"], "EMPTY_DRAFT_UPLOAD_BOUNDARY_PASS")
            self.assertEqual(empty["schema_version"], 1)
            self.assertEqual(empty["github_draft"]["asset_count"], 0)
            self.assertEqual(empty["github_draft"]["id"], 901)
            self.assertIs(empty["github_draft"]["immutable"], False)
            self.assertEqual(
                empty["github_draft"]["upload_url"],
                fixture["values"]["create_response"]["upload_url"],
            )

            populated = self._verify_draft(fixture)
            self.assertEqual(
                populated["status"], "POPULATED_DRAFT_PUBLISH_BOUNDARY_PASS"
            )
            self.assertEqual(populated["schema_version"], 2)
            self.assertEqual(populated["github_draft"]["asset_count"], 14)
            self.assertEqual(populated["github_draft"]["id"], 901)
            self.assertIs(populated["github_draft"]["immutable"], False)
            self.assertEqual(
                populated["publish_endpoint"],
                "https://api.github.com/repos/ALLPROTO/core-lm-benchmark/releases/901",
            )
            self.assertEqual(populated["publish_request"], fixture["publish_request"])
            self.assertEqual(
                populated["github_immutable_releases_policy"],
                {
                    "enabled": True,
                    "enforced_by_owner": True,
                    "endpoint": github_release.IMMUTABLE_RELEASES_ENDPOINT,
                },
            )
            policy_snapshot = next(
                item
                for item in populated["api_snapshots"]
                if item["kind"] == "immutable_policy_prepublish"
            )
            self.assertEqual(
                policy_snapshot["sha256"],
                hashlib.sha256(
                    fixture["paths"]["immutable_policy_prepublish"].read_bytes()
                ).hexdigest(),
            )

    def test_empty_draft_rejects_nonempty_or_inexact_create_response(self):
        cases = (
            "asset",
            "body",
            "draft",
            "id",
            "immutable",
            "published",
            "tag",
            "target",
            "upload_url",
            "url",
            "assets_url",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                value = fixture["values"]["create_response"]
                if case == "asset":
                    value["assets"] = [copy.deepcopy(fixture["values"]["draft"]["assets"][0])]
                elif case == "body":
                    value["body"] = "edited"
                elif case == "draft":
                    value["draft"] = False
                elif case == "id":
                    value["id"] = 0
                elif case == "immutable":
                    value["immutable"] = True
                elif case == "published":
                    value["published_at"] = "2026-08-10T12:34:56Z"
                elif case == "tag":
                    value["tag_name"] = FUTURE_TAG
                elif case == "target":
                    value["target_commitish"] = COMMIT
                elif case == "upload_url":
                    value["upload_url"] += "-wrong"
                elif case == "url":
                    value["url"] += "-wrong"
                else:
                    value["assets_url"] += "-wrong"
                self._replace_json(fixture["paths"]["create_response"], value)
                with self.assertRaises(portfolio.PortfolioReleaseError):
                    self._verify_empty_draft(fixture)

    def test_draft_html_url_requires_exact_lowercase_untagged_slug(self):
        repository = portfolio.CANONICAL_REPOSITORY
        cases = {
            "published-tag": f"{repository}/releases/tag/{TAG}",
            "uppercase": (
                f"{repository}/releases/tag/"
                "untagged-0123456789ABCDEFABCD"
            ),
            "nonhex": (
                f"{repository}/releases/tag/"
                "untagged-g123456789abcdefabcd"
            ),
            "short": f"{repository}/releases/tag/{DRAFT_SLUG[:-1]}",
            "long": f"{repository}/releases/tag/{DRAFT_SLUG}0",
            "query": f"{repository}/releases/tag/{DRAFT_SLUG}?draft=1",
            "fragment": f"{repository}/releases/tag/{DRAFT_SLUG}#draft",
            "foreign-repository": (
                f"https://github.com/ALLPROTO/other/releases/tag/{DRAFT_SLUG}"
            ),
            "download-path": (
                f"{repository}/releases/download/{DRAFT_SLUG}"
            ),
        }
        for case, html_url in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                fixture["values"]["create_response"]["html_url"] = html_url
                self._replace_json(
                    fixture["paths"]["create_response"],
                    fixture["values"]["create_response"],
                )
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "html_url"
                ):
                    self._verify_empty_draft(fixture)

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            fixture["values"]["create_response"].pop("html_url")
            self._replace_json(
                fixture["paths"]["create_response"],
                fixture["values"]["create_response"],
            )
            with self.assertRaisesRegex(portfolio.PortfolioReleaseError, "html_url"):
                self._verify_empty_draft(fixture)

    def test_populated_draft_rejects_asset_set_and_identity_mismatches(self):
        cases = (
            "zero-assets",
            "thirteen-assets",
            "extra-asset",
            "digest",
            "release-id",
            "tag",
            "body",
            "draft",
            "immutable",
            "asset-id-zero",
            "asset-id-duplicate",
            "url",
            "assets-url",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                value = fixture["values"]["draft"]
                if case == "zero-assets":
                    value["assets"] = []
                elif case == "thirteen-assets":
                    value["assets"] = value["assets"][:-1]
                elif case == "extra-asset":
                    extra = copy.deepcopy(value["assets"][0])
                    extra["id"] = 99
                    extra["name"] = "unexpected"
                    value["assets"].append(extra)
                elif case == "digest":
                    value["assets"][0]["digest"] = "sha256:" + "0" * 64
                elif case == "release-id":
                    value["id"] = 902
                elif case == "tag":
                    value["tag_name"] = FUTURE_TAG
                elif case == "body":
                    value["body"] = "edited"
                elif case == "draft":
                    value["draft"] = False
                elif case == "immutable":
                    value["immutable"] = True
                elif case == "asset-id-zero":
                    value["assets"][0]["id"] = 0
                elif case == "asset-id-duplicate":
                    value["assets"][1]["id"] = value["assets"][0]["id"]
                elif case == "url":
                    value["url"] += "-wrong"
                else:
                    value["assets_url"] += "-wrong"
                self._replace_json(fixture["paths"]["draft"], value)
                with self.assertRaises(portfolio.PortfolioReleaseError):
                    self._verify_draft(fixture)

    def test_populated_draft_requires_one_create_bound_asset_slug(self):
        replacement_slug = "untagged-fedcba9876543210fedc"

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            draft = fixture["values"]["draft"]
            draft["html_url"] = (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/tag/"
                f"{replacement_slug}"
            )
            for asset in draft["assets"]:
                asset["browser_download_url"] = (
                    f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                    f"{replacement_slug}/{asset['name']}"
                )
            self._replace_json(fixture["paths"]["draft"], draft)
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError,
                "html_url differs from create response",
            ):
                self._verify_draft(fixture)

        asset_urls = {
            "different-untagged": (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                f"{replacement_slug}/{{name}}"
            ),
            "published-tag": (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                f"{TAG}/{{name}}"
            ),
            "uppercase": (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                "untagged-0123456789ABCDEFABCD/{name}"
            ),
            "foreign-repository": (
                "https://github.com/ALLPROTO/other/releases/download/"
                f"{DRAFT_SLUG}/{{name}}"
            ),
            "query": (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                f"{DRAFT_SLUG}/{{name}}?download=1"
            ),
        }
        for case, template in asset_urls.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                first = fixture["values"]["draft"]["assets"][0]
                first["browser_download_url"] = template.format(name=first["name"])
                self._replace_json(
                    fixture["paths"]["draft"], fixture["values"]["draft"]
                )
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "asset URL differs"
                ):
                    self._verify_draft(fixture)

    def test_published_release_rejects_draft_untagged_asset_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            release = fixture["values"]["release_id"]
            first = release["assets"][0]
            first["browser_download_url"] = (
                f"{portfolio.CANONICAL_REPOSITORY}/releases/download/"
                f"{DRAFT_SLUG}/{first['name']}"
            )
            self._replace_json(fixture["paths"]["release_id"], release)
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "asset URL differs"
            ):
                self._verify(fixture)

    def test_publish_patch_request_rejects_every_nonexact_variant(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            cases = {
                "draft": lambda value: value.__setitem__("draft", True),
                "latest": lambda value: value.__setitem__("make_latest", "false"),
                "tag": lambda value: value.__setitem__("tag_name", FUTURE_TAG),
                "body": lambda value: value.__setitem__("body", "edited"),
                "missing": lambda value: value.pop("target_commitish"),
                "extra": lambda value: value.__setitem__("release_id", 901),
            }
            for case, mutate in cases.items():
                with self.subTest(case=case):
                    value = copy.deepcopy(fixture["publish_request"])
                    mutate(value)
                    with self.assertRaisesRegex(
                        portfolio.PortfolioReleaseError,
                        "publish PATCH request is not exact",
                    ):
                        github_release._validate_publish_request(
                            value,
                            identity=fixture["identity"],
                            records=fixture["records"],
                        )

    def test_populated_draft_accepts_false_owner_enforcement_and_binds_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            policy_path = fixture["paths"]["immutable_policy_prepublish"]
            self._replace_json(
                policy_path,
                {"enabled": True, "enforced_by_owner": False},
            )
            populated = self._verify_draft(fixture)
            self.assertEqual(
                populated["github_immutable_releases_policy"],
                {
                    "enabled": True,
                    "enforced_by_owner": False,
                    "endpoint": github_release.IMMUTABLE_RELEASES_ENDPOINT,
                },
            )
            policy_snapshot = next(
                item
                for item in populated["api_snapshots"]
                if item["kind"] == "immutable_policy_prepublish"
            )
            self.assertEqual(
                policy_snapshot["sha256"],
                hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            )

    def test_populated_draft_requires_exact_two_boolean_immutable_policy(self):
        cases = {
            "false": {"enabled": False, "enforced_by_owner": True},
            "missing": {},
            "missing-owner": {"enabled": True},
            "missing-enabled": {"enforced_by_owner": False},
            "extra": {
                "enabled": True,
                "enforced_by_owner": False,
                "unexpected": True,
            },
            "nonboolean-enabled": {
                "enabled": 1,
                "enforced_by_owner": False,
            },
            "nonboolean-owner-integer": {
                "enabled": True,
                "enforced_by_owner": 0,
            },
            "nonboolean-owner-string": {
                "enabled": True,
                "enforced_by_owner": "true",
            },
            "nonboolean-owner-null": {
                "enabled": True,
                "enforced_by_owner": None,
            },
        }
        for case, value in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                self._replace_json(
                    fixture["paths"]["immutable_policy_prepublish"], value
                )
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError,
                    "immutable-releases policy response",
                ):
                    self._verify_draft(fixture)

    def test_draft_gates_require_artifact_and_tag_signature_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            with self._verification_patches(artifact={"status": "FAIL"}):
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "offline signed-artifact"
                ):
                    github_release.verify_empty_draft_response(
                        assets=fixture["assets"],
                        ffprobe=fixture["ffprobe"],
                        create_response_json=fixture["paths"]["create_response"],
                    )
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "offline signed-artifact"
                ):
                    github_release.verify_draft_saved_responses(
                        assets=fixture["assets"],
                        ffprobe=fixture["ffprobe"],
                        create_response_json=fixture["paths"]["create_response"],
                        draft_json=fixture["paths"]["draft"],
                        immutable_policy_json=(
                            fixture["paths"]["immutable_policy_prepublish"]
                        ),
                        tag_ref_json=fixture["paths"]["tag_ref"],
                        tag_object_json=fixture["paths"]["tag_object"],
                        commit_object_json=fixture["paths"]["commit_object"],
                    )

            fixture["values"]["tag_ref"]["object"]["sha"] = "0" * 40
            self._replace_json(
                fixture["paths"]["tag_ref"], fixture["values"]["tag_ref"]
            )
            publish_path = fixture["requests"] / "must-not-exist.json"
            receipt_path = fixture["receipts"] / "must-not-exist.json"
            with self._verification_patches():
                self.assertEqual(
                    github_release.main(
                        self._verify_draft_cli_arguments(
                            fixture, publish_path, receipt_path
                        )
                    ),
                    2,
                )
            self.assertFalse(publish_path.exists())
            self.assertFalse(receipt_path.exists())

    def test_full_artifact_verifier_runs_on_private_snapshot_before_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            observed = {}

            def verifier(snapshot, *, ffprobe):
                observed["snapshot"] = snapshot
                observed["names"] = {entry.name for entry in snapshot.iterdir()}
                observed["ffprobe"] = ffprobe
                self.assertNotEqual(snapshot, fixture["assets"])
                self.assertEqual(len(observed["names"]), 14)
                return self._artifact_result()

            with (
                patch.object(github_release, "verify_release", side_effect=verifier),
                patch.object(
                    github_release,
                    "_verify_git_payload_signature",
                    return_value={
                        "api_verified": False,
                        "cryptographic_verification": "SSH_GIT_NAMESPACE_PASS",
                    },
                ),
            ):
                receipt = github_release.verify_saved_responses(
                    assets=fixture["assets"],
                    ffprobe=fixture["ffprobe"],
                    release_id_json=fixture["paths"]["release_id"],
                    release_tag_json=fixture["paths"]["release_tag"],
                    latest_json=fixture["paths"]["latest"],
                    tag_ref_json=fixture["paths"]["tag_ref"],
                    tag_object_json=fixture["paths"]["tag_object"],
                    commit_object_json=fixture["paths"]["commit_object"],
                )
            self.assertEqual(
                receipt["status"],
                "OFFLINE_ARTIFACT_AND_SAVED_PUBLIC_API_SNAPSHOT_PASS",
            )
            self.assertEqual(
                receipt["artifact_verification"]["status"],
                "OFFLINE_ARTIFACT_PASS",
            )
            self.assertEqual(
                receipt["github_release"]["tag_api_verification"]["api_verified"],
                False,
            )
            self.assertEqual(
                receipt["github_release"]["tag_api_verification"][
                    "cryptographic_verification"
                ],
                "SSH_GIT_NAMESPACE_PASS",
            )
            self.assertFalse(observed["snapshot"].exists())

    def test_no_pass_when_offline_artifact_verifier_does_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            with self._verification_patches(artifact={"status": "FAIL"}):
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "offline signed-artifact"
                ):
                    github_release.verify_saved_responses(
                        assets=fixture["assets"],
                        ffprobe=fixture["ffprobe"],
                        release_id_json=fixture["paths"]["release_id"],
                        release_tag_json=fixture["paths"]["release_tag"],
                        latest_json=fixture["paths"]["latest"],
                        tag_ref_json=fixture["paths"]["tag_ref"],
                        tag_object_json=fixture["paths"]["tag_object"],
                        commit_object_json=fixture["paths"]["commit_object"],
                    )

    def test_api_json_is_read_through_one_nofollow_fd(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            path = fixture["paths"]["release"]
            real_open = os.open
            observed = []

            def tracked_open(candidate, flags, *args, **kwargs):
                if os.fspath(candidate) == os.fspath(path):
                    observed.append(flags)
                return real_open(candidate, flags, *args, **kwargs)

            with patch.object(github_release.os, "open", side_effect=tracked_open):
                value, digest = github_release._snapshot(path, "release JSON")
            self.assertEqual(value["id"], 901)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertEqual(len(observed), 1)
            if hasattr(os, "O_NOFOLLOW"):
                self.assertTrue(observed[0] & os.O_NOFOLLOW)

    def test_every_asset_digest_is_mandatory(self):
        for replacement in (None, ""):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                fixture["values"]["release_id"]["assets"][0]["digest"] = replacement
                self._replace_json(
                    fixture["paths"]["release_id"], fixture["values"]["release_id"]
                )
                with self.assertRaisesRegex(
                    portfolio.PortfolioReleaseError, "asset digest differs"
                ):
                    self._verify(fixture)

    def test_latest_receives_full_release_contract(self):
        mutations = (
            ("body", lambda latest: latest.__setitem__("body", "edited")),
            (
                "target",
                lambda latest: latest.__setitem__("target_commitish", COMMIT),
            ),
            (
                "published",
                lambda latest: latest.__setitem__(
                    "published_at", "2026-08-10T12:34:57Z"
                ),
            ),
            (
                "asset",
                lambda latest: latest["assets"][0].__setitem__(
                    "digest", "sha256:" + "0" * 64
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                mutate(fixture["values"]["latest"])
                self._replace_json(
                    fixture["paths"]["latest"], fixture["values"]["latest"]
                )
                with self.assertRaises(portfolio.PortfolioReleaseError):
                    self._verify(fixture)

    def test_commit_object_binds_source_commit_to_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            fixture["values"]["commit_object"]["tree"]["sha"] = "9" * 40
            self._replace_json(
                fixture["paths"]["commit_object"],
                fixture["values"]["commit_object"],
            )
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "does not bind"
            ):
                self._verify(fixture)

    def test_receipt_has_six_bound_api_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            receipt = self._verify(fixture)
            self.assertEqual(
                {item["kind"] for item in receipt["api_snapshots"]},
                {
                    "release_id",
                    "release_tag",
                    "latest",
                    "tag_ref",
                    "tag_object",
                    "commit_object",
                },
            )
            self.assertEqual(receipt["source"]["commit"], COMMIT)
            self.assertEqual(receipt["source"]["tree"], TREE)
            self.assertEqual(receipt["schema_version"], 2)

    def test_final_release_requires_three_equal_immutable_views_and_asset_ids(self):
        cases = (
            "id",
            "immutable",
            "url",
            "assets-url",
            "asset-id-duplicate",
            "asset-id-different",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                value = fixture["values"]["release_tag"]
                if case == "id":
                    value["id"] = 902
                elif case == "immutable":
                    value["immutable"] = False
                elif case == "url":
                    value["url"] += "-wrong"
                elif case == "assets-url":
                    value["assets_url"] += "-wrong"
                elif case == "asset-id-duplicate":
                    value["assets"][1]["id"] = value["assets"][0]["id"]
                else:
                    value["assets"][0]["id"] = 99
                self._replace_json(fixture["paths"]["release_tag"], value)
                with self.assertRaises(portfolio.PortfolioReleaseError):
                    self._verify(fixture)

    def test_output_and_receipt_cannot_overlap_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            inside_assets = fixture["assets"] / "request.json"
            self.assertEqual(
                github_release.main(
                    [
                        "prepare-draft",
                        "--assets",
                        str(fixture["assets"]),
                        "--ffprobe",
                        str(fixture["ffprobe"]),
                        "--output",
                        str(inside_assets),
                    ]
                ),
                2,
            )
            inside_api = fixture["api_dir"] / "receipt.json"
            self.assertEqual(
                github_release.main(self._verify_cli_arguments(fixture, inside_api)),
                2,
            )
            self.assertFalse(inside_assets.exists())
            self.assertFalse(inside_api.exists())
            inside_policy_api = fixture["api_dir"] / "policy-receipt.json"
            self.assertEqual(
                github_release.main(
                    self._verify_policy_cli_arguments(fixture, inside_policy_api)
                ),
                2,
            )
            self.assertFalse(inside_policy_api.exists())
            inside_draft_api = fixture["api_dir"] / "publish.json"
            outside_receipt = fixture["receipts"] / "populated.json"
            self.assertEqual(
                github_release.main(
                    self._verify_draft_cli_arguments(
                        fixture, inside_draft_api, outside_receipt
                    )
                ),
                2,
            )
            self.assertFalse(inside_draft_api.exists())
            self.assertFalse(outside_receipt.exists())

            same_parent_publish = fixture["requests"] / "publish.json"
            same_parent_receipt = fixture["requests"] / "populated-receipt.json"
            self.assertEqual(
                github_release.main(
                    self._verify_draft_cli_arguments(
                        fixture, same_parent_publish, same_parent_receipt
                    )
                ),
                2,
            )
            self.assertFalse(same_parent_publish.exists())
            self.assertFalse(same_parent_receipt.exists())

    def test_valid_cli_outputs_are_canonical_and_nonoverwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            request_path = fixture["requests"] / "request.json"
            policy_receipt_path = fixture["receipts"] / "policy-receipt.json"
            empty_receipt_path = fixture["receipts"] / "empty-draft-receipt.json"
            publish_path = fixture["requests"] / "publish.json"
            populated_receipt_path = (
                fixture["receipts"] / "populated-draft-receipt.json"
            )
            receipt_path = fixture["receipts"] / "receipt.json"
            with self._verification_patches():
                self.assertEqual(
                    github_release.main(
                        self._verify_policy_cli_arguments(
                            fixture, policy_receipt_path
                        )
                    ),
                    0,
                )
                self.assertEqual(
                    github_release.main(
                        [
                            "prepare-draft",
                            "--assets",
                            str(fixture["assets"]),
                            "--ffprobe",
                            str(fixture["ffprobe"]),
                            "--output",
                            str(request_path),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    github_release.main(
                        self._verify_empty_draft_cli_arguments(
                            fixture, empty_receipt_path
                        )
                    ),
                    0,
                )
                self.assertEqual(
                    github_release.main(
                        self._verify_draft_cli_arguments(
                            fixture, publish_path, populated_receipt_path
                        )
                    ),
                    0,
                )
                self.assertEqual(
                    github_release.main(
                        self._verify_cli_arguments(fixture, receipt_path)
                    ),
                    0,
                )
            self.assertEqual(request_path.read_bytes(), _canonical(fixture["request"]))
            policy_receipt = json.loads(
                policy_receipt_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                policy_receipt_path.read_bytes(), _canonical(policy_receipt)
            )
            empty_receipt = json.loads(
                empty_receipt_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                empty_receipt_path.read_bytes(), _canonical(empty_receipt)
            )
            self.assertEqual(
                empty_receipt["status"], "EMPTY_DRAFT_UPLOAD_BOUNDARY_PASS"
            )
            self.assertEqual(
                publish_path.read_bytes(), _canonical(fixture["publish_request"])
            )
            populated_receipt = json.loads(
                populated_receipt_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                populated_receipt_path.read_bytes(), _canonical(populated_receipt)
            )
            self.assertEqual(
                populated_receipt["status"],
                "POPULATED_DRAFT_PUBLISH_BOUNDARY_PASS",
            )
            self.assertEqual(
                policy_receipt["api_snapshot"]["kind"],
                "immutable_policy_precreate",
            )
            self.assertIn(
                "immutable_policy_prepublish",
                {
                    item["kind"]
                    for item in populated_receipt["api_snapshots"]
                },
            )
            self.assertNotEqual(policy_receipt_path, populated_receipt_path)
            parsed = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt_path.read_bytes(), _canonical(parsed))
            with self._verification_patches():
                self.assertEqual(
                    github_release.main(
                        self._verify_draft_cli_arguments(
                            fixture, publish_path, populated_receipt_path
                        )
                    ),
                    2,
                )

    def test_populated_draft_pair_output_failure_removes_new_peer(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            publish_path = fixture["requests"] / "publish.json"
            receipt_path = fixture["receipts"] / "already-exists.json"
            existing = b"operator-owned receipt\n"
            receipt_path.write_bytes(existing)
            with self._verification_patches():
                self.assertEqual(
                    github_release.main(
                        self._verify_draft_cli_arguments(
                            fixture, publish_path, receipt_path
                        )
                    ),
                    2,
                )
            self.assertFalse(publish_path.exists())
            self.assertEqual(receipt_path.read_bytes(), existing)

    def test_local_ssh_git_signature_passes_when_api_says_false(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "key"
            subprocess.run(
                (
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            public = key.with_suffix(".pub").read_text(encoding="ascii").strip()
            (root / "allowed_signers").write_text(
                f"fixture@example.invalid {public}\n", encoding="ascii"
            )
            payload = root / "payload"
            payload.write_text("tree " + TREE + "\n\nfixture\n", encoding="utf-8")
            subprocess.run(
                (
                    "/usr/bin/ssh-keygen",
                    "-Y",
                    "sign",
                    "-f",
                    str(key),
                    "-n",
                    "git",
                    str(payload),
                ),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            verification = {
                "payload": payload.read_text(encoding="utf-8"),
                "reason": "unknown_signature_type",
                "signature": Path(str(payload) + ".sig").read_text(encoding="ascii"),
                "verified": False,
            }
            result = github_release._verify_git_payload_signature(
                verification, root, "fixture commit"
            )
            self.assertIs(result["api_verified"], False)
            self.assertEqual(
                result["cryptographic_verification"], "SSH_GIT_NAMESPACE_PASS"
            )
            verification["payload"] += "tamper"
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "SSH verification failed"
            ):
                github_release._verify_git_payload_signature(
                    verification, root, "fixture commit"
                )

    def _successor_fixture(self, fixture):
        fixture["values"]["release"]["immutable"] = True
        fixture["values"]["latest"]["immutable"] = True
        self._replace_json(
            fixture["paths"]["release"], fixture["values"]["release"]
        )
        self._replace_json(
            fixture["paths"]["latest"], fixture["values"]["latest"]
        )
        successor = fixture["successor"]
        media = successor / "docs" / "media"
        media.mkdir(parents=True)
        poster = (fixture["assets"] / f"{TAG}-demo-poster.png").read_bytes()
        poster_path = media / "corelm-result.png"
        poster_path.write_bytes(poster)
        poster_url = (
            f"{portfolio.CANONICAL_REPOSITORY}/releases/download/{TAG}/"
            f"{TAG}-demo-poster.png"
        )
        video_url = (
            f"{portfolio.CANONICAL_REPOSITORY}/releases/download/{TAG}/{TAG}-demo.mp4"
        )
        readme_path = successor / "README.md"
        base_readme = (
            b"# Core LM Benchmark\n\n"
            b"Canonical C0 benchmark documentation.\n"
        )
        readme_path.write_bytes(
            github_release._expected_successor_readme(base_readme, TAG, COMMIT)
        )
        fixture["successor_base_readme"] = base_readme
        signed_payload = (
            f"tree {C1_TREE}\n"
            f"parent {COMMIT}\n"
            "author Ivan <fixture@example.invalid> 0 +0000\n"
            "committer Ivan <fixture@example.invalid> 0 +0000\n\n"
            "Add stable release media links\n"
        )
        c1_verification = {
            "payload": signed_payload,
            "reason": "unknown_signature_type",
            "signature": FAKE_SIGNATURE,
            "verified": False,
        }
        successor_commit = {
            "commit": {
                "tree": {"sha": C1_TREE},
                "verification": c1_verification,
            },
            "parents": [{"sha": COMMIT}],
            "sha": C1_COMMIT,
        }
        compare_commit = {"commit": {"tree": {"sha": C1_TREE}}, "sha": C1_COMMIT}
        compare = {
            "ahead_by": 1,
            "base_commit": {"sha": COMMIT},
            "behind_by": 0,
            "commits": [compare_commit],
            "files": [
                {
                    "filename": "README.md",
                    "sha": github_release._git_blob_sha1(readme_path.read_bytes()),
                    "status": "modified",
                },
                {
                    "filename": "docs/media/corelm-result.png",
                    "sha": github_release._git_blob_sha1(poster),
                    "status": "added",
                },
            ],
            "merge_base_commit": {"sha": COMMIT},
            "status": "ahead",
            "total_commits": 1,
        }
        for name, value in (("compare", compare), ("successor_commit", successor_commit)):
            path = fixture["api_dir"] / f"{name}.json"
            self._replace_json(path, value)
            fixture["paths"][name] = path
            fixture["values"][name] = value

    def _verify_successor(self, fixture):
        paths = fixture["paths"]
        def checkout(
            _root, *, allowed_signers, c0_commit, c1_commit, c1_tree
        ):
            self.assertEqual(allowed_signers.name, "allowed_signers")
            if (
                c0_commit != COMMIT
                or c1_commit != C1_COMMIT
                or c1_tree != C1_TREE
            ):
                raise portfolio.PortfolioReleaseError(
                    "presentation successor checkout object mismatch"
                )
            return fixture["successor_base_readme"]

        with (
            self._verification_patches(),
            patch.object(
                github_release,
                "_verify_successor_checkout",
                side_effect=checkout,
            ),
        ):
            return github_release.verify_presentation_successor(
                assets=fixture["assets"],
                ffprobe=fixture["ffprobe"],
                release_json=paths["release"],
                latest_json=paths["latest"],
                tag_ref_json=paths["tag_ref"],
                tag_object_json=paths["tag_object"],
                commit_object_json=paths["commit_object"],
                compare_json=paths["compare"],
                successor_commit_json=paths["successor_commit"],
                successor_root=fixture["successor"],
            )

    def test_presentation_successor_contract_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(temporary)
            self._successor_fixture(fixture)
            receipt = self._verify_successor(fixture)
            self.assertEqual(receipt["status"], "PRESENTATION_SUCCESSOR_PASS")
            self.assertEqual(receipt["c0"]["commit"], COMMIT)
            self.assertIs(receipt["c0"]["github_immutable"], True)
            self.assertEqual(receipt["c1"]["parent"], COMMIT)
            self.assertEqual(receipt["c1"]["commit"], C1_COMMIT)
            self.assertEqual(
                receipt["c1"]["allowed_paths"],
                ["README.md", "docs/media/corelm-result.png"],
            )
            self.assertEqual(
                receipt["c1"]["readme_policy"],
                "EXACT_PRESENTATION_ONLY_TRANSFORMATION_OF_C0",
            )

    def test_presentation_successor_rejects_extra_path_wrong_poster_and_moving_tag(self):
        cases = ("extra", "poster", "tag", "mutable", "url")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                self._successor_fixture(fixture)
                if case == "extra":
                    fixture["values"]["compare"]["files"].append(
                        {"filename": "docs/extra.md", "sha": "0" * 40, "status": "added"}
                    )
                    self._replace_json(
                        fixture["paths"]["compare"], fixture["values"]["compare"]
                    )
                elif case == "poster":
                    (fixture["successor"] / "docs/media/corelm-result.png").write_bytes(
                        b"wrong"
                    )
                elif case == "tag":
                    fixture["values"]["tag_ref"]["object"]["sha"] = "0" * 40
                    self._replace_json(
                        fixture["paths"]["tag_ref"], fixture["values"]["tag_ref"]
                    )
                elif case == "mutable":
                    fixture["values"]["release"]["immutable"] = False
                    fixture["values"]["latest"]["immutable"] = False
                    self._replace_json(
                        fixture["paths"]["release"], fixture["values"]["release"]
                    )
                    self._replace_json(
                        fixture["paths"]["latest"], fixture["values"]["latest"]
                    )
                else:
                    readme = fixture["successor"] / "README.md"
                    readme.write_text(
                        readme.read_text(encoding="utf-8").replace(
                            f"/releases/download/{TAG}/",
                            "/releases/latest/download/",
                        ),
                        encoding="utf-8",
                    )
                with self.assertRaises(portfolio.PortfolioReleaseError):
                    self._verify_successor(fixture)

    def test_presentation_successor_rejects_unbound_tree_and_readme_overclaim(self):
        cases = ("tree", "overclaim")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(temporary)
                self._successor_fixture(fixture)
                if case == "tree":
                    wrong_tree = "9" * 40
                    fixture["values"]["successor_commit"]["commit"]["tree"][
                        "sha"
                    ] = wrong_tree
                    fixture["values"]["compare"]["commits"][0]["commit"]["tree"][
                        "sha"
                    ] = wrong_tree
                    payload = fixture["values"]["successor_commit"]["commit"][
                        "verification"
                    ]["payload"]
                    fixture["values"]["successor_commit"]["commit"][
                        "verification"
                    ]["payload"] = payload.replace(C1_TREE, wrong_tree, 1)
                    self._replace_json(
                        fixture["paths"]["successor_commit"],
                        fixture["values"]["successor_commit"],
                    )
                    self._replace_json(
                        fixture["paths"]["compare"], fixture["values"]["compare"]
                    )
                else:
                    readme = fixture["successor"] / "README.md"
                    readme.write_text(
                        "# Core LM Benchmark\n\n"
                        "SCIENTIFIC BLIND GENERALIZATION PROVEN. "
                        "This successor redefines the released evidence.\n",
                        encoding="utf-8",
                    )
                    fixture["values"]["compare"]["files"][0]["sha"] = (
                        github_release._git_blob_sha1(readme.read_bytes())
                    )
                    self._replace_json(
                        fixture["paths"]["compare"], fixture["values"]["compare"]
                    )
                with self.assertRaises(portfolio.PortfolioReleaseError):
                    self._verify_successor(fixture)

    def test_successor_checkout_binds_clean_head_tree_parent_and_exact_diff(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "successor-repository"
            repository.mkdir()

            def git(*arguments):
                completed = subprocess.run(
                    ("/usr/bin/git", "-C", str(repository), *arguments),
                    env={
                        "HOME": str(Path(temporary) / "home"),
                        "LANG": "C",
                        "LC_ALL": "C",
                        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    },
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                return completed.stdout.decode("utf-8").strip()

            git("init", "-b", "main")
            git("config", "user.name", "Fixture Author")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "commit.gpgsign", "false")
            git("remote", "add", "origin", portfolio.CANONICAL_REPOSITORY)
            key = Path(temporary) / "successor-signing-key"
            subprocess.run(
                (
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            allowed_signers = Path(temporary) / "allowed_signers"
            public_key = key.with_suffix(".pub").read_text(encoding="ascii").strip()
            allowed_signers.write_text(
                f"fixture@example.invalid {public_key}\n", encoding="ascii"
            )
            base_readme = (
                b"# Core LM Benchmark\n\n"
                b"Canonical C0 benchmark documentation.\n"
            )
            readme = repository / "README.md"
            readme.write_bytes(base_readme)
            (repository / "LICENSE").write_text("fixture\n", encoding="utf-8")
            git("add", "README.md", "LICENSE")
            git("commit", "-m", "Create C0")
            c0_commit = git("rev-parse", "HEAD")

            media = repository / "docs" / "media"
            media.mkdir(parents=True)
            readme.write_bytes(
                github_release._expected_successor_readme(
                    base_readme, TAG, c0_commit
                )
            )
            (media / "corelm-result.png").write_bytes(b"fixture poster bytes\n")
            git("add", "README.md", "docs/media/corelm-result.png")
            git(
                "-c",
                "gpg.format=ssh",
                "-c",
                f"user.signingkey={key}",
                "commit",
                "-S",
                "-m",
                "Add presentation successor",
            )
            c1_commit = git("rev-parse", "HEAD")
            c1_tree = git("rev-parse", "HEAD^{tree}")

            self.assertEqual(
                github_release._verify_successor_checkout(
                    repository,
                    allowed_signers=allowed_signers,
                    c0_commit=c0_commit,
                    c1_commit=c1_commit,
                    c1_tree=c1_tree,
                ),
                base_readme,
            )
            readme.write_text(
                "# Core LM Benchmark\n\nSCIENTIFIC GENERALIZATION PROVEN\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "not clean|differ"
            ):
                github_release._verify_successor_checkout(
                    repository,
                    allowed_signers=allowed_signers,
                    c0_commit=c0_commit,
                    c1_commit=c1_commit,
                    c1_tree=c1_tree,
                )
            readme.write_bytes(
                github_release._expected_successor_readme(
                    base_readme, TAG, c0_commit
                )
            )
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "tree differs"
            ):
                github_release._verify_successor_checkout(
                    repository,
                    allowed_signers=allowed_signers,
                    c0_commit=c0_commit,
                    c1_commit=c1_commit,
                    c1_tree="9" * 40,
                )

            readme.write_text(
                "# Core LM Benchmark\n\nMALICIOUS SCIENTIFIC OVERCLAIM\n",
                encoding="utf-8",
            )
            (repository / "MALWARE").write_text("payload\n", encoding="utf-8")
            git("add", "README.md", "MALWARE")
            git("commit", "-m", "Create malicious replacement candidate")
            malicious_commit = git("rev-parse", "HEAD")
            git("replace", malicious_commit, c1_commit)
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "replacement refs"
            ):
                github_release._verify_successor_checkout(
                    repository,
                    allowed_signers=allowed_signers,
                    c0_commit=c0_commit,
                    c1_commit=malicious_commit,
                    c1_tree=c1_tree,
                )
            git("replace", "-d", malicious_commit)
            grafts = repository / ".git" / "info" / "grafts"
            grafts.write_text(
                f"{malicious_commit} {c0_commit}\n", encoding="ascii"
            )
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "legacy grafts"
            ):
                github_release._verify_successor_checkout(
                    repository,
                    allowed_signers=allowed_signers,
                    c0_commit=c0_commit,
                    c1_commit=malicious_commit,
                    c1_tree=c1_tree,
                )

            grafts.unlink()
            git("checkout", "-b", "rogue-successor", c0_commit)
            readme.write_bytes(
                github_release._expected_successor_readme(
                    base_readme, TAG, c0_commit
                )
            )
            media.mkdir(parents=True, exist_ok=True)
            (media / "corelm-result.png").write_bytes(b"fixture poster bytes\n")
            rogue_key = Path(temporary) / "rogue-signing-key"
            subprocess.run(
                (
                    "/usr/bin/ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(rogue_key),
                ),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            git("add", "README.md", "docs/media/corelm-result.png")
            git(
                "-c",
                "gpg.format=ssh",
                "-c",
                f"user.signingkey={rogue_key}",
                "commit",
                "-S",
                "-m",
                "Create rogue-signed successor",
            )
            rogue_commit = git("rev-parse", "HEAD")
            rogue_tree = git("rev-parse", "HEAD^{tree}")
            fake_verifier = Path(temporary) / "fake-ssh-verifier"
            fake_verifier.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *find-principals*) printf '%s\\n' fixture@example.invalid ;;\n"
                "  *) printf '%s\\n' 'Good git signature for fixture@example.invalid' ;;\n"
                "esac\n"
                "exit 0\n",
                encoding="ascii",
            )
            fake_verifier.chmod(0o700)
            git("config", "gpg.ssh.program", str(fake_verifier))
            with self.assertRaisesRegex(
                portfolio.PortfolioReleaseError, "Git query was rejected"
            ):
                github_release._verify_successor_checkout(
                    repository,
                    allowed_signers=allowed_signers,
                    c0_commit=c0_commit,
                    c1_commit=rogue_commit,
                    c1_tree=rogue_tree,
                )


if __name__ == "__main__":
    unittest.main()
