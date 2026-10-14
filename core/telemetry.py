import json
import os
import time
from datetime import datetime
from contextlib import contextmanager

class LatencyProfiler:
    def __init__(self, log_path="logs/latency_metrics.jsonl"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.current_turn = {}

    @contextmanager
    def measure(self, phase_name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.current_turn[phase_name] = round(elapsed_ms, 2)

    def record_metric(self, key: str, value_ms: float):
        self.current_turn[key] = round(value_ms, 2)

    def flush(self, transcript: str = "", route: str = "") -> dict:
        if not self.current_turn:
            return {}

        payload = {
            "timestamp": datetime.now().isoformat(),
            "transcript": transcript,
            "route": route,
            "metrics": dict(self.current_turn)
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        flushed = self.current_turn
        self.current_turn = {}
        return flushed

profiler = LatencyProfiler()