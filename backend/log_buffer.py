"""Bounded per-scan log replay, persisted independently of WebSocket clients."""

import asyncio
from collections import deque
import json

from backend.db import utc_now
from backend.framework import load_module


class LogBuffer:
    def __init__(self, directory, capacity=2000):
        if capacity < 1:
            raise ValueError("Log capacity must be positive")
        self.directory, self.capacity = directory, capacity
        self.events, self.conditions, self.counts = {}, {}, {}

    def _load(self, scan_id):
        if scan_id not in self.events:
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
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{int(scan_id)}.jsonl"
            self.counts[scan_id] += 1
            if self.counts[scan_id] >= self.capacity:
                temp = path.with_suffix(".tmp")
                temp.write_text("".join(json.dumps(item) + "\n" for item in events), encoding="utf-8", newline="\n")
                temp.replace(path)
                self.counts[scan_id] = 0
            else:
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(event) + "\n")
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
    def __init__(self, settings):
        self.dashboard = load_module(settings, "dashboard.py")

    def parse(self, line):
        clean = self.dashboard._ANSI_RE.sub("", line).strip()
        match = self.dashboard.PHASE_RE.search(clean)
        if match:
            return "phase", {"phase": self.dashboard.RECON_PHASE_BY_NUM.get(match[1], match[1]), "message": match[2]}
        return "log", {"message": clean}
