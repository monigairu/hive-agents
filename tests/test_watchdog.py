"""shared/watchdog.py（沈黙タイムアウトの見張り）の単体テスト。"""

from __future__ import annotations

import asyncio

import pytest

from shared.watchdog import guard_silence


async def _emit(items, delay: float = 0):
    """テスト用のイベント列。delay を挟みながら items を順に流す。"""
    for item in items:
        if delay:
            await asyncio.sleep(delay)
        yield item


def test_passes_events_through():
    async def run():
        return [ev async for ev in guard_silence(_emit([1, 2, 3]), timeout=1.0)]

    assert asyncio.run(run()) == [1, 2, 3]


def test_raises_on_silence():
    """イベントが途絶えたら TimeoutError。それまでのイベントは届いている。"""

    async def stalled():
        yield 1
        await asyncio.sleep(10)  # 沈黙（見張りが落とすので実際には10秒待たない）
        yield 2

    async def run():
        received = []
        with pytest.raises(TimeoutError):
            async for ev in guard_silence(stalled(), timeout=0.05):
                received.append(ev)
        return received

    assert asyncio.run(run()) == [1]


def test_timeout_zero_disables_watchdog():
    async def run():
        return [ev async for ev in guard_silence(_emit([1, 2], delay=0.02), timeout=0)]

    assert asyncio.run(run()) == [1, 2]


def test_slow_but_steady_stream_is_not_killed():
    """見張るのは沈黙だけ：イベントが出続けていれば合計時間が長くても落とさない。"""

    async def run():
        events = guard_silence(_emit(list(range(5)), delay=0.03), timeout=0.1)
        return [ev async for ev in events]

    assert asyncio.run(run()) == [0, 1, 2, 3, 4]
