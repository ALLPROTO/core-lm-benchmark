from pathlib import Path
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "publication" / "run_portfolio_python.sh"


class PortfolioPythonLauncherTests(unittest.TestCase):
    def test_launcher_uses_an_empty_external_cache_and_allowlisted_tools(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('-X "pycache_prefix=$portfolio_pycache"', source)
        self.assertIn('TMPDIR="$portfolio_tmp_root"', source)
        self.assertIn("strict_portfolio_source_bootstrap", source)
        self.assertIn("-c core.trustctime=true", source)
        self.assertIn(
            "forbids ignored paths outside the verified app bundle", source
        )
        self.assertIn("--others --ignored --exclude-standard", source)
        self.assertIn("/usr/bin/mktemp -d", source)
        self.assertIn('/bin/chmod 700 "$portfolio_pycache"', source)
        self.assertIn('/bin/rmdir "$portfolio_pycache"', source)
        self.assertNotIn("eval ", source)
        self.assertNotIn("exec ", source)

        completed = subprocess.run(
            (
                str(LAUNCHER),
                str(Path(sys.executable).resolve(strict=True)),
                "build_portfolio_release.py",
                "--help",
            ),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertIn(b"usage:", completed.stdout.lower())

    def test_launcher_rejects_ignored_namespace_injection_before_python(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            repository = fixture / "source"
            publication = repository / "publication"
            publication.mkdir(parents=True)
            shutil.copy2(LAUNCHER, publication / LAUNCHER.name)
            (publication / LAUNCHER.name).chmod(0o755)
            (publication / "build_portfolio_release.py").write_text(
                "raise SystemExit('fixture tool must not run directly')\n",
                encoding="utf-8",
            )
            for relative in ("security/.keep", "RealLLM/.keep"):
                target = repository / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture\n", encoding="utf-8")
            (repository / ".gitignore").write_text(
                "dist/\n**/__pycache__/\n*.py[cod]\n",
                encoding="utf-8",
            )

            invocation_log = fixture / "python-invocations.log"
            python = fixture / "python"
            python.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' invoked >> {invocation_log!s}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            python.chmod(0o700)
            temporary_root = fixture / "tmp"
            temporary_root.mkdir(mode=0o700)

            git = "/usr/bin/git"
            subprocess.run((git, "init", "-q", str(repository)), check=True)
            subprocess.run(
                (git, "-C", str(repository), "config", "user.name", "Fixture"),
                check=True,
            )
            subprocess.run(
                (
                    git,
                    "-C",
                    str(repository),
                    "config",
                    "user.email",
                    "fixture@example.invalid",
                ),
                check=True,
            )
            subprocess.run((git, "-C", str(repository), "add", "."), check=True)
            subprocess.run(
                (git, "-C", str(repository), "commit", "-qm", "fixture"),
                check=True,
            )

            (repository / "dist/CoreLMBenchmark.app").mkdir(parents=True)
            environment = {
                "HOME": str(fixture / "home"),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "TMPDIR": str(temporary_root),
            }
            command = (
                str(publication / LAUNCHER.name),
                str(python),
                "build_portfolio_release.py",
                "--verify",
                str(fixture / "assets"),
            )
            accepted = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr.decode())
            self.assertEqual(invocation_log.read_text(encoding="utf-8"), "invoked\n")

            root_shadow = repository / "security.pyc"
            root_shadow.write_bytes(b"ignored-namespace-shadow")
            root_rejected = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(root_rejected.returncode, 0)
            self.assertIn(
                b"forbids ignored paths outside the verified app bundle",
                root_rejected.stderr,
            )

            root_shadow.unlink()
            with (repository / ".git/info/exclude").open(
                "a", encoding="utf-8"
            ) as exclude:
                exclude.write("\nsecurity/__init__.py\n")
            (repository / "security/__init__.py").write_text(
                "raise SystemExit('injected')\n", encoding="utf-8"
            )
            exclude_rejected = subprocess.run(
                command,
                cwd=repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(exclude_rejected.returncode, 0)
            self.assertIn(
                b"forbids ignored paths outside the verified app bundle",
                exclude_rejected.stderr,
            )
            self.assertEqual(invocation_log.read_text(encoding="utf-8"), "invoked\n")

    def test_launcher_rejects_relative_python_and_unknown_tool(self) -> None:
        for arguments in (
            ("python3", "build_portfolio_release.py"),
            (str(Path(sys.executable).resolve(strict=True)), "other.py"),
        ):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    (str(LAUNCHER), *arguments),
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 2)

    def test_launcher_rejects_relative_or_checkout_local_tmpdir(self) -> None:
        python = str(Path(sys.executable).resolve(strict=True))
        for temporary in ("relative-cache", str(ROOT)):
            with self.subTest(temporary=temporary):
                environment = os.environ.copy()
                environment["TMPDIR"] = temporary
                completed = subprocess.run(
                    (
                        str(LAUNCHER),
                        python,
                        "build_portfolio_release.py",
                        "--help",
                    ),
                    cwd=ROOT,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 2)

    def test_normative_runbooks_use_the_isolated_launcher(self) -> None:
        for relative in ("docs/DEMO.md", "publication/PORTFOLIO_RELEASE.md"):
            with self.subTest(document=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("publication/run_portfolio_python.sh", source)
                self.assertNotIn("-I -B publication/collect_portfolio_demo.py", source)
                self.assertNotIn("-I -B publication/build_portfolio_release.py", source)
                self.assertNotIn(
                    "-I -B \\\n  publication/verify_portfolio_github_release.py",
                    source,
                )

    def test_shell_entrypoints_pin_root_discovery_tools(self) -> None:
        for relative in (
            "corelm",
            "publication/run_portfolio_python.sh",
            "scripts/verify-python.sh",
        ):
            with self.subTest(entrypoint=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("$(/usr/bin/dirname --", source)
                self.assertNotIn("$(dirname ", source)

    def test_default_gate_requires_absolute_python_and_external_tmpdir(self) -> None:
        gate = ROOT / "scripts/verify-python.sh"
        source = gate.read_text(encoding="utf-8")
        self.assertNotIn("command -v", source)
        self.assertIn("PYTHON_BIN must be an absolute path", source)
        self.assertIn("test caches must be outside the source checkout", source)

        environment = os.environ.copy()
        environment["PYTHON_BIN"] = "python3"
        relative_python = subprocess.run(
            ("/bin/sh", str(gate), "Tests.test_portfolio_python_launcher"),
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertNotEqual(relative_python.returncode, 0)
        self.assertIn(b"PYTHON_BIN must be an absolute path", relative_python.stderr)

        environment["PYTHON_BIN"] = str(Path(sys.executable).resolve(strict=True))
        environment["TMPDIR"] = str(ROOT)
        local_tmpdir = subprocess.run(
            ("/bin/sh", str(gate), "Tests.test_portfolio_python_launcher"),
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        self.assertNotEqual(local_tmpdir.returncode, 0)
        self.assertIn(b"test caches must be outside", local_tmpdir.stderr)

    def test_product_clis_reject_direct_python_without_external_cache(self) -> None:
        product_tools = (
            "publication/build_portfolio_release.py",
            "publication/collect_portfolio_demo.py",
            "publication/verify_portfolio_github_release.py",
            "platforms/macos/scripts/run-automated-portfolio-demo.py",
        )
        guard_shapes = []
        for relative in product_tools:
            with self.subTest(tool=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                tree = ast.parse(source)
                guard = next(
                    node
                    for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "_require_isolated_product_python"
                )
                guard_shapes.append(ast.dump(guard, include_attributes=False))
                guard_call = source.index("    _require_isolated_product_python()")
                local_imports = [
                    source.index(marker)
                    for marker in (
                        "from security",
                        "from publication",
                        "from RealLLM",
                    )
                    if marker in source
                ]
                self.assertTrue(local_imports)
                self.assertLess(guard_call, min(local_imports))
                completed = subprocess.run(
                    (
                        str(Path(sys.executable).resolve(strict=True)),
                        "-I",
                        "-B",
                        str(ROOT / relative),
                        "--help",
                    ),
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(b"tracked isolated Python launcher", completed.stderr)
        self.assertEqual(len(set(guard_shapes)), 1)


if __name__ == "__main__":
    unittest.main()
