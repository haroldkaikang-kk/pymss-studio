"""Real VR weights and synthetic MP3; verifies execution, not musical quality."""
import argparse
import json
import logging
import platform
import sys
import time
from pathlib import Path
from unittest import mock

import numpy as np
import torch
from pymss import MSSeparator, download_model
from pymss.audio_io import load_audio, save_audio
from pymss.separator import _resolve_public_device, _select_device, _prefer_mlx_for_auto


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    logger = logging.getLogger("intel-vr-regression")
    torch.set_num_threads(2)
    intel_platform = mock.Mock(wraps=platform)
    intel_platform.system.return_value = "Darwin"
    intel_platform.machine.return_value = "x86_64"
    # Mock only the engine platform, leaving audio libraries on the real host.
    # Reproduce an Intel AMD system reporting MPS, including saved MLX options.
    with mock.patch("pymss.separator.platform", intel_platform), mock.patch.object(torch.backends.mps, "is_available", return_value=True):
        for requested in ("auto", "cpu", "mps", "mlx"):
            device, params = _resolve_public_device(requested, {"mps_model_backend": "mlx_full"}, logger)
            selected = _select_device(device, [0], logger)
            params = _prefer_mlx_for_auto(device, selected, params, logger)
            assert selected == "cpu", (requested, selected)
            assert "mps_model_backend" not in params, params
    print("Device regression passed; downloading VR model", flush=True)
    name = "3_HP-Vocal-UVR.pth"
    download_model(name, model_dir=root / "models", source="huggingface", timeout=120)
    sr = 44100
    t = np.arange(sr * 3) / sr
    signal = 0.12 * np.sin(2 * np.pi * 220 * t) + 0.07 * np.sin(2 * np.pi * 523.25 * t)
    mix = np.column_stack([signal, np.roll(signal, 37)]).astype(np.float32)
    source = root / "Intel 分离回归 (MP3).mp3"
    save_audio(source, mix, sr, "mp3", {"mp3_bit_rate": "320k"})
    print("MP3 prepared; starting real VR inference", flush=True)
    with mock.patch.dict(sys.modules, {"mlx": None, "mlx.core": None}), mock.patch(
        "pymss.separator.platform", intel_platform
    ), mock.patch.object(
        torch.backends.mps, "is_available", return_value=True
    ):
        with MSSeparator.from_model_name(
            name, model_dir=root / "models", device="auto", store_dirs=str(root / "outputs"),
            save_as_folder=True, output_format="wav", audio_params={"wav_bit_depth": "FLOAT"},
            inference_params={"batch_size": 2, "window_size": 512, "aggression": 5},
        ) as separator:
            assert separator.device == "cpu", separator.device
            assert separator.model.mps_model_backend == "torch"
            success = separator.process_folder(str(source))
            assert success == [source.name], success
    outputs = sorted((root / "outputs").rglob("*.wav"))
    assert len(outputs) == 2, outputs
    details = []
    for path in outputs:
        audio, rate = load_audio(path, sr=None, mono=False)
        assert rate == sr and audio.shape[0] == 2 and audio.shape[1] > sr * 2, (rate, audio.shape)
        assert np.isfinite(audio).all() and np.max(np.abs(audio)) > 0
        details.append({"file": path.name, "samples": audio.shape[1], "sample_rate": rate})
    report = {"status": "passed", "host": platform.platform(), "torch": torch.__version__,
              "model": name, "device": "cpu", "simulated_mps_available": True,
              "mlx_import_blocked": True, "input": "synthetic MP3, not user audio",
              "seconds": round(time.monotonic() - started, 2), "outputs": details}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
