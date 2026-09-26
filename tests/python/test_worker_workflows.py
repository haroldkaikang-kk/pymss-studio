from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import _bootstrap as _worker_test_bootstrap
else:
    import _bootstrap as _worker_test_bootstrap

import worker_workflows
from worker_workflows import (
    _apply_simple_ensembles,
    _apply_simple_output_names,
    _prepare_legacy_global_input,
    _prepare_simple_runtime_definition,
    _finalize_simple_output_paths,
    _render_simple_filename,
    _simple_output_names,
    _workflow_output_stem,
)


class WorkflowTemporaryFileTests(unittest.TestCase):
    def test_cleanup_keeps_the_shared_directory_available_for_parallel_writers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(worker_workflows.tempfile, "gettempdir", return_value=temporary):
                payload = {"workflow": {"nodes": []}}
                path, _format = worker_workflows._write_workflow_file(payload, "cleanup-shared-dir")
                worker_workflows._cleanup_workflow_file("cleanup-shared-dir")

                self.assertFalse(path.exists())
                self.assertTrue(path.parent.is_dir())

    def test_single_run_removes_the_transient_definition_on_success_and_failure(self) -> None:
        for task_id, error in (("cleanup-success", None), ("cleanup-failure", RuntimeError("failed"))):
            with self.subTest(task_id=task_id):
                payload = {"taskId": task_id, "workflow": {"nodes": []}, "output": "results"}
                path, _format = worker_workflows._write_workflow_file(payload, task_id)
                self.addCleanup(path.unlink, missing_ok=True)
                run = patch.object(
                    worker_workflows,
                    "_run_pymss",
                    return_value={"files": [], "outputs": [], "outputDir": "results", "outputFormat": "wav"},
                    side_effect=error,
                )
                with run, patch.object(worker_workflows, "emit"), patch.object(worker_workflows, "emit_error", return_value=1):
                    expected = 1 if error else 0
                    self.assertEqual(worker_workflows.cmd_infer_workflow(payload), expected)
                self.assertFalse(path.exists())

    def test_batch_run_removes_each_task_definition(self) -> None:
        task_ids = ["cleanup-batch-1", "cleanup-batch-2"]
        payload = {
            "taskId": "cleanup-batch",
            "workflow": {"nodes": []},
            "output": "results",
            "tasks": [{"taskId": task_id} for task_id in task_ids],
        }
        paths = [worker_workflows._write_workflow_file(payload, task_id)[0] for task_id in task_ids]
        for path in paths:
            self.addCleanup(path.unlink, missing_ok=True)
        result = {"files": [], "outputs": [], "outputDir": "results", "outputFormat": "wav"}
        with patch.object(worker_workflows, "_run_pymss", return_value=result), \
             patch.object(worker_workflows, "emit"), patch.object(worker_workflows, "emit_error", return_value=1):
            self.assertEqual(worker_workflows.cmd_infer_workflow(payload), 0)
        self.assertTrue(all(not path.exists() for path in paths))


