import asyncio

from backend.log_buffer import LogBuffer


def test_tc_run_5_replay_then_live_no_gaps_and_persists(tmp_path):
    async def scenario():
        logs = LogBuffer(tmp_path, capacity=3)
        for index in range(5):
            await logs.emit(1, "log", message=str(index))
        assert [item["id"] for item in logs.replay(1)] == [3, 4, 5]
        stream = logs.stream(1, after=3)
        assert (await anext(stream))["id"] == 4
        assert (await anext(stream))["id"] == 5
        pending = asyncio.create_task(anext(stream))
        await logs.emit(1, "phase", phase="nuclei")
        assert (await pending)["id"] == 6
        await logs.emit(1, "done", status="done")
        assert (await anext(stream))["type"] == "done"
        logs.flush()   # a restart happens after the old process has written its journal
        loaded = LogBuffer(tmp_path, capacity=3)
        assert loaded.replay(1) == logs.replay(1)
        reconnected = [item async for item in loaded.stream(1, after=5)]
        assert [item["id"] for item in reconnected] == [6, 7]
    asyncio.run(scenario())
