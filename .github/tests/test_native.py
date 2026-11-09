"""Exercise the release workflow without invoking native build or Apple tools."""

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text()
SPEC = importlib.util.spec_from_file_location(
    "native_source_version", ROOT / ".github/scripts/source_version.py"
)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def step(name):
    """Extract one literal run block, failing rather than silently testing a copy."""
    matches = re.findall(
        rf"^      - name: {re.escape(name)}\n"
        r"(?:(?!      - ).*\n)*?        run: \|\n"
        r"((?:          .*(?:\n|$)|[ \t]*\n)+)",
        WORKFLOW,
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise AssertionError(f"Expected one shell block for {name!r}")
    return textwrap.dedent(matches[0])


STUB = r'''
import json
import os
from pathlib import Path
import plistlib
import re
import sys

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
root = Path.cwd()
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\n")
bundle = root / os.environ["TEST_BUNDLE"]
contents = bundle / "Contents"
mode = os.environ.get("BUILD_MODE", "complete")

if tool == "xcodebuild":
    # Check freshness at the build boundary, not just after the shell returns.
    for path in (
        contents / "MacOS/codec", contents / "Info.plist",
        contents / "Resources/English.lproj/InfoPlist.strings",
        contents / "_CodeSignature", bundle.parent / "Default",
        bundle.parent / "codec.build",
    ):
        assert not path.exists(), "stale output survived: " + str(path)
    if mode != "missing-binary":
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "MacOS/codec").write_bytes(b"rebuilt-universal")
    if mode != "missing-plist":
        project = (root / "codec.xcodeproj/project.pbxproj").read_text()
        copied = re.findall(r'INFOPLIST_FILE = "([^"]+)";', project)
        assert copied == ["codec copy-Info.plist"] * 3, copied
        data = plistlib.loads((root / copied[0]).read_bytes())
        settings = dict(re.findall(
            r"(?m)^\s*(MARKETING_VERSION|CURRENT_PROJECT_VERSION) = ([^;]+);", project
        ))
        def resolve(match):
            key = match[1] or match[2]
            value = settings[key].strip('"')
            return re.sub(r"\$\(([^)]+)\)|\$\{([^}]+)\}", resolve, value)
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            if key in data:
                data[key] = re.sub(
                    r"\$\(([^)]+)\)|\$\{([^}]+)\}", resolve, data[key]
                )
        if mode == "stale-plist":
            data["CFBundleShortVersionString"] = os.environ["STALE_VERSION"]
        if mode == "stale-build-version":
            data["CFBundleVersion"] = os.environ["STALE_VERSION"]
        (contents / "Info.plist").write_bytes(plistlib.dumps(data))
    if mode != "missing-localized":
        target = contents / "Resources/English.lproj/InfoPlist.strings"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (root / "English.lproj/InfoPlist.strings").read_bytes()
        if mode == "stale-localized":
            data = data.replace(
                os.environ["SOURCE_VERSION"].encode(), os.environ["STALE_VERSION"].encode()
            )
        target.write_bytes(data)
elif tool == "lipo":
    binary = os.environ["TEST_BUNDLE"] + "/Contents/MacOS/codec"
    architectures = os.environ.get("ARCHS", "arm64 x86_64")
    if args == ["-info", binary]:
        print("Architectures in the fat file: " + architectures)
    else:
        assert args in (["-verify_arch", "arm64", binary],
                        ["-verify_arch", "x86_64", binary]), args
        if args[1] not in architectures.split():
            sys.exit(1)
elif tool == "python3":
    assert args == [".github/scripts/source_version.py", "--verify-bundle",
                    os.environ["TEST_BUNDLE"]]
    os.execv(os.environ["REAL_PYTHON"], [os.environ["REAL_PYTHON"], *args])
elif tool in ("ditto", "hdiutil"):
    assert Path(os.environ["BUNDLE_PATH"]).is_dir()
    if tool == "ditto":
        assert args[:-1] == ["-c", "-k", "--keepParent", os.environ["BUNDLE_PATH"]]
    else:
        assert args[:-1] == ["create", "-format", "UDBZ", "-volname", "codec",
                            "-srcfolder", os.environ["BUNDLE_PATH"]]
    Path(args[-1]).write_bytes(b"stub archive")
elif tool == "xcrun":
    scenario = os.environ.get("NOTARY_MODE", "accepted")
    if args[:2] == ["notarytool", "submit"]:
        assert args[3:] == [
            "--keychain-profile", "notarytool-profile", "--keychain",
            os.environ["KEYCHAIN_PATH"], "--wait", "--output-format", "json"
        ]
        assert Path(args[2]).is_file()
        second = args[2].endswith(".dmg")
        if scenario == "transport" or (scenario == "second-transport" and second):
            sys.exit(71)
        if scenario == "malformed":
            print("this is not JSON")
        else:
            status = "Invalid" if (
                scenario == "invalid" or (scenario == "second-invalid" and second)
            ) else "Accepted"
            print(json.dumps({"id": "submission-dmg" if second else "submission-zip",
                              "status": status}))
    elif args[:2] == ["notarytool", "log"]:
        assert args[3:] == ["--keychain-profile", "notarytool-profile",
                            "--keychain", os.environ["KEYCHAIN_PATH"]]
        # A diagnostic failure must not mask the Invalid status.
        sys.exit(72)
    elif args[:2] == ["stapler", "staple"]:
        assert len(args) == 3 and args[2].endswith(".dmg")
        if scenario == "staple":
            sys.exit(73)
    else:
        raise AssertionError(args)
elif tool == "plutil":
    assert args[0] == "-extract" and args[2:] == ["raw", "-o", "-", "-"]
    try:
        value = json.load(sys.stdin)[args[1]]
        assert isinstance(value, str)
        print(value)
    except (ValueError, KeyError, AssertionError):
        sys.exit(74)
else:
    raise AssertionError("Unexpected tool: " + tool)
'''


class NativeShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".native-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (*source.SOURCE_PATHS, Path(".github/scripts/source_version.py")):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        self.version = source.read(self.root)
        self.source_bytes = {
            path: (self.root / path).read_bytes() for path in source.SOURCE_PATHS
        }
        major, minor, patch = map(int, self.version.split("."))
        self.stale = f"{major}.{minor}.{patch + 1}"
        self.relative_bundle = "test/Plugins/codec.bundle"
        self.bundle = self.root / self.relative_bundle
        self.contents = self.bundle / "Contents"
        self.log = self.root / "calls.jsonl"
        self.env_file = self.root / "github-env"
        self.env_file.touch()
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        for name in ("xcodebuild", "lipo", "python3", "ditto", "hdiutil", "xcrun", "plutil"):
            executable = self.bin / name
            executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(STUB))
            executable.chmod(0o755)
        # A closed PATH prevents accidental fallback to any installed native tool.
        for name in ("rm", "ls", "grep", "cp", "mkdir"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.bin / name).symlink_to(executable)
        self.env = {
            "PATH": str(self.bin),
            "CALL_LOG": str(self.log),
            "REAL_PYTHON": sys.executable,
            "PYTHONDONTWRITEBYTECODE": "1",
            "SOURCE_VERSION": self.version,
            "STALE_VERSION": self.stale,
            "TEST_BUNDLE": self.relative_bundle,
            "BUNDLE_PATH": self.relative_bundle,
            "KEYCHAIN_PATH": str(self.root / "fake.keychain-db"),
            "GITHUB_ENV": str(self.env_file),
        }
        self.seed()

    def seed(self):
        self.preserved = {}
        for relative in (
            "QuickLook/Thumbnail.png", "manifest.json", "Resources/constants.xlf",
            "Windows/codec.4DX", "Windows64/codec.4DX", "CodeResources",
        ):
            data = (ROOT / self.relative_bundle / "Contents" / relative).read_bytes()
            self.write(relative, data)
            self.preserved[relative] = data
        for relative in (
            "Frameworks/Dependency.framework/Versions/A/Dependency",
            "Frameworks/Dependency.framework/Versions/A/Resources/dependency.dat",
        ):
            data = b"preserved framework dependency"
            self.write(relative, data)
            self.preserved[relative] = data
        (self.contents / "Frameworks/Dependency.framework/Versions/Current").symlink_to("A")
        for relative in (
            "MacOS/codec", "Info.plist", "Resources/English.lproj/InfoPlist.strings",
            "_CodeSignature/CodeResources",
        ):
            self.write(relative, b"stale build output")
        for relative in ("Default/stale", "codec.build/stale"):
            path = self.bundle.parent / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale intermediate")

    def write(self, relative, data):
        path = self.contents / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_step(self, name, **env):
        script = step(name)
        values = {
            "env.PRODUCT_NAME": "codec", "env.BASE_DIR": "test",
            "env.MACOS_DEPLOYMENT_TARGET": "11.0",
            "needs.version.outputs.version": self.version,
        }
        for key, value in values.items():
            script = script.replace("${{ " + key + " }}", value)
        self.assertNotIn("${{", script)
        return subprocess.run(
            ["/bin/bash", "-c", script], cwd=self.root, env={**self.env, **env},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def calls(self, tool):
        if not self.log.exists():
            return []
        return [call[1:] for line in self.log.read_text().splitlines()
                if (call := json.loads(line))[0] == tool]

    def build(self, **env):
        self.assert_ok(self.run_step("build macOS plugin (universal)", **env))

    def bundle_snapshot(self):
        return {
            path.relative_to(self.bundle): (
                path.readlink() if path.is_symlink() else path.read_bytes()
            )
            for path in self.bundle.rglob("*")
            if path.is_symlink() or path.is_file()
        }

    def test_exact_downloaded_windows_artifact_is_merged_and_exported(self):
        before = self.bundle_snapshot()
        stale = self.root / "winbuild/aaa-stale/codec.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale nested Windows artifact")
        artifact = self.root / "winbuild/codec.4DX"
        artifact.write_bytes(b"exact downloaded Windows artifact\x00\xff")

        self.assert_ok(self.run_step("merge Windows binaries into the bundle"))

        expected = {**before, Path("Contents/Windows64/codec.4DX"): artifact.read_bytes()}
        self.assertEqual(self.bundle_snapshot(), expected)
        self.assertEqual(stale.read_bytes(), b"stale nested Windows artifact")
        self.assertEqual(self.env_file.read_text(),
                         f"BUNDLE_PATH={self.relative_bundle}\n")
        self.assertFalse(self.log.exists(), "Merge unexpectedly invoked a native tool")
        for path, data in self.source_bytes.items():
            self.assertEqual((self.root / path).read_bytes(), data, str(path))

    def test_missing_or_empty_exact_windows_artifact_rejects_stale_nested_candidate(self):
        before = self.bundle_snapshot()
        stale = self.root / "winbuild/aaa-stale/codec.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"stale nested Windows artifact")
        artifact = self.root / "winbuild/codec.4DX"
        for mode in ("missing", "empty"):
            with self.subTest(mode=mode):
                if mode == "empty":
                    artifact.write_bytes(b"")
                result = self.run_step("merge Windows binaries into the bundle")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "Windows binary missing at exact artifact path winbuild/codec.4DX",
                    result.stdout,
                )
                self.assertEqual(self.bundle_snapshot(), before)
                self.assertEqual(stale.read_bytes(), b"stale nested Windows artifact")
                self.assertEqual(self.env_file.read_text(), "")
                self.assertFalse(self.log.exists(),
                                 "Merge unexpectedly invoked a native tool")

    def test_fresh_universal_build_preserves_resources_and_dependencies(self):
        self.build()
        self.assertEqual((self.contents / "MacOS/codec").read_bytes(), b"rebuilt-universal")
        for relative, data in self.preserved.items():
            self.assertEqual((self.contents / relative).read_bytes(), data, relative)
        link = self.contents / "Frameworks/Dependency.framework/Versions/Current"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.readlink(), Path("A"))
        for path in (self.contents / "_CodeSignature", self.bundle.parent / "Default",
                     self.bundle.parent / "codec.build"):
            self.assertFalse(path.exists())
        for path, data in self.source_bytes.items():
            self.assertEqual((self.root / path).read_bytes(), data, str(path))
        source.verify_bundle(self.bundle, self.root)
        built = plistlib.loads((self.contents / "Info.plist").read_bytes())
        self.assertNotIn("CFBundleVersion", built)
        self.assertEqual(built["CFBundleShortVersionString"], self.version)
        self.assert_ok(self.run_step("verify universal binary"))
        self.assertEqual(len(self.calls("python3")), 1)
        binary = self.relative_bundle + "/Contents/MacOS/codec"
        self.assertEqual(self.calls("lipo"), [
            ["-info", binary], ["-verify_arch", "arm64", binary],
            ["-verify_arch", "x86_64", binary],
        ])
        self.assertEqual(self.calls("xcodebuild"), [[
            "-project", "codec.xcodeproj", "-target", "codec",
            "-configuration", "Default", "ARCHS=arm64 x86_64", "ONLY_ACTIVE_ARCH=NO",
            "MACOSX_DEPLOYMENT_TARGET=11.0", "CODE_SIGNING_ALLOWED=NO",
            f"CONFIGURATION_BUILD_DIR={self.root}/test/Plugins", "build",
        ]])

    def test_missing_rebuilt_binary_is_rejected(self):
        self.build(BUILD_MODE="missing-binary")
        self.assertFalse((self.contents / "MacOS/codec").exists())
        result = self.run_step("verify universal binary")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected binary not found", result.stdout)
        self.assertEqual(self.calls("lipo"), [])
        self.assertEqual(self.calls("python3"), [])

    def test_missing_rebuilt_metadata_is_rejected(self):
        for mode, relative in (
            ("missing-plist", "Info.plist"),
            ("missing-localized", "Resources/English.lproj/InfoPlist.strings"),
        ):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                self.assertFalse((self.contents / relative).exists())
                result = self.run_step("verify universal binary")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FileNotFoundError", result.stderr)

    def test_stale_rebuilt_metadata_is_rejected(self):
        for mode in ("stale-plist", "stale-build-version", "stale-localized"):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                result = self.run_step("verify universal binary")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("differs from selected source", result.stderr)

    def test_each_universal_architecture_is_required(self):
        self.build()
        for architectures in ("arm64", "x86_64", "arm64e x86_64", "arm64 x86_64h"):
            with self.subTest(architectures=architectures):
                self.log.unlink(missing_ok=True)
                result = self.run_step("verify universal binary", ARCHS=architectures)
                self.assertNotEqual(result.returncode, 0)
                binary = self.relative_bundle + "/Contents/MacOS/codec"
                expected = [["-info", binary], ["-verify_arch", "arm64", binary]]
                if "arm64" in architectures.split():
                    expected.append(["-verify_arch", "x86_64", binary])
                self.assertEqual(self.calls("lipo"), expected)
                self.assertEqual(self.calls("python3"), [])

    def compiled_localization(self):
        localized = source.text(self.root / source.LOCALIZED)
        values = dict(re.findall(r'(?m)^(\w+)\s*=\s*"([^"]*)";', localized))
        self.assertEqual(values["CFBundleShortVersionString"], self.version)
        self.assertIn(self.version, values["CFBundleGetInfoString"])
        return values

    def test_compiled_binary_and_xml_localization_are_accepted(self):
        self.build()
        values = self.compiled_localization()
        for serialization, signature in (
            (plistlib.FMT_BINARY, b"bplist00"),
            (plistlib.FMT_XML, b"<?xml"),
        ):
            with self.subTest(serialization=serialization):
                data = plistlib.dumps(values, fmt=serialization)
                self.assertTrue(data.startswith(signature))
                self.write("Resources/English.lproj/InfoPlist.strings", data)
                self.assert_ok(self.run_step("verify universal binary"))
        self.assertEqual(len(self.calls("python3")), 2)

    def test_stale_compiled_localization_is_rejected(self):
        self.build()
        values = self.compiled_localization()
        for serialization in (plistlib.FMT_BINARY, plistlib.FMT_XML):
            for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
                with self.subTest(serialization=serialization, key=key):
                    stale = {**values, key: values[key].replace(self.version, self.stale)}
                    self.write("Resources/English.lproj/InfoPlist.strings",
                               plistlib.dumps(stale, fmt=serialization))
                    result = self.run_step("verify universal binary")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Built localized display differs from selected source",
                                  result.stderr)
        self.assertEqual(len(self.calls("python3")), 4)

    def assert_package_calls(self, submissions, staple=False, diagnostic=None):
        zip_path = f"codec-{self.version}.zip"
        dmg_path = f"codec-{self.version}.dmg"
        self.assertEqual(len(self.calls("ditto")), 1)
        self.assertEqual(len(self.calls("hdiutil")), 1)
        calls = self.calls("xcrun")
        submitted = [call[2] for call in calls if call[:2] == ["notarytool", "submit"]]
        self.assertEqual(submitted, [zip_path, dmg_path][:submissions])
        self.assertEqual(
            [call for call in calls if call[:2] == ["stapler", "staple"]],
            [["stapler", "staple", dmg_path]] if staple else [],
        )
        logs = [call[2] for call in calls if call[:2] == ["notarytool", "log"]]
        self.assertEqual(logs, [diagnostic] if diagnostic else [])
        if staple:
            self.assertEqual(calls[-1], ["stapler", "staple", dmg_path])

    def test_both_accepted_submissions_then_staple_publish_paths(self):
        self.assert_ok(self.run_step("package, notarize & staple"))
        self.assert_package_calls(2, staple=True)
        self.assertEqual(self.env_file.read_text().splitlines(), [
            f"ZIP_PATH=codec-{self.version}.zip",
            f"DMG_PATH=codec-{self.version}.dmg",
        ])

    def test_invalid_zero_exit_status_blocks_staple_and_publication(self):
        result = self.run_step("package, notarize & staple", NOTARY_MODE="invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("returned 'Invalid'", result.stdout)
        self.assert_package_calls(1, diagnostic="submission-zip")
        self.assertEqual(self.env_file.read_text(), "")

    def test_transport_failure_blocks_staple_and_publication(self):
        result = self.run_step("package, notarize & staple", NOTARY_MODE="transport")
        self.assertNotEqual(result.returncode, 0)
        self.assert_package_calls(1)
        self.assertEqual(self.env_file.read_text(), "")

    def test_malformed_json_blocks_staple_and_publication(self):
        result = self.run_step("package, notarize & staple", NOTARY_MODE="malformed")
        self.assertNotEqual(result.returncode, 0)
        self.assert_package_calls(1)
        self.assertTrue(self.calls("plutil"))
        self.assertEqual(self.env_file.read_text(), "")

    def test_second_submission_failure_blocks_staple_and_publication(self):
        for scenario, diagnostic in (
            ("second-transport", None), ("second-invalid", "submission-dmg"),
        ):
            with self.subTest(scenario=scenario):
                self.log.unlink(missing_ok=True)
                result = self.run_step("package, notarize & staple", NOTARY_MODE=scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assert_package_calls(2, diagnostic=diagnostic)
                self.assertEqual(self.env_file.read_text(), "")

    def test_staple_failure_blocks_publication(self):
        result = self.run_step("package, notarize & staple", NOTARY_MODE="staple")
        self.assertNotEqual(result.returncode, 0)
        self.assert_package_calls(2, staple=True)
        self.assertEqual(self.env_file.read_text(), "")


class WindowsShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".native-windows-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "test/Plugins/codec.bundle"
        shutil.copytree(ROOT / "test/Plugins/codec.bundle", self.bundle)
        self.destination = self.bundle / "Contents/Windows64/codec.4DX"
        self.output = self.root / "test/plugins/codec.bundle/contents/windows64/codec.4DX"
        self.preserved = {
            path.relative_to(self.bundle): path.read_bytes()
            for path in self.bundle.rglob("*")
            if path.is_file() and path != self.destination
        }
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        # PowerShell runs real filesystem cmdlets, never a native build or signing tool.
        self.log = self.root / "unexpected-native-calls"
        for name in ("msbuild", "xcodebuild", "lipo", "codesign", "security",
                     "xcrun", "ditto", "hdiutil", "4D"):
            executable = self.bin / name
            executable.write_text(
                f"#!{sys.executable}\n"
                "import os, sys\n"
                "from pathlib import Path\n"
                "Path(os.environ['CALL_LOG']).write_text(sys.argv[0])\n"
                "sys.exit(99)\n"
            )
            executable.chmod(0o755)
        self.env = {
            "PATH": str(self.bin), "CALL_LOG": str(self.log),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        self.pwsh = "/usr/local/bin/pwsh"
        self.assertTrue(Path(self.pwsh).is_file(), "PowerShell is required for native tests")

    def run_step(self, name, prelude="", postlude=""):
        script = step(name)
        for key, value in (("PRODUCT_NAME", "codec"), ("BASE_DIR", "test")):
            script = script.replace("${{ env." + key + " }}", value)
        self.assertNotIn("${{", script)
        result = subprocess.run(
            [self.pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference = 'Stop'\n" + prelude + "\n" + script
             + "\n" + postlude],
            cwd=self.root, env=self.env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30,
        )
        self.assertFalse(self.log.exists(), "A real native operation was attempted")
        return result

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_preserved(self):
        for relative, data in self.preserved.items():
            self.assertEqual((self.bundle / relative).read_bytes(), data, str(relative))

    def clean(self):
        for relative in ("test/Plugins/Default/stale.4DX", "Objs/Release/stale.obj"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale intermediate")
        self.assert_ok(self.run_step("clean stale outputs"))
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.root / "test/Plugins/Default").exists())
        self.assertFalse((self.root / "Objs").exists())
        self.assert_preserved()

    def test_cleanup_accepts_already_missing_outputs(self):
        self.clean()
        self.assert_ok(self.run_step("clean stale outputs"))
        self.assertFalse(self.destination.exists())
        self.assert_preserved()

    def test_cleanup_removal_errors_abort_before_build_can_proceed(self):
        paths = (
            "test/Plugins/codec.bundle/Contents/Windows64/codec.4DX",
            "test/Plugins/Default", "Objs",
        )
        for failing in paths:
            with self.subTest(failing=failing):
                self.destination.write_bytes(b"stale binary")
                for relative in paths[1:]:
                    path = self.root / relative / "stale"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"stale intermediate")
                mock = r'''
function Remove-Item {
    [CmdletBinding()]
    param([string]$LiteralPath, [switch]$Recurse, [switch]$Force)
    if ($LiteralPath -eq 'FAILING_PATH') {
        Write-Error "mock removal denied"
        return
    }
    Microsoft.PowerShell.Management\Remove-Item @PSBoundParameters
}
'''.replace("FAILING_PATH", failing)
                result = self.run_step(
                    "clean stale outputs", prelude=mock,
                    postlude="Set-Content -LiteralPath 'cleanup-succeeded' -Value 'yes'",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("mock removal denied", result.stdout + result.stderr)
                self.assertTrue((self.root / failing).exists())
                self.assertFalse((self.root / "cleanup-succeeded").exists())
                self.assert_preserved()

    def test_cleanup_and_exact_msbuild_output_normalization(self):
        self.clean()
        # Deliberately earlier stale matches must never be selected recursively.
        stale = self.root / "test/aaa-stale/codec.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive first match")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"mock rebuilt Release x64")
        self.assert_ok(self.run_step("normalize windows output to canonical case"))
        self.assertEqual(self.destination.read_bytes(), b"mock rebuilt Release x64")
        self.assertEqual(self.output.read_bytes(), b"mock rebuilt Release x64")
        self.assertEqual(stale.read_bytes(), b"wrong recursive first match")
        self.assert_preserved()

    def test_missing_exact_output_rejects_recursive_stale_match(self):
        self.clean()
        stale = self.root / "test/aaa-stale/codec.4DX"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"wrong recursive first match")
        result = self.run_step("normalize windows output to canonical case")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Windows binary missing at exact MSBuild output",
                      result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertEqual(stale.read_bytes(), b"wrong recursive first match")
        self.assert_preserved()

    def test_same_physical_path_skips_self_copy_on_case_insensitive_filesystem(self):
        self.clean()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"mock rebuilt Release x64")
        same_path = self.destination.exists() and os.path.samefile(
            self.output, self.destination
        )
        result = self.run_step("normalize windows output to canonical case")
        self.assert_ok(result)
        self.assertEqual("skipping copy." in result.stdout, same_path)
        self.assertEqual(self.destination.read_bytes(), b"mock rebuilt Release x64")
        self.assertEqual(os.path.samefile(self.output, self.destination), same_path)
        self.assert_preserved()


