"""ストリームの見張り（F-03 安定化）。

LLM・A2A呼び出しはネットワーク断や過負荷で「無言のまま固まる」ことがあり、
固まるとSSEストリームごと止まってUIは永遠に「かんがえている…」になる。
guard_silence はイベント列に沈黙タイムアウトを付ける：

- 見張るのは合計時間ではなく「イベント間の沈黙」。働いているAgentは
  イベントを出し続けるので、時間のかかる正常な仕事（多段パイプライン等）は
  妨げず、応答が途絶えたときだけ TimeoutError で素早く失敗させる
- 固まるより明示的に落とす方針：TimeoutError は呼び出し側（server.py）が
  受け、UIにエラーイベントとして知らせる

google-adk に依存しない純asyncioの部品（tests/ の隔離実行で検証できる）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TypeVar

T = TypeVar("T")


async def guard_silence(events: AsyncIterator[T], timeout: float) -> AsyncIterator[T]:
    """イベントが timeout 秒途絶えたら TimeoutError を送出する見張り付きで流す。

    Args:
        events: 見張り対象の非同期イベント列（例：runner.run_async(...)）。
        timeout: 許容する沈黙の秒数。0以下なら見張りなし（そのまま流す）。

    Raises:
        TimeoutError: 次のイベントが timeout 秒以内に来なかった。
    """
    if timeout <= 0:
        async for event in events:
            yield event
        return
    iterator = aiter(events)
    while True:
        try:
            event = await asyncio.wait_for(anext(iterator), timeout)
        except StopAsyncIteration:
            return
        yield event
