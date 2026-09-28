import json
import sys
import unittest
from pathlib import Path
from unittest import mock

if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import worker_bootstrap as runtime


class IntelRuntimeTests(unittest.TestCase):
    def test_intel_selects_cpu_pins_and_local_wheels(self):
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(runtime.platform, "machine", return_value="x86_64"):
            manifest = runtime._manifest()
            self.assertEqual(set(manifest["backends"]), {"cpu"})
            self.assertEqual(manifest["backends"]["cpu"]["torch"]["requirement"], "torch==2.2.2")
            self.assertIn("--find-links", runtime._intel_pip_args())
            with mock.patch.object(runtime, "_latest_pypi_version", side_effect=AssertionError("must not upgrade Intel core from PyPI")):
                self.assertEqual(runtime._core_target_version("pymss"), "2.1.7+intel1")
                self.assertEqual(runtime._core_target_version("pymss-core"), "0.1.10+intel1")

    def test_other_platforms_keep_original_manifest_and_updates(self):
        original = json.loads(runtime.MANIFEST_PATH.read_text())
        for system, machine in [("darwin", "arm64"), ("linux", "x86_64"), ("win32", "AMD64")]:
            with self.subTest(system=system), mock.patch.object(sys, "platform", system), mock.patch.object(runtime.platform, "machine", return_value=machine):
                self.assertEqual(runtime._manifest(), original)
                self.assertEqual(runtime._intel_pip_args(), [])
                with mock.patch.object(runtime, "_latest_pypi_version", return_value="9.0"):
                    self.assertEqual(runtime._core_target_version("pymss"), "9.0")
