import asyncio
from pathlib import Path
from unittest.mock import Mock

from backend.config import PROJECT_ROOT
from backend.db import Database
from backend.jobs.scope_resolver import ScopeResolver
from backend.models import ResolveRequest


def environment(settings, scope=None):
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    database = Database(settings.BBASM_DATA / "bbasm.db")
    database.migrate()
    resolver = ScopeResolver(settings, database, Mock())
    result = resolver.resolve(ResolveRequest(input="raw", scope=scope or ["example.com"]))
    return database, resolver, result


def write_output(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


class FakeEgress:
    def check(self, plan, command):
        pass  # Only used with in-memory FakeProcess; never permits real subprocesses.


class FakeProcess:
    def __init__(self, code=0, hold=False):
        self.pid = 12345
        self.code, self.killed = code, False
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(b"\x1b[36m[*] Phase 2: HTTP Probing\x1b[0m\n[+] parsed\n")
        self.finished = asyncio.Event()
        if not hold:
            self.stdout.feed_eof()
            self.finished.set()

    async def wait(self):
        await self.finished.wait()
        return self.code


async def stop_fake(process):
    process.killed = True
    if not process.stdout.at_eof():
        process.stdout.feed_eof()
    process.finished.set()


async def until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.001)
    await asyncio.wait_for(poll(), 5)
