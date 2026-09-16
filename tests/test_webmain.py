import io
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import webmain  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestStopFlag(unittest.TestCase):
    def test_stop_when_nothing_is_running(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = webmain.main(["--stop", "--port", str(_free_port())])
        self.assertEqual(code, 1)
        self.assertIn("not running", out.getvalue())

    def test_stop_shuts_down_a_real_server(self):
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "webmain.py"), "--port", str(port),
                 "--root", tmp, "--no-browser"],
                cwd=tmp,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 15
                while not webmain._is_running(port):
                    self.assertIsNone(server.poll(), "server exited during startup")
                    self.assertLess(time.monotonic(), deadline, "server never came up")
                    time.sleep(0.1)

                # A second launch on the same port must not start another server.
                again = io.StringIO()
                with redirect_stdout(again):
                    self.assertEqual(webmain.main(["--port", str(port), "--no-browser"]), 0)
                self.assertIn("already running", again.getvalue())

                with redirect_stdout(io.StringIO()):
                    self.assertEqual(webmain.main(["--stop", "--port", str(port)]), 0)

                self.assertEqual(server.wait(timeout=15), 0)
                self.assertFalse(webmain._is_running(port))
            finally:
                if server.poll() is None:
                    server.kill()
                server.wait()
                server.stdout.close()


if __name__ == "__main__":
    unittest.main()
