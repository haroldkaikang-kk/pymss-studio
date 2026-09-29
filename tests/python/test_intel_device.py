import unittest
from unittest import mock

if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import worker_infer
import worker_models


class IntelDeviceTests(unittest.TestCase):
    def test_intel_auto_and_saved_apple_devices_use_cpu(self):
        with mock.patch.object(worker_infer.sys, "platform", "darwin"), mock.patch.object(
            worker_infer.platform, "machine", return_value="x86_64"
        ):
            for requested in (None, "auto", "mps", "mlx"):
                with self.subTest(requested=requested):
                    device, ids, label = worker_infer._resolve_separator_device(requested, [1])
                    self.assertEqual((device, ids), ("cpu", [0]))
                    self.assertIn("Intel compatibility", label)

    def test_other_platforms_keep_their_device(self):
        for system, machine in (("darwin", "arm64"), ("linux", "x86_64"), ("win32", "AMD64")):
            with mock.patch.object(worker_infer.sys, "platform", system), mock.patch.object(
                worker_infer.platform, "machine", return_value=machine
            ):
                for requested in ("auto", "mps", "mlx", "cpu"):
                    with self.subTest(system=system, requested=requested):
                        self.assertEqual(worker_infer._resolve_separator_device(requested, [0]),
                                         (requested, [0], requested))

    def test_intel_ui_does_not_offer_amd_mps_or_mlx(self):
        torch = mock.Mock()
        torch.__version__ = "2.2.2"
        torch.version.hip = None
        torch.version.cuda = None
        torch.cuda.is_available.return_value = False
        torch.cuda.device_count.return_value = 0
        torch.backends.mps.is_available.return_value = True
        with mock.patch.dict("sys.modules", {"torch": torch, "pymss": mock.Mock()}), mock.patch.object(
            worker_models.sys, "platform", "darwin"
        ), mock.patch.object(worker_models.platform, "machine", return_value="x86_64"), mock.patch.object(
            worker_models, "emit"
        ) as emit, mock.patch.object(worker_models, "import_available", return_value=True), mock.patch.object(
            worker_models, "package_version", return_value="test"
        ):
            self.assertEqual(worker_models.cmd_env_info(), 0)
        self.assertFalse(emit.call_args.args[1]["mpsAvailable"])
        self.assertFalse(emit.call_args.args[1]["mlxAvailable"])


if __name__ == "__main__":
    unittest.main()
