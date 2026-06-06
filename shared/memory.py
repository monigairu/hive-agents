"""ReasoningBank 風メモリ（要件 F-08 / F-09）。

「成功・失敗の両方から再利用可能な教訓を蒸留し、次の同種タスク開始時に検索して
注入する」自己改善ループの最小実装。retrieve →（タスクで利用）→ record → forget。

設計の要点:
- ストレージは JSON 1ファイル（既定 ``.hive/memory.json``、``HIVE_MEMORY_PATH`` で変更可）。
- 検索は依存ゼロのキーワード重なりスコア（埋め込み不要・決定論的・日本語は2-gram）。
- ``forget`` で TTL と件数上限による忘却を行い、reflection が誤りを固着させるのを防ぐ。
- Cloud Run 化時は ``ReasoningBank`` のインターフェースを保ったまま、保存先を
  Vertex AI Agent Engine Memory Bank に差し替え可能（``sandbox.py`` と同じ思想）。

参考: ReasoningBank (Google Research, arXiv 2509.25140)。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["success", "failure"]

_DEFAULT_PATH = Path(os.environ.get("HIVE_MEMORY_PATH", ".hive/memory.json"))
_CJK = r"぀-ヿ一-鿿"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tokens(text: str) -> set[str]:
    """検索用トークン集合。英数字は単語、日本語は2-gram（語境界がないため）。"""
    text = text.lower()
    words = re.findall(r"[a-z0-9]+", text)
    cjk = re.findall(rf"[{_CJK}]", text)
    bigrams = [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return set(words) | set(bigrams)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class MemoryItem(BaseModel):
    """1件の教訓。title は検索キー兼表示用、lesson が再利用可能な本文。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_type: str
    kind: Kind
    title: str
    lesson: str
    uses: int = 0
    created_at: datetime = Field(default_factory=_now)
    last_used_at: datetime = Field(default_factory=_now)


class ReasoningBank:
    """JSON ファイルを台帳にした最小メモリストア（プロセス間共有も可）。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _DEFAULT_PATH

    # --- 永続化 -----------------------------------------------------------
    def _load(self) -> list[MemoryItem]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").strip()
        return [MemoryItem.model_validate(d) for d in json.loads(raw)] if raw else []

    def _save(self, items: list[MemoryItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [it.model_dump(mode="json") for it in items]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- 公開API ----------------------------------------------------------
    def retrieve(self, query: str, task_type: str, k: int = 3) -> list[MemoryItem]:
        """同種タスクの教訓を関連度順に最大 k 件返し、利用実績を更新する。"""
        items = self._load()
        q = _tokens(query)
        scored = [
            (len(q & _tokens(f"{it.title} {it.lesson}")), it)
            for it in items
            if it.task_type == task_type
        ]
        scored = [(s, it) for s, it in scored if s > 0]
        scored.sort(key=lambda x: (x[0], x[1].uses, x[1].last_used_at), reverse=True)
        top = [it for _, it in scored[:k]]
        for it in top:
            it.uses += 1
            it.last_used_at = _now()
        if top:
            self._save(items)
        return top

    def record(self, task_type: str, kind: Kind, title: str, lesson: str) -> MemoryItem:
        """教訓を追記する。類似の既存項目があれば統合（上書き）して重複を防ぐ。"""
        items = self._load()
        key = _tokens(title)
        for it in items:
            if it.task_type == task_type and it.kind == kind and _jaccard(key, _tokens(it.title)) >= 0.6:
                it.lesson = lesson  # 最新の知見で上書き＝矛盾の解消
                it.uses += 1
                it.last_used_at = _now()
                self._save(items)
                return it
        item = MemoryItem(task_type=task_type, kind=kind, title=title, lesson=lesson, uses=1)
        items.append(item)
        self._save(items)
        return item

    def forget(self, *, max_items: int = 200, ttl_days: int = 90) -> int:
        """TTL 超過と件数上限で古い・使われない教訓を破棄し、削除件数を返す。"""
        items = self._load()
        cutoff = _now() - timedelta(days=ttl_days)
        kept = [it for it in items if it.last_used_at >= cutoff]
        if len(kept) > max_items:
            kept.sort(key=lambda it: (it.uses, it.last_used_at), reverse=True)
            kept = kept[:max_items]
        removed = len(items) - len(kept)
        if removed:
            self._save(kept)
        return removed


def render_memories(items: list[MemoryItem]) -> str:
    """検索した教訓を、タスク文の先頭に差し込むプロンプト断片へ整形する。"""
    if not items:
        return ""
    lines = ["[過去の教訓（同種タスクの成功・失敗から自動抽出）]"]
    lines += [f"{'✓' if it.kind == 'success' else '⚠'} {it.lesson}" for it in items]
    return "\n".join(lines) + "\n\n"
