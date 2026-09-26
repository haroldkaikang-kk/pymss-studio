from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf

if __package__:
    from . import _bootstrap as _worker_test_bootstrap
else:
    import _bootstrap as _worker_test_bootstrap

from worker_audio import _DiskMixBuffer, _apply_track_effects, cmd_export_editor_mix


class EditorEffectTests(unittest.TestCase):
    def _export_payload(self, root: Path, source: Path, *, name: str = "effects") -> dict:
        return {
            "project": {
                "id": "project",
                "name": name,
                "masterVolume": 1,
                "masterPan": 0,
                "assets": [{
                    "id": "source",
                    "path": str(source),
                    "duration": 0.2,
                    "sampleRate": 1000,
                    "channels": 1,
                }],
                "tracks": [{
                    "id": "track",
                    "sourceId": "source",
                    "volume": 1,
                    "pan": 0,
                    "muted": False,
                    "solo": False,
                    "effects": {"reverb": 0, "delay": 1, "delayTime": 0.1},
                    "clips": [{
                        "assetId": "source",
                        "start": 0,
                        "offset": 0,
                        "duration": 0.2,
                        "volume": 1,
                        "fadeIn": 0,
                        "fadeOut": 0,
                        "muted": False,
                    }],
                }],
            },
            "exportDir": str(root / "output"),
            "format": "wav",
        }

    def test_disabled_effects_leave_audio_unchanged(self) -> None:
        audio = np.array([[0.1, -0.2, 0.3]], dtype=np.float32)
        rendered = _apply_track_effects(audio, {}, 1000)
        np.testing.assert_array_equal(rendered, audio)

    def test_disk_mix_buffer_grows_without_losing_mono_or_stereo_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            buffer = _DiskMixBuffer(np, root, ".mix-test-", 1, 4)
            original_path = buffer.path
            buffer.add(0, np.ones((1, 4), dtype=np.float32))
            buffer.add(4, np.array([[0.5, 0.5], [0.25, 0.25]], dtype=np.float32))
            rendered = buffer.block(0, 6, 2)
            grown_path = buffer.path
            buffer.close()

            np.testing.assert_array_equal(rendered[:, :4], np.ones((2, 4), dtype=np.float32))
            np.testing.assert_array_equal(rendered[:, 4:], np.array([[0.5, 0.5], [0.25, 0.25]], dtype=np.float32))
            self.assertFalse(original_path.exists())
            self.assertFalse(grown_path.exists())

    def test_echo_preserves_channels_and_adds_a_tail(self) -> None:
        audio = np.zeros((2, 10), dtype=np.float32)
        audio[:, 0] = 1.0
        rendered = _apply_track_effects(audio, {"delay": 1, "delayTime": 0.1}, 1000)
        self.assertEqual(rendered.shape, (2, 510))
        self.assertGreater(float(np.abs(rendered[:, 100:]).max()), 0.0)

    def test_compressor_reduces_large_peaks(self) -> None:
        audio = np.ones((1, 32), dtype=np.float32)
        rendered = _apply_track_effects(audio, {"compressor": 1}, 1000)
        self.assertLess(float(np.max(np.abs(rendered))), 1.0)

    def test_editor_export_passes_track_effects_to_the_rendered_mix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            samples = np.zeros(200, dtype=np.float32)
            samples[0] = 1.0
            sf.write(source, samples, 1000)
            payload = self._export_payload(root, source)
            with mock.patch("worker_audio.emit"):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            rendered, sample_rate = sf.read(str(root / "output" / "effects_mix.wav"))

        self.assertEqual(sample_rate, 1000)
        self.assertGreater(len(rendered), len(samples))

    def test_repeated_editor_exports_preserve_the_previous_mix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(200, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source, name="repeat")
            events: list[dict] = []
            with mock.patch("worker_audio.emit", side_effect=lambda kind, value, **_kwargs: events.append(value) if kind == "editor_mix_exported" else None):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
                first = root / "output" / "repeat_mix.wav"
                first_bytes = first.read_bytes()
                self.assertEqual(cmd_export_editor_mix(payload), 0)

            second = root / "output" / "repeat_mix_2.wav"
            self.assertTrue(second.is_file())
            self.assertEqual(first.read_bytes(), first_bytes)
            self.assertEqual([Path(event["path"]).name for event in events], [first.name, second.name])

    def test_export_fails_instead_of_silently_skipping_a_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source, name="missing")
            payload["project"]["assets"].append({
                "id": "missing",
                "path": str(root / "missing.wav"),
                "name": "missing.wav",
                "duration": 0.1,
                "sampleRate": 1000,
                "channels": 1,
            })
            payload["project"]["tracks"].append({
                "id": "missing-track",
                "sourceId": "missing",
                "volume": 1,
                "pan": 0,
                "muted": False,
                "solo": False,
                "clips": [{
                    "assetId": "missing",
                    "start": 0,
                    "offset": 0,
                    "duration": 0.1,
                    "volume": 1,
                    "muted": False,
                }],
            })
            with mock.patch("worker_audio.emit"), \
                 mock.patch("worker_audio.emit_error", return_value=1) as emit_error:
                self.assertEqual(cmd_export_editor_mix(payload), 1)

            self.assertEqual(emit_error.call_args.args[0], "EDITOR_EXPORT_SOURCE_MISSING")
            self.assertIn("missing.wav", emit_error.call_args.args[1])
            self.assertFalse((root / "output" / "missing_mix.wav").exists())

    def test_auto_sample_rate_uses_the_highest_active_rate_with_a_48khz_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            first = root / "first.wav"
            second = root / "second.wav"
            sf.write(first, np.ones(1600, dtype=np.float32) * 0.1, 32000)
            sf.write(second, np.ones(4800, dtype=np.float32) * 0.1, 96000)
            payload = self._export_payload(root, first, name="rates")
            payload["project"]["assets"][0].update(duration=0.05, sampleRate=32000)
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.05
            payload["project"]["assets"].append({
                "id": "second",
                "path": str(second),
                "name": second.name,
                "duration": 0.05,
                "sampleRate": 96000,
                "channels": 1,
            })
            payload["project"]["tracks"].append({
                "id": "second-track",
                "sourceId": "second",
                "volume": 1,
                "pan": 0,
                "muted": False,
                "solo": False,
                "effects": {},
                "clips": [{
                    "assetId": "second",
                    "start": 0,
                    "offset": 0,
                    "duration": 0.05,
                    "volume": 1,
                    "muted": False,
                }],
            })
            events: list[dict] = []
            with mock.patch("worker_audio.emit", side_effect=lambda kind, value, **_kwargs: events.append(value) if kind == "editor_mix_exported" else None):
                self.assertEqual(cmd_export_editor_mix(payload), 0)

            _rendered, sample_rate = sf.read(root / "output" / "rates_mix.wav")
            self.assertEqual(sample_rate, 48000)
            self.assertEqual(events[-1]["sampleRate"], 48000)

            payload["fileName"] = "rates_44100.flac"
            payload["format"] = "flac"
            payload["audioParams"] = {"sampleRate": 44100, "flacBitDepth": "PCM_24"}
            with mock.patch("worker_audio.emit"):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            _rendered, sample_rate = sf.read(root / "output" / "rates_44100.flac")
            self.assertEqual(sample_rate, 44100)

    def test_peak_protection_is_optional_and_reports_its_adjustment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.8, 1000, subtype="FLOAT")
            payload = self._export_payload(root, source, name="peak")
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["volume"] = 2
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.1
            payload["audioParams"] = {"wavBitDepth": "FLOAT", "peakProtection": True}
            protected_events: list[dict] = []
            with mock.patch("worker_audio.emit", side_effect=lambda kind, value, **_kwargs: protected_events.append(value) if kind == "editor_mix_exported" else None):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            protected, _sample_rate = sf.read(root / "output" / "peak_mix.wav")

            payload["fileName"] = "peak_raw.wav"
            payload["audioParams"]["peakProtection"] = False
            raw_events: list[dict] = []
            with mock.patch("worker_audio.emit", side_effect=lambda kind, value, **_kwargs: raw_events.append(value) if kind == "editor_mix_exported" else None):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            raw, _sample_rate = sf.read(root / "output" / "peak_raw.wav")

            self.assertLessEqual(float(np.max(np.abs(protected))), 0.981)
            self.assertGreater(float(np.max(np.abs(raw))), 1.5)
            self.assertTrue(protected_events[-1]["peakProtectionApplied"])
            self.assertLess(protected_events[-1]["peakAdjustmentDb"], 0)
            self.assertFalse(raw_events[-1]["peakProtectionApplied"])

            payload["fileName"] = "peak_pcm.wav"
            payload["audioParams"] = {"wavBitDepth": "PCM_24", "peakProtection": False}
            pcm_events: list[dict] = []
            with mock.patch("worker_audio.emit", side_effect=lambda kind, value, **_kwargs: pcm_events.append(value) if kind == "editor_mix_exported" else None):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            pcm, _sample_rate = sf.read(root / "output" / "peak_pcm.wav")
            self.assertLessEqual(float(np.max(np.abs(pcm))), 0.981)
            self.assertTrue(pcm_events[-1]["peakProtectionApplied"])

    def test_export_fades_match_the_linear_preview_curve(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32), 1000, subtype="FLOAT")
            payload = self._export_payload(root, source, name="fade")
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0].update(duration=0.1, fadeIn=0.1)
            with mock.patch("worker_audio.emit"):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            rendered, _sample_rate = sf.read(root / "output" / "fade_mix.wav")

            self.assertAlmostEqual(float(rendered[50]), 50 / 99, places=3)

    def test_multi_clip_preallocation_preserves_timeline_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000, subtype="FLOAT")
            payload = self._export_payload(root, source, name="timeline")
            track = payload["project"]["tracks"][0]
            track["effects"] = {}
            track["clips"] = [
                {
                    "id": "first",
                    "assetId": "source",
                    "start": 0,
                    "offset": 0,
                    "duration": 0.1,
                    "volume": 1,
                    "muted": False,
                },
                {
                    "id": "second",
                    "assetId": "source",
                    "start": 0.05,
                    "offset": 0,
                    "duration": 0.1,
                    "volume": 1,
                    "muted": False,
                },
            ]
            with mock.patch("worker_audio.emit"):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            rendered, _sample_rate = sf.read(root / "output" / "timeline_mix.wav")

            self.assertEqual(len(rendered), 150)
            self.assertAlmostEqual(float(rendered[25]), 0.1, places=3)
            self.assertAlmostEqual(float(rendered[75]), 0.2, places=3)
            self.assertAlmostEqual(float(rendered[125]), 0.1, places=3)

    def test_master_pan_reports_the_final_stereo_channel_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source, name="master-pan")
            payload["project"]["masterPan"] = 0.5
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.1
            events: list[dict] = []
            with mock.patch("worker_audio.emit", side_effect=lambda kind, value, **_kwargs: events.append(value) if kind == "editor_mix_exported" else None):
                self.assertEqual(cmd_export_editor_mix(payload), 0)
            rendered, _sample_rate = sf.read(root / "output" / "master-pan_mix.wav", always_2d=True)

            self.assertEqual(rendered.shape[1], 2)
            self.assertEqual(events[-1]["channels"], 2)

    def test_windows_reserved_export_names_are_made_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source)
            payload["fileName"] = "CON.wav"
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.1
            with mock.patch("worker_audio.emit"):
                self.assertEqual(cmd_export_editor_mix(payload), 0)

            self.assertTrue((root / "output" / "_CON.wav").is_file())

    def test_background_export_reports_monotonic_progress_with_the_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source, name="progress")
            payload["taskId"] = "editor-export-task"
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.1
            events: list[tuple[str, dict, str | None]] = []
            with mock.patch(
                "worker_audio.emit",
                side_effect=lambda kind, value, task_id=None: events.append((kind, value, task_id)),
            ):
                self.assertEqual(cmd_export_editor_mix(payload), 0)

            progress = [value["completed"] for kind, value, _task_id in events if kind == "editor_export_progress"]
            self.assertEqual(progress, sorted(progress))
            self.assertEqual(progress[-1], 100)
            self.assertTrue(all(task_id == "editor-export-task" for _kind, _value, task_id in events))
            self.assertEqual(events[-1][0], "editor_mix_exported")

    def test_export_write_failure_removes_hidden_and_visible_partial_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source, name="write-failure")
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.1
            with mock.patch("worker_audio.emit"), \
                 mock.patch("soundfile.SoundFile.write", side_effect=RuntimeError("write failed")), \
                 mock.patch("worker_audio.emit_error", return_value=1):
                self.assertEqual(cmd_export_editor_mix(payload), 1)

            output_dir = root / "output"
            self.assertFalse((output_dir / "write-failure_mix.wav").exists())
            self.assertEqual(list(output_dir.glob(".pymss-export-*.part")), [])

    def test_cooperative_cancellation_during_write_removes_the_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            source = root / "source.wav"
            sf.write(source, np.ones(100, dtype=np.float32) * 0.1, 1000)
            payload = self._export_payload(root, source, name="cancelled")
            payload["taskId"] = "cancel-write"
            payload["project"]["tracks"][0]["effects"] = {}
            payload["project"]["tracks"][0]["clips"][0]["duration"] = 0.1
            output_dir = root / "output"
            cancel_path = output_dir / ".pymss-export-cancel-write.cancel"
            events: list[str] = []

            def cancel_during_write(*_args, **_kwargs):
                cancel_path.write_text("cancel", encoding="utf-8")

            with mock.patch("soundfile.SoundFile.write", side_effect=cancel_during_write), \
                 mock.patch("worker_audio.emit", side_effect=lambda kind, _value, **_kwargs: events.append(kind)):
                self.assertEqual(cmd_export_editor_mix(payload), 0)

            self.assertIn("task_cancelled", events)
            self.assertFalse((output_dir / "cancelled_mix.wav").exists())
            self.assertEqual(list(output_dir.glob(".pymss-export-*.part")), [])
            self.assertFalse(cancel_path.exists())


if __name__ == "__main__":
    unittest.main()
