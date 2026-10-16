"""Bounded per-scan log replay, persisted independently of WebSocket clients."""

import asyncio
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json

from backend.db import utc_now
from backend.framework import load_module


class LogBuffer:
    def __init__(self, directory, capacity=2000):
        if capacity < 1:
            raise ValueError("Log capacity must be positive")
        self.directory, self.capacity = directory, capacity
        self.events, self.conditions, self.counts = {}, {}, {}
        # File writes happen on one background thread, in order: a slow disk (Docker bind mount) must not stall the
        # event loop that serves the API and the WebSocket. Replay always reads memory, the file is only the journal.
        self._io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bbasm-log")

    def flush(self):
        """Wait until everything emitted so far is on disk (restart reads, tests, shutdown)."""
        self._io.submit(lambda: None).result()

    def close(self):
        self._io.shutdown(wait=True)

    @staticmethod
    def _append(path, line):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)

    @staticmethod
    def _rewrite(path, items):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8", newline="\n")
        temp.replace(path)

    def _load(self, scan_id):
        if scan_id not in self.events:
            self.flush()   # a journal this process is still writing must be complete before it is read back
            items = deque(maxlen=self.capacity)
            path = self.directory / f"{int(scan_id)}.jsonl"
            if path.is_file():
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            item = json.loads(line)
                            if isinstance(item, dict) and isinstance(item.get("id"), int) and "type" in item:
                                items.append(item)
                        except ValueError:
                            continue  # Interrupted final append is safe to discard.
                # Repeated restarts must not allow the journal to grow without limit.
                path.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8", newline="\n")
            self.events[scan_id] = items
            self.conditions[scan_id] = asyncio.Condition()
            self.counts[scan_id] = 0
        return self.events[scan_id]

    async def emit(self, scan_id, event_type, **payload):
        events = self._load(scan_id)
        async with self.conditions[scan_id]:
            event = {**payload, "id": events[-1]["id"] + 1 if events else 1,
                     "type": event_type, "ts": utc_now()}
            if "message" in event:
                event["message"] = str(event["message"])[:4096]
            events.append(event)
            path = self.directory / f"{int(scan_id)}.jsonl"
            self.counts[scan_id] += 1
            if self.counts[scan_id] >= self.capacity:
                self._io.submit(self._rewrite, path, list(events))
                self.counts[scan_id] = 0
            else:
                self._io.submit(self._append, path, json.dumps(event) + "\n")
            self.conditions[scan_id].notify_all()
            return event

    def replay(self, scan_id, after=0):
        return [dict(item) for item in self._load(scan_id) if item["id"] > after]

    async def stream(self, scan_id, after=0):
        self._load(scan_id)
        while True:
            async with self.conditions[scan_id]:
                batch = self.replay(scan_id, after)
                if not batch:
                    if self.events[scan_id] and self.events[scan_id][-1]["type"] == "done":
                        return
                    await self.conditions[scan_id].wait()
                    continue
            for item in batch:
                after = item["id"]
                yield item
                if item["type"] == "done":
                    return


class ReconLogParser:
    def __init__(self, settings, config=None):
        self.dashboard = load_module(settings, "dashboard.py")
        self.config = config

    # What a skipped/failed line from the pinned scripts really means. The scripts say "not installed or no live hosts"
    # for ffuf even when ffuf was never going to run; the dashboard tells the three causes apart.
    def classify(self, clean):
        depth = getattr(self.config, "depth", None)
        if "ffuf not installed or no live hosts" in clean and (depth != "strong" or getattr(self.config, "skip_ffuf", False)):
            return "skipped_config", "[!] Dò thư mục (ffuf): bỏ qua theo mức quét — chỉ chạy ở Strong"
        if re.search(r"skipped \(BBASM\)|Skipping .* \(quick mode\)|skipped by BBASM", clean):
            return "skipped_config", clean.replace("(BBASM)", "theo cấu hình scan")
        if re.search(r"not installed|command not found|ProjectDiscovery httpx not found", clean, re.I):
            return "missing_tool", clean
        if re.search(r"timed out|timeout|exceeded", clean, re.I) and clean.startswith("[!]"):
            return "timeout", clean
        if re.search(r"No live hosts|No JS files|No parameterized|No subdomains|nothing to", clean, re.I):
            return "no_input", clean
        return None, clean

    def parse(self, line):
        clean = self.dashboard._ANSI_RE.sub("", line).strip()
        match = self.dashboard.PHASE_RE.search(clean)
        if match:
            return "phase", {"phase": self.dashboard.RECON_PHASE_BY_NUM.get(match[1], match[1]), "message": match[2]}
        tag, message = self.classify(clean)
        return "log", ({"message": message, "tag": tag} if tag else {"message": message})
