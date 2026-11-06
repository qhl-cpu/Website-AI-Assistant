import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "sync_knowledge.py"
SPEC = importlib.util.spec_from_file_location("sync_knowledge", MODULE_PATH)
sync_knowledge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_knowledge)


class KnowledgeSyncTests(unittest.TestCase):
    def make_pipeline(self, root, *, fail_step=None, stale_step=None):
        root = root.resolve()
        outputs = [
            ("01_ingest_wordpress.py", "data/raw/wp_documents_raw.jsonl"),
            ("02_clean_documents.py", "data/processed/wp_documents_clean.jsonl"),
            ("03_chunk_documents.py", "data/processed/wp_chunks.jsonl"),
            ("04_embed_chunks.py", "data/processed/wp_chunks_embedded.jsonl"),
        ]
        (root / "scripts").mkdir()
        (root / "backend/scripts").mkdir(parents=True)
        for index, (name, output) in enumerate(outputs, start=1):
            code = (
                "from pathlib import Path\n"
                f"assert Path.cwd() == Path({str(root)!r})\n"
                f"Path('step-{index}').touch()\n"
            )
            if index == fail_step:
                code += "raise SystemExit(1)\n"
            elif index != stale_step:
                code += (
                    f"output = Path({output!r})\n"
                    "output.parent.mkdir(parents=True, exist_ok=True)\n"
                    "output.write_text('fresh data\\n')\n"
                )
            (root / "scripts" / name).write_text(code)
        (root / "backend/scripts/upload_chunks_to_qdrant.py").write_text(
            "from pathlib import Path\n"
            f"assert Path.cwd() == Path({str(root / 'backend')!r})\n"
            "assert Path('../data/processed/wp_chunks_embedded.jsonl').read_text() == 'fresh data\\n'\n"
            "Path('../uploaded').touch()\n"
        )

    def test_failed_chunking_does_not_embed_or_upload_old_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_pipeline(root, fail_step=3)
            old_chunks = root / "data/processed/wp_chunks.jsonl"
            old_chunks.parent.mkdir(parents=True)
            old_chunks.write_text("old chunks")

            with self.assertRaises(subprocess.CalledProcessError):
                sync_knowledge.run_pipeline(root, upload=True)

            self.assertTrue((root / "step-3").exists())
            self.assertFalse((root / "step-4").exists())
            self.assertFalse((root / "uploaded").exists())
            self.assertEqual("old chunks", old_chunks.read_text())

    def test_success_without_fresh_output_stops_before_next_step(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_pipeline(root, stale_step=1)
            old_raw = root / "data/raw/wp_documents_raw.jsonl"
            old_raw.parent.mkdir(parents=True)
            old_raw.write_text("old documents")

            with self.assertRaisesRegex(RuntimeError, "fresh, nonempty"):
                sync_knowledge.run_pipeline(root, upload=True)

            self.assertFalse((root / "step-2").exists())
            self.assertFalse((root / "uploaded").exists())

    def test_successful_pipeline_uses_correct_directories_and_uploads_fresh_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_pipeline(root)

            sync_knowledge.run_pipeline(root, upload=True)

            self.assertTrue((root / "uploaded").exists())

    def test_upload_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_pipeline(root)

            sync_knowledge.run_pipeline(root)

            self.assertTrue((root / "step-4").exists())
            self.assertFalse((root / "uploaded").exists())


if __name__ == "__main__":
    unittest.main()
