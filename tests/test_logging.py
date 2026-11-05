import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class LoggingTests(unittest.TestCase):
    def setUp(self):
        env = {
            "SRC_GITLAB": "https://source.example.com",
            "DST_GITLAB": "https://target.example.com",
            "SRC_TOKEN": "source-test-token",
            "DST_TOKEN": "target-test-token",
            "SRC_ROOT_GROUP": "source",
            "DST_ROOT_GROUP": "target",
            "TARGET_DEV_BRANCH_PREFIX": "NONE",
            "DRY_RUN": "true",
            "PUSH_EXISTING_PROJECTS": "true",
            "CONTINUE_ON_ERROR": "true",
        }
        spec = importlib.util.spec_from_file_location("mirror_test", ROOT / "mirror.py")
        self.mirror = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, env), patch("sys.argv", ["mirror.py"]):
            spec.loader.exec_module(self.mirror)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log_path = Path(self.temp.name) / "latest.log"
        self.mirror.LASTLOG_PATH = str(self.log_path)

    def test_green_headings_only_on_terminal_and_plain_saved_log(self):
        for tty in (True, False):
            with self.subTest(tty=tty):
                output = io.StringIO()
                output.isatty = lambda: tty
                with contextlib.redirect_stdout(output):
                    self.mirror.log("[MIRROR PROJECT #3]")
                    self.mirror.log("[OK] Result")
                heading = "\033[32m[MIRROR PROJECT #3]\033[0m" if tty else "[MIRROR PROJECT #3]"
                self.assertEqual(output.getvalue(), heading + "\n[OK] Result\n")
                self.assertNotIn("\033", self.log_path.read_text())

    def test_each_repository_activity_stays_after_its_own_heading(self):
        group = {"id": 1, "name": "Source", "full_path": "source"}
        projects = [
            {"name": name, "path": name, "path_with_namespace": "source/" + name}
            for name in ("first", "second")
        ]
        for mode in ("existing", "new", "skipped", "failed"):
            with self.subTest(mode=mode):
                self.mirror.MIRROR_PROJECT_COUNTER = 0
                self.mirror.PUSH_EXISTING_PROJECTS = mode != "skipped"
                output = io.StringIO()
                output.isatty = lambda: False
                with contextlib.ExitStack() as stack:
                    stack.enter_context(contextlib.redirect_stdout(output))
                    stack.enter_context(patch.object(self.mirror, "get_group_by_full_path", return_value={"id": 2}))
                    lookup = stack.enter_context(patch.object(self.mirror, "get_project_by_full_path", return_value=None if mode == "new" else {"id": 3}))
                    if mode == "failed":
                        lookup.side_effect = RuntimeError("lookup unavailable")
                    stack.enter_context(patch.object(self.mirror, "list_projects", return_value=projects))
                    stack.enter_context(patch.object(self.mirror, "list_subgroups", return_value=[]))
                    stack.enter_context(patch.object(self.mirror, "ls_remote_refs", return_value={"refs/heads/main": "abc"}))
                    self.mirror.migrate_group_recursive(group)
                text = output.getvalue()
                blocks = text.split("[MIRROR PROJECT #")
                self.assertEqual(len(blocks), 3, text)
                self.assertNotIn("target/first", blocks[0])
                for number, name in enumerate(("first", "second"), start=1):
                    block = blocks[number]
                    self.assertTrue(block.startswith(str(number) + "]\n"))
                    self.assertNotIn("-" * 72, block)
                    self.assertIn("source/" + name if mode == "failed" else "target/" + name, block)
                    if mode == "failed":
                        self.assertIn("[ERROR]", block)
                    elif mode == "skipped":
                        self.assertIn("[SKIP PUSH EXISTING PROJECT]", block)
                    else:
                        self.assertIn("[DRY-RUN] Refs not yet mirrored", block)
                    other = "second" if name == "first" else "first"
                    self.assertNotIn("target/" + other, block)


if __name__ == "__main__":
    unittest.main()