class NativeConfigurationTests(unittest.TestCase):
    def test_windows_exact_output_matches_release_x64_project(self):
        project = ET.parse(ROOT / "codec.vcxproj")
        namespace = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        condition = "'$(Configuration)|$(Platform)'=='Release|x64'"
        outdirs = [node.text for node in project.findall(".//m:OutDir", namespace)
                   if node.get("Condition") == condition]
        extensions = [node.text for node in project.findall(".//m:TargetExt", namespace)
                      if node.get("Condition") == condition]
        self.assertEqual(len(outdirs), 1)
        self.assertEqual(extensions, [".4DX"])
        actual = (outdirs[0].replace("$(ProjectDir)", "")
                  .replace("$(ProjectName)", "codec").replace("\\", "/")
                  + "codec" + extensions[0])
        normalize = step("normalize windows output to canonical case")
        match = re.search(r'^\$source = "([^"]+)"$', normalize, re.MULTILINE)
        self.assertIsNotNone(match)
        expected = match[1].replace("$base", "test").replace("$product", "codec")
        self.assertEqual(actual, expected)
        self.assertIn("Test-Path -LiteralPath $source -PathType Leaf", normalize)
        self.assertIn("throw ", normalize)
        self.assertNotIn("-Recurse", normalize)
        self.assertIn("$sourceResolved -ieq $destResolved", normalize)
        self.assertIn("Copy-Item -LiteralPath $source $destination -Force", normalize)

    def test_windows_fresh_invalidation_and_original_platform_settings(self):
        clean = step("clean stale outputs")
        removals = re.findall(r"^\s*Remove-Item (.+)$", clean, re.MULTILINE)
        self.assertEqual(removals, [
            '-LiteralPath "$base/Plugins/$product.bundle/Contents/Windows64/$product.4DX" -Force -ErrorAction Stop',
            '-LiteralPath "$base/Plugins/Default" -Recurse -Force -ErrorAction Stop',
            '-LiteralPath "Objs" -Recurse -Force -ErrorAction Stop',
        ])
        self.assertEqual(re.findall(
            r'^if \(Test-Path -LiteralPath (.+) -ErrorAction Stop\) \{$',
            clean, re.MULTILINE,
        ), [
            '"$base/Plugins/$product.bundle/Contents/Windows64/$product.4DX"',
            '"$base/Plugins/Default"', '"Objs"',
        ])
        self.assertNotIn("SilentlyContinue", clean)
        self.assertNotIn("catch", clean)
        self.assertLess(WORKFLOW.index("- name: clean stale outputs"),
                        WORKFLOW.index("- name: build x64"))
        self.assertIn("/p:Configuration=Release /p:Platform=x64", step("build x64"))
        self.assertIn("/p:PlatformToolset=v143 /p:WindowsTargetPlatformVersion=10.0",
                      step("build x64"))
        project = ET.parse(ROOT / "codec.vcxproj")
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        self.assertEqual(
            {node.get("Include") for node in project.findall(".//m:ProjectConfiguration", ns)},
            {"Debug|Win32", "Debug|x64", "Release|Win32", "Release|x64"},
        )
        self.assertEqual({node.text for node in project.findall(".//m:PlatformToolset", ns)},
                         {"v140"})

    def test_original_macos_settings_and_release_secrets(self):
        project = (ROOT / source.PROJECT).read_text()
        for setting, value, count in (
            ("SDKROOT", "macosx", 6), ("MACOSX_DEPLOYMENT_TARGET", "10.9", 3),
            ("CLANG_CXX_LIBRARY", '"libc++"', 6),
            ("INFOPLIST_FILE", '"codec copy-Info.plist"', 3),
            ("WRAPPER_EXTENSION", "bundle", 3),
        ):
            self.assertEqual(len(re.findall(
                rf"(?m)^\s*{setting} = {re.escape(value)};", project
            )), count)
        for name in ("Default", "Development", "Deployment"):
            self.assertEqual(len(re.findall(rf"(?m)^\s*name = {name};", project)), 2)
        self.assertIn("English.lproj/InfoPlist.strings", project)
        for resource in ("manifest.json in CopyFiles", "constants.xlf in CopyFiles",
                         "InfoPlist.strings in Resources"):
            self.assertIn(resource, project)
        self.assertEqual(set(re.findall(r"\$\{\{ secrets\.([A-Z_]+) \}\}", WORKFLOW)), {
            "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
            "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
            "NOTARYTOOL_PASSWORD",
        })
        self.assertIn("runs-on: windows-latest", WORKFLOW)
        self.assertIn("runs-on: macos-latest", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
