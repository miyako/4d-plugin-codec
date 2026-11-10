"""Compile actual first-party sources and the complete unmodified SDK (macOS)."""

import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "4D Plugin API/4DPluginAPI.c",
    "4D Plugin API/Classes/C_TEXT.cpp",
    "4D Plugin API/Classes/C_BLOB.cpp",
    "4D Plugin API/Classes/C_LONGINT.cpp",
    "4D Plugin API/Classes/ARRAY_TEXT.cpp",
    "support/4DPlugin-JSON.cpp",
    "4DPlugin-codec.cpp",
)


@unittest.skipUnless(platform.system() == "Darwin", "native Cocoa shim requires macOS")
class OwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="codec-ownership-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = ROOT
        revision = os.environ.get("CODEC_OWNERSHIP_REVISION")
        if revision:
            source = work / "baseline"
            files = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True
            ).splitlines()
            for name in files:
                if name.endswith((".c", ".cpp", ".h", ".hpp")):
                    target = source / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(subprocess.check_output(
                        ["git", "show", f"{revision}:{name}"], cwd=ROOT
                    ))
        cls.binary = work / "ownership"
        command = [
            "clang++", "-std=c++11", "-x", "objective-c++",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
            "-Wno-deprecated-declarations", "-Wno-multichar",
            "-I", str(source), "-I", str(source / "4D Plugin API"),
            "-I", str(source / "4D Plugin API/Classes"),
            "-I", str(source / "include"), "-I", str(source / "support"),
            *[str(source / name) for name in SOURCES],
            str(ROOT / ".github/tests/ownership.cpp"),
            "-framework", "Cocoa", "-framework", "CoreGraphics",
            "-o", str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def exercise(self, name):
        result = subprocess.run(
            [str(self.binary), name], text=True, capture_output=True,
            env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                 "UBSAN_OPTIONS": "halt_on_error=1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_string_setters(self):
        self.exercise("setters")

    def test_picture_setter(self):
        self.exercise("picture")

    def test_owning_getters_and_handoffs(self):
        self.exercise("getters")

    def test_boolean_getter_mismatch(self):
        self.exercise("boolean")

    def test_number_getter_mismatch(self):
        self.exercise("number")

    def test_collection_getter_mismatch(self):
        self.exercise("collection")

    def test_array_transfers_and_borrowed_copies(self):
        self.exercise("arrays")

    def test_actual_dispatcher(self):
        self.exercise("dispatcher")


if __name__ == "__main__":
    unittest.main()