class LegacyWorkflowInputTests(unittest.TestCase):
    def test_legacy_placeholder_is_bound_to_global_input_without_mutating_definition(self) -> None:
        definition = {
            "nodes": [
                {"id": 1, "type": "pymss_load_audio", "widgets_values": ["input.wav", ""]},
                {"id": 2, "type": "pymss_load_audio", "widgets_values": ["", None]},
            ],
        }
        payload = {"workflow": definition}

        transient, inputs = _prepare_legacy_global_input(payload, "D:/Audio/song.wav", None)

        self.assertEqual(inputs, {"input.wav": "D:/Audio/song.wav"})
        self.assertEqual(definition["nodes"][1]["widgets_values"], ["", None])
        self.assertEqual(transient["workflow"]["nodes"][0]["widgets_values"], ["D:/Audio/song.wav", ""])
        self.assertEqual(transient["workflow"]["nodes"][1]["widgets_values"], ["D:/Audio/song.wav", None])

    def test_embedded_audio_paths_are_overridden_by_the_global_input(self) -> None:
        payload = {
            "workflow": {
                "nodes": [{"id": 1, "type": "pymss_load_audio", "widgets_values": ["D:/old/song.wav", None]}],
            },
        }

        transient, inputs = _prepare_legacy_global_input(payload, "D:/Audio/new.wav", None)

        self.assertEqual(inputs, {"D:/old/song.wav": "D:/Audio/new.wav"})
        self.assertEqual(
            transient["workflow"]["nodes"][0]["widgets_values"],
            ["D:/Audio/new.wav", None],
        )

    def test_named_slots_are_bound_to_the_global_file_after_ui_rollback(self) -> None:
        payload = {
            "workflow": {
                "nodes": [{"id": 1, "type": "pymss_load_audio", "widgets_values": ["input.wav", "lead"]}],
            },
        }

        _transient, inputs = _prepare_legacy_global_input(payload, "D:/Audio/song.wav", {"lead": "old.wav"})

        self.assertEqual(inputs, {"lead": "D:/Audio/song.wav"})

    def test_legacy_batch_nodes_get_a_transient_global_input_slot(self) -> None:
        payload = {
            "workflow": {
                "nodes": [{"id": 1, "type": "pymss_load_audio_batch", "widgets_values": ["old-folder", False, True]}],
            },
        }

        transient, inputs = _prepare_legacy_global_input(payload, "D:/Audio/song.wav", None)

        self.assertEqual(inputs, {"__pymss_studio_global_input__": "D:/Audio/song.wav"})
        self.assertEqual(
            transient["workflow"]["nodes"][0]["widgets_values"],
            ["old-folder", False, True, "__pymss_studio_global_input__"],
        )

    def test_yaml_workflows_keep_the_original_payload_and_inputs(self) -> None:
        payload = {"workflow": {"steps": [{"id": "one", "input": "input"}]}}

        transient, inputs = _prepare_legacy_global_input(payload, "D:/Audio/song.wav", None)

        self.assertIs(transient, payload)
        self.assertEqual(inputs, {})


