from pathlib import Path
import hashlib
import stat
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "platforms" / "macos" / "Operator"
SOURCES = OPERATOR / "Sources"
COMMAND_LAUNCHER = (
    OPERATOR / "CommandLauncher" / "CoreLMOperatorCommandLauncher.swift"
)
LAUNCHER = ROOT / "platforms" / "macos" / "scripts" / "run-operator.sh"


class MacOSOperatorTests(unittest.TestCase):
    def test_operator_is_a_separate_nested_package(self):
        operator_package = (OPERATOR / "Package.swift").read_text(
            encoding="utf-8"
        )
        production_package = (ROOT / "Package.swift").read_text(
            encoding="utf-8"
        )
        package_app = (
            ROOT / "platforms/macos/scripts/package-app.sh"
        ).read_text(encoding="utf-8")
        bundle_verifier = (
            ROOT / "security/verify_app_bundle.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('name: "CoreLMOperator"', operator_package)
        self.assertIn(
            'name: "CoreLMOperatorCommandLauncher"', operator_package
        )
        self.assertIn('path: "CommandLauncher"', operator_package)
        self.assertIn('.testTarget(', operator_package)
        self.assertNotIn("CoreLMOperator", production_package)
        self.assertNotIn("CoreLMOperator", package_app)
        self.assertNotIn("CoreLMOperator", bundle_verifier)
        self.assertIn(
            "release bundle must contain exactly seven declared resources",
            bundle_verifier,
        )

    def test_corelm_has_one_exact_operator_route_and_no_arguments(self):
        dispatcher = (ROOT / "corelm").read_text(encoding="utf-8")
        self.assertEqual(dispatcher.count("./corelm macos operator"), 1)
        self.assertEqual(
            dispatcher.count(
                "macos:operator) script=platforms/macos/scripts/run-operator.sh ;;"
            ),
            1,
        )
        completed = subprocess.run(
            (str(ROOT / "corelm"), "macos", "operator", "unexpected"),
            cwd=ROOT,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(
            completed.stderr,
            "./corelm macos operator accepts no arguments\n",
        )

    def test_launcher_builds_outside_checkout_and_freezes_group_before_cleanup(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertTrue(stat.S_IMODE(LAUNCHER.stat().st_mode) & stat.S_IXUSR)
        self.assertIn('[ "$#" -eq 0 ]', source)
        self.assertIn(
            'OPERATOR_CACHE_ROOT="$OPERATOR_CACHE_PARENT/CoreLMOperator"',
            source,
        )
        self.assertIn(
            "operator build scratch must be outside the source checkout",
            source,
        )
        self.assertIn(
            '/usr/bin/mktemp -d "$OPERATOR_CACHE_ROOT/session.XXXXXX"',
            source,
        )
        self.assertIn('CONTROL_DIRECTORY="$SCRATCH_DIRECTORY/control"', source)
        self.assertIn('/bin/mkdir -m 700 "$CONTROL_DIRECTORY"', source)
        self.assertIn('/bin/chmod 500 "$CONTROL_DIRECTORY"', source)
        self.assertIn('/bin/kill -TERM -- "-$group_id"', source)
        self.assertIn('/bin/kill -KILL -- "-$group_id"', source)
        self.assertIn('--command-launcher "$COMMAND_LAUNCHER"', source)
        self.assertIn('--group-file "$GROUP_FILE"', source)
        self.assertIn("--jobs 1", source)
        self.assertLess(
            source.index('/bin/chmod 500 "$CONTROL_DIRECTORY"'),
            source.index('/bin/kill -TERM -- "-$group_id"'),
        )
        self.assertLess(
            source.index('/bin/kill -KILL -- "-$group_id"'),
            source.index('/bin/rm -rf -- "$SCRATCH_DIRECTORY"'),
        )
        self.assertIn("/usr/bin/env -i \\", source)
        for forbidden in (
            "eval ",
            "/bin/sh -c",
            "CORELM_ALLOW_DIRTY_SOURCE",
            "CORELM_SKIP_",
            "portfolio-demo",
        ):
            self.assertNotIn(forbidden, source)

        syntax = subprocess.run(
            ("/bin/sh", "-n", str(LAUNCHER)),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_compiled_command_launcher_has_exact_fail_closed_grammar(self):
        source = COMMAND_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("payload.count == 12", source)
        for flag in (
            "--group-file",
            "--dispatcher",
            "--dispatcher-sha256",
            "--verifier",
            "--verifier-sha256",
            "--action",
        ):
            self.assertEqual(source.count(f'== "{flag}"'), 1)
        for token in ("verify", "models", "build", "proof", "app-check"):
            self.assertIn(token, source)
        self.assertIn("Set(environment.keys) == exactEnvironment", source)
        self.assertIn('"__CF_USER_TEXT_ENCODING"', source)
        self.assertIn("if getpgrp() == processID", source)
        self.assertIn("groupID = setsid()", source)
        self.assertIn("getpgid(0) == groupID", source)
        self.assertIn("O_EXCL | O_NOFOLLOW | O_CLOEXEC", source)
        self.assertIn("fsync(descriptor)", source)
        self.assertIn("renamex_np", source)
        self.assertIn("UInt32(RENAME_EXCL)", source)
        self.assertIn("requiresPostCommandAppVerification", source)
        self.assertIn("configuration.verifier", source)
        self.assertEqual(
            source.count("try configuration.revalidateCommands()"), 2
        )
        self.assertIn("exit(commandStatus)", source)
        self.assertIn("posix_spawn(", source)
        self.assertIn("waitpid(child, &childStatus, 0)", source)
        self.assertNotIn("let child = Process()", source)
        self.assertNotIn("fork()", source)
        self.assertNotIn("/bin/sh", source)
        self.assertNotIn('arguments = ["-c"', source)
        self.assertNotIn("ProcessInfo.processInfo.arguments", source)

    def test_ui_has_exact_classification_and_only_fixed_controls(self):
        view = (SOURCES / "OperatorContentView.swift").read_text(
            encoding="utf-8"
        )
        store = (SOURCES / "OperatorStore.swift").read_text(encoding="utf-8")
        models = (SOURCES / "OperatorModels.swift").read_text(
            encoding="utf-8"
        )
        all_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(SOURCES.glob("*.swift"))
        )

        self.assertIn(
            '"MANUAL OPERATOR · NOT PORTFOLIO EVIDENCE · "', store
        )
        self.assertIn('"NOT INDEPENDENT REPLICATION"', store)
        for title, action in (
            ("Verify Repository", ".verifyRepository"),
            ("Model Inventory", ".modelCompatibility"),
            ("Build App", ".buildApp"),
            ("Full System Proof", ".fullSystemProof"),
            ("Open Built App", ".openBuiltApplication"),
        ):
            self.assertIn(f'Button("{title}")', view)
            self.assertIn(action, view)
        self.assertEqual(models.count('["verify"]'), 1)
        self.assertEqual(models.count('["models", "list"]'), 1)
        self.assertIn(
            hashlib.sha256(
                (ROOT / "RealLLM/pinned_model_registry.json").read_bytes()
            ).hexdigest(),
            models,
        )
        self.assertEqual(models.count('["macos", "build"]'), 1)
        self.assertEqual(models.count('["macos", "proof"]'), 1)
        self.assertIn("guard !isRunning else", store)
        self.assertIn(".disabled(store.isRunning)", view)
        self.assertIn(
            "store.isRunning || !store.builtApplicationAvailable", view
        )
        self.assertIn('appendingPathComponent("dist"', models)
        self.assertIn('"CoreLMBenchmark.app", isDirectory: true', models)
        self.assertIn("Normal Quit safely terminates", view)
        for forbidden in (
            'Button("Cancel',
            'Button("Stop',
            'Button("Portfolio',
            '"portfolio-demo"',
            "TextField(",
            "fileImporter(",
            "NSOpenPanel",
            "authenticated worker event",
        ):
            self.assertNotIn(forbidden, all_sources)

    def test_runner_has_single_eof_drain_owners_and_typed_terminal_state(self):
        runner = (SOURCES / "OperatorCommandRunner.swift").read_text(
            encoding="utf-8"
        )
        models = (SOURCES / "OperatorModels.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn("process.executableURL = authority.launcher", runner)
        self.assertIn('"--action", action.launcherToken', runner)
        self.assertIn("process.environment = environment", runner)
        self.assertIn("process.currentDirectoryURL = project.root", runner)
        self.assertIn("process.standardInput = FileHandle.nullDevice", runner)
        self.assertIn('"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"', runner)
        self.assertIn("while let data = try handle.read(upToCount:", runner)
        self.assertIn("drains.wait()", runner)
        self.assertIn("processExited.wait()", runner)
        self.assertIn("deliveryQueue.sync", runner)
        self.assertIn("finalSequence", runner)
        self.assertIn("snapshot.sequence > lastOutputSequence", (
            SOURCES / "OperatorStore.swift"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("readabilityHandler", runner)
        self.assertNotIn("readDataToEndOfFile", runner)
        self.assertNotIn("String(decoding: data", runner)
        self.assertIn("OperatorProofTerminalObserver", runner)
        self.assertIn("line == Self.passLine", runner)
        self.assertIn("line == Self.metricFailLine", runner)
        self.assertNotIn("output.contains", models)
        self.assertIn("try project.revalidateControlSurface()", runner)
        self.assertIn("try authority.prepareForSpawn()", runner)
        for transitive in (
            "RealLLM/model_compatibility.py",
            "RealLLM/pinned_model_registry.json",
            "schemas/model-compatibility-inspection.schema.json",
            "security/generate_build_provenance.py",
            "security/generate_app_proof_core.py",
            "security/verify_git_checkout.py",
        ):
            self.assertIn(f'"{transitive}"', models)
        self.assertNotIn("/bin/sh", runner)
        self.assertNotIn('arguments = ["-c"', runner)

    def test_quit_uses_safe_group_termination_and_open_reverification(self):
        application = (SOURCES / "CoreLMOperatorApp.swift").read_text(
            encoding="utf-8"
        )
        store = (SOURCES / "OperatorStore.swift").read_text(encoding="utf-8")
        runner = (SOURCES / "OperatorCommandRunner.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn("applicationShouldTerminate", application)
        self.assertIn("store?.isRunning == true", application)
        self.assertIn("return .terminateLater", application)
        self.assertIn("beginApplicationTermination", store)
        self.assertIn("commandHandle?.cancel()", store)
        self.assertIn("reply(toApplicationShouldTerminate: true)", store)
        self.assertIn("kill(-groupID, SIGTERM)", runner)
        self.assertIn("kill(-groupID, SIGKILL)", runner)
        self.assertIn("final class OperatorProcessGroupController", runner)
        self.assertIn("groupController.requestTermination()", runner)
        self.assertIn("let cleanupQueue = DispatchQueue", runner)
        self.assertIn("try project.validatedBuiltApplication()", store)
        self.assertIn("NSWorkspace.shared.open(application)", store)
        self.assertIn('"app-check"', (
            SOURCES / "OperatorModels.swift"
        ).read_text(encoding="utf-8"))

    def test_no_operator_source_contains_private_path_or_publication_action(self):
        paths = [
            *sorted(OPERATOR.rglob("*.swift")),
            OPERATOR / "Package.swift",
            LAUNCHER,
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("/" + "Users" + "/private", combined)
        self.assertNotIn("portfolio-demo", combined)
        self.assertNotIn("--output", combined)


if __name__ == "__main__":
    unittest.main()
