"""Real Streamlit session helpers for the installed-update regression."""

from __future__ import annotations

import json
import socket
import subprocess
import time

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect


class LiveContractSession:
    """Exercise Streamlit's file watcher without restarting its Python process."""

    def __init__(self, python, checkout, env):
        app = checkout / "installation_probe.py"
        app.write_text(
            "import streamlit as st\n"
            "from pathlib import Path\n"
            "from meli_intelligence.ui import public_demo as demo\n"
            'result = {"contract": getattr(demo, "CONTRACT_VERSION", "1")}\n'
            'result["module"] = str(Path(demo.__file__).resolve())\n'
            "try:\n"
            "    m = demo.validate_bundle()\n"
            '    result["rows"] = {k:v["row_count"] for k,v in m["datasets"].items()}\n'
            "except ValueError as exc:\n"
            '    result["error"] = str(exc)\n'
            "st.json(result)\n"
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.log = (checkout.parent / "streamlit-session.log").open("w")
        self.process = subprocess.Popen(
            [
                str(python),
                "-I",
                "-m",
                "streamlit",
                "run",
                str(app),
                "--server.headless=true",
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--server.fileWatcherType=poll",
                "--server.runOnSave=true",
                "--browser.gatherUsageStats=false",
            ],
            cwd=checkout,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 90
        try:
            while True:
                try:
                    self.socket = connect(
                        f"ws://127.0.0.1:{port}/_stcore/stream",
                        subprotocols=["streamlit"],
                        open_timeout=2,
                        legacy=True,
                        ping_interval=None,
                        close_timeout=2,
                    )
                    break
                except OSError:
                    assert self.process.poll() is None, "Streamlit exited"
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
        except BaseException:
            self.close()
            raise

    def read(self, expected_contract, *, expected_rows=None, expected_error=None):
        message = BackMsg()
        message.rerun_script.query_string = ""
        self.socket.send(message.SerializeToString())
        deadline = time.monotonic() + 90
        observed = []
        while time.monotonic() < deadline:
            assert self.process.poll() is None, "Streamlit restarted or exited"
            try:
                raw = self.socket.recv(timeout=max(0.1, deadline - time.monotonic()))
            except TimeoutError:
                break
            forward = ForwardMsg()
            forward.ParseFromString(raw)
            if forward.WhichOneof("type") != "delta":
                continue
            element = forward.delta.new_element
            if element.WhichOneof("type") != "json":
                continue
            result = json.loads(element.json.body)
            observed.append(result)
            if (
                result.get("contract") == expected_contract
                and result.get("rows") == expected_rows
                and result.get("error") == expected_error
            ):
                return result
        raise AssertionError(f"Expected contract was not rendered: {observed}")

    def close(self):
        if hasattr(self, "socket"):
            self.socket.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        self.log.close()