class WorkflowOutputMetadataTests(unittest.TestCase):
    def test_simple_filename_metadata_is_detected_and_runtime_copy_is_flat(self) -> None:
        definition = {
            "version": 1,
            "defaults": {"output_format": "flac"},
            "steps": [{
                "id": "split",
                "save": {"vocals": "vocals"},
                "output_names": {"vocals": "lead"},
            }],
        }
        self.assertTrue(_simple_output_names(definition))
        runtime = _prepare_simple_runtime_definition(definition)
        self.assertEqual(runtime["steps"][0]["save"], {"vocals": "Default"})
        self.assertEqual(runtime["steps"][0]["output_format"], "flac")
        self.assertEqual(definition["steps"][0]["save"]["vocals"], "vocals")

    def test_empty_filename_metadata_does_not_change_directory_outputs(self) -> None:
        definition = {
            "version": 1,
            "steps": [{"id": "split", "save": {"vocals": "vocals"}, "output_names": {}}],
        }
        self.assertFalse(_simple_output_names(definition))
        self.assertIs(_prepare_simple_runtime_definition(definition), definition)

    def test_editor_layout_metadata_is_removed_from_runtime_definition(self) -> None:
        definition = {
            "version": 1,
            "studio": {"editor": "simple", "viewport": {"x": 0, "y": 0, "zoom": 1}},
            "steps": [{"id": "split", "save": {"vocals": "vocals"}}],
        }
        runtime = _prepare_simple_runtime_definition(definition)
        self.assertNotIn("studio", runtime)
        self.assertIn("studio", definition)
        self.assertIsNot(runtime, definition)

    def test_ensemble_metadata_is_removed_before_pymss_yaml_parsing(self) -> None:
        definition = {
            "version": 1,
            "steps": [
                {"id": "split", "input": "input", "save": {}},
                {"id": "cleanup", "input": "blend.Vocals", "save": {}},
            ],
            "ensembles": [{
                "id": "blend",
                "inputs": [{"source": "split.vocals", "weight": 1}, {"source": "split.music", "weight": 1}],
                "algorithm": "avg_wave",
                "output_stem": "Vocals",
                "save": "Default",
            }],
        }
        runtime = _prepare_simple_runtime_definition(definition)
        self.assertNotIn("ensembles", runtime)
        self.assertEqual(runtime["steps"][1]["input"], "input")
        self.assertEqual(definition["steps"][1]["input"], "blend.Vocals")
        self.assertIn("ensembles", definition)
        self.assertIsNot(runtime, definition)

    def test_simple_ensemble_records_compile_to_graph_nodes_and_output_metadata(self) -> None:
        class DAGLink:
            def __init__(self, **values):
                self.__dict__.update(values)

        class DAGNode:
            def __init__(self, *, id, type, inputs, data, title=""):
                self.id = id
                self.type = type
                self.inputs = inputs
                self.data = data
                self.title = title

        graph_module = ModuleType("pymss.graph")
        graph_module.DAGLink = DAGLink
        graph_module.DAGNode = DAGNode
        graph_module.AUDIO = "AUDIO"
        graph_module.STRING = "STRING"
        pymss_module = ModuleType("pymss")
        pymss_module.graph = graph_module
        dag = SimpleNamespace(nodes=[
            DAGNode(id="input", type="input_audio", inputs=[], data={}),
            DAGNode(id="step:modelA", type="mss_separate", inputs=[], data={}),
            DAGNode(id="step:modelB", type="mss_separate", inputs=[], data={}),
            DAGNode(id="step:cleanup", type="mss_separate", inputs=[DAGLink(
                link_id=7,
                source_node_id="input",
                source_slot=0,
                target_node_id="step:cleanup",
                target_slot=0,
                type="AUDIO",
            )], data={}),
            DAGNode(id="save:modelA:Vocals", type="pymss_save_audio", inputs=[None, None], data={}),
        ])
        definition = {
            "steps": [
                {"id": "modelA", "model": "a.ckpt", "stems": ["Vocals"], "save": {"Vocals": "Default"}},
                {"id": "modelB", "stems": ["Drums", "Vocals"]},
                {"id": "cleanup", "input": "blend.Vocals", "stems": ["Voice"]},
            ],
            "ensembles": [{
                "id": "blend",
                "inputs": [
                    {"source": "input", "weight": 1},
                    {"source": "modelB.Vocals", "weight": 0.75},
                ],
                "algorithm": "avg_fft",
                "output_stem": "Vocals",
                "save": "Default",
                "output_name": "%stem%",
            }],
        }

        with tempfile.TemporaryDirectory() as directory:
            reserved_names = set()
            with patch.dict("sys.modules", {"pymss": pymss_module, "pymss.graph": graph_module}):
                step_metadata = _apply_simple_output_names(
                    dag,
                    definition,
                    input_path="D:/Audio/song.wav",
                    output_format="flac",
                    output_dir=Path(directory),
                    reserved_names=reserved_names,
                    apply_names=False,
                )
                ensemble_metadata = _apply_simple_ensembles(
                    dag,
                    definition,
                    input_path="D:/Audio/song.wav",
                    output_format="flac",
                    output_dir=Path(directory),
                    reserved_names=reserved_names,
                    start_index=len(step_metadata),
                )

        ensemble = next(node for node in dag.nodes if node.type == "pymss_audio_ensemble")
        save = next(node for node in dag.nodes if node.id == "studio:ensemble-save:blend")
        cleanup = next(node for node in dag.nodes if node.id == "step:cleanup")
        filename = next(node for node in dag.nodes if node.type == "StringConstant")
        self.assertEqual(ensemble.data["widgets_values"], [2, "avg_fft", 1.0, 0.75])
        self.assertEqual(
            [(link.source_node_id, link.source_slot, link.target_slot) for link in ensemble.inputs],
            [("input", 0, 0), ("step:modelB", 2, 1)],
        )
        self.assertEqual(save.inputs[0].source_node_id, ensemble.id)
        self.assertEqual(cleanup.inputs[0].source_node_id, ensemble.id)
        self.assertEqual(cleanup.inputs[0].source_slot, 0)
        self.assertEqual(cleanup.inputs[0].target_slot, 0)
        self.assertEqual(save.inputs[1].source_node_id, filename.id)
        self.assertEqual(filename.data["widgets_values"], ["Vocals_2"])
        self.assertEqual(step_metadata, [{"stem": "Vocals", "filename": ""}])
        self.assertEqual(ensemble_metadata, [{"stem": "Vocals", "filename": "Vocals_2.flac"}])

    def test_unsaved_simple_ensemble_can_feed_a_downstream_step(self) -> None:
        class DAGLink:
            def __init__(self, **values):
                self.__dict__.update(values)

        class DAGNode:
            def __init__(self, *, id, type, inputs, data, title=""):
                self.id = id
                self.type = type
                self.inputs = inputs
                self.data = data
                self.title = title

        graph_module = ModuleType("pymss.graph")
        graph_module.DAGLink = DAGLink
        graph_module.DAGNode = DAGNode
        graph_module.AUDIO = "AUDIO"
        graph_module.STRING = "STRING"
        pymss_module = ModuleType("pymss")
        pymss_module.graph = graph_module
        dag = SimpleNamespace(nodes=[
            DAGNode(id="input", type="input_audio", inputs=[], data={}),
            DAGNode(id="step:first", type="mss_separate", inputs=[], data={}),
            DAGNode(id="step:second", type="mss_separate", inputs=[], data={}),
            DAGNode(id="step:cleanup", type="mss_separate", inputs=[DAGLink(
                link_id=3,
                source_node_id="input",
                source_slot=0,
                target_node_id="step:cleanup",
                target_slot=0,
                type="AUDIO",
            )], data={}),
        ])
        definition = {
            "steps": [
                {"id": "first", "stems": ["Vocals"]},
                {"id": "second", "stems": ["Vocals"]},
                {"id": "cleanup", "input": "blend.Vocals", "stems": ["Voice"]},
            ],
            "ensembles": [{
                "id": "blend",
                "inputs": [
                    {"source": "first.Vocals", "weight": 1},
                    {"source": "second.Vocals", "weight": 0.5},
                ],
                "algorithm": "avg_wave",
                "output_stem": "Vocals",
                "save": False,
            }],
        }

        with patch.dict("sys.modules", {"pymss": pymss_module, "pymss.graph": graph_module}):
            metadata = _apply_simple_ensembles(
                dag,
                definition,
                input_path="D:/Audio/song.wav",
                output_format="wav",
            )

        ensemble = next(node for node in dag.nodes if node.id == "studio:ensemble:blend")
        cleanup = next(node for node in dag.nodes if node.id == "step:cleanup")
        self.assertEqual(metadata, [])
        self.assertFalse(any(node.id == "studio:ensemble-save:blend" for node in dag.nodes))
        self.assertEqual(cleanup.inputs[0].source_node_id, ensemble.id)
        link_ids = [
            link.link_id
            for node in dag.nodes
            for link in node.inputs
            if link is not None
        ]
        self.assertEqual(len(link_ids), len(set(link_ids)))

    def test_simple_ensemble_rejects_non_finite_weights_in_worker(self) -> None:
        class DAGLink:
            def __init__(self, **values):
                self.__dict__.update(values)

        class DAGNode:
            def __init__(self, *, id, type, inputs, data, title=""):
                self.id = id
                self.type = type
                self.inputs = inputs
                self.data = data
                self.title = title

        graph_module = ModuleType("pymss.graph")
        graph_module.DAGLink = DAGLink
        graph_module.DAGNode = DAGNode
        graph_module.AUDIO = "AUDIO"
        graph_module.STRING = "STRING"
        pymss_module = ModuleType("pymss")
        pymss_module.graph = graph_module

        for weight in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(weight=weight):
                dag = SimpleNamespace(nodes=[
                    DAGNode(id="input", type="input_audio", inputs=[], data={}),
                    DAGNode(id="step:model", type="mss_separate", inputs=[], data={}),
                ])
                definition = {
                    "steps": [{"id": "model", "stems": ["Vocals"]}],
                    "ensembles": [{
                        "id": "blend",
                        "inputs": [
                            {"source": "input", "weight": 1},
                            {"source": "model.Vocals", "weight": weight},
                        ],
                        "algorithm": "avg_wave",
                        "output_stem": "Vocals",
                        "save": False,
                    }],
                }
                with patch.dict("sys.modules", {"pymss": pymss_module, "pymss.graph": graph_module}):
                    with self.assertRaisesRegex(RuntimeError, "finite and greater than zero"):
                        _apply_simple_ensembles(
                            dag,
                            definition,
                            input_path="D:/Audio/song.wav",
                            output_format="wav",
                        )

    def test_intermediate_outputs_follow_explicit_save_links(self) -> None:
        definition = {
            "version": 1,
            "save_intermediate": False,
            "steps": [
                {"id": "first", "input": "input", "save": {"vocals": "Default", "music": "Default"}},
                {"id": "second", "input": "first.vocals", "save": {"clean": "Default"}},
            ],
        }
        runtime = _prepare_simple_runtime_definition(definition)
        self.assertEqual(runtime["steps"][0]["save"], {"vocals": "Default", "music": "Default"})
        self.assertNotIn("save_intermediate", runtime)
        self.assertEqual(definition["steps"][0]["save"]["vocals"], "Default")

    def test_simple_filename_template_renders_tokens_and_extension(self) -> None:
        self.assertEqual(
            _render_simple_filename(
                "%filename%_%stem%_%model%.wav",
                input_path="D:/Audio/song.mp3",
                stem="vocals",
                model="model.pth",
                step_id="split",
                index=1,
                output_format="flac",
            ),
            "song_vocals_model.flac",
        )
        self.assertEqual(
            _render_simple_filename(
                "%filename%_%stem%_%model%",
                input_path="D:/Audio/小蓝背心 - 灯火通明.mp3",
                stem="Instrumental",
                model="melband_roformer_instvox_duality_v2.ckpt",
                step_id="step1",
                index=1,
                output_format="wav",
            ),
            "小蓝背心 - 灯火通明_Instrumental_melband_roformer_instvox_duality_v2.wav",
        )

    def test_simple_output_paths_restore_unicode_names_after_graph_sanitizing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            generated = output_dir / "pymss_studio_0001.wav"
            generated.write_bytes(b"audio")
            finalized = _finalize_simple_output_paths(
                [str(generated)],
                [{"stem": "Instrumental", "filename": "小蓝背心 - 灯火通明_Instrumental_model.wav"}],
                output_dir,
            )
            self.assertEqual(finalized, [str(output_dir / "小蓝背心 - 灯火通明_Instrumental_model.wav")])
            self.assertTrue(Path(finalized[0]).is_file())
            self.assertFalse(generated.exists())

    def test_output_stem_matches_single_separation_for_prefixed_filename(self) -> None:
        self.assertEqual(
            _workflow_output_stem("D:/results/song/song_vocals.wav", "D:/Audio/song.wav"),
            "vocals",
        )

    def test_output_stem_keeps_unprefixed_filename(self) -> None:
        self.assertEqual(
            _workflow_output_stem("D:/results/vocals.wav", "D:/Audio/song.wav"),
            "vocals",
        )

    def test_output_stem_handles_windows_separators(self) -> None:
        self.assertEqual(
            _workflow_output_stem(r"D:\\results\\song\\song_vocals.wav", r"D:\\Audio\\song.wav"),
            "vocals",
        )

    def test_output_stem_supports_graphs_without_primary_input(self) -> None:
        self.assertEqual(_workflow_output_stem("D:/results/custom_mix.wav"), "custom_mix")


if __name__ == "__main__":
    unittest.main()
