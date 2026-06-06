"""shared/memory.py（ReasoningBank）の単体テスト。"""

from __future__ import annotations

from datetime import timedelta

from shared.memory import MemoryItem, ReasoningBank, _now, render_memories


def _bank(tmp_path) -> ReasoningBank:
    return ReasoningBank(path=tmp_path / "memory.json")


def test_record_then_retrieve_roundtrip(tmp_path):
    bank = _bank(tmp_path)
    bank.record("api", "failure", "api 失敗: 422 が出る", "次回の注意: pydanticの必須項目を確認")

    hits = bank.retrieve("APIで422エラーが出る", "api")

    assert len(hits) == 1
    assert hits[0].kind == "failure"
    assert hits[0].uses == 2  # record(1) + retrieve(+1)


def test_retrieve_filters_by_task_type(tmp_path):
    bank = _bank(tmp_path)
    bank.record("api", "success", "api 成功: CRUD", "CRUDを一括実装")
    bank.record("lp", "success", "lp 成功: LP", "HTMLで実装")

    hits = bank.retrieve("CRUD API", "api")

    assert [h.task_type for h in hits] == ["api"]


def test_retrieve_ranks_by_relevance(tmp_path):
    bank = _bank(tmp_path)
    bank.record("api", "failure", "api 失敗: 認証エラー", "JWTの検証に注意")
    bank.record("api", "failure", "api 失敗: バリデーション", "必須フィールドに注意")

    hits = bank.retrieve("バリデーションでエラー", "api", k=1)

    assert "バリデーション" in hits[0].title


def test_record_consolidates_similar(tmp_path):
    bank = _bank(tmp_path)
    bank.record("api", "failure", "api 失敗: タイムアウト", "古い教訓")
    bank.record("api", "failure", "api 失敗: タイムアウト", "新しい教訓")

    items = bank._load()
    assert len(items) == 1  # 重複追加されない
    assert items[0].lesson == "新しい教訓"  # 最新で上書き
    assert items[0].uses == 2


def test_forget_drops_expired_and_caps(tmp_path):
    bank = _bank(tmp_path)
    fresh = MemoryItem(task_type="api", kind="success", title="新", lesson="新")
    stale = MemoryItem(
        task_type="api", kind="failure", title="古", lesson="古",
        last_used_at=_now() - timedelta(days=200),
    )
    bank._save([fresh, stale])

    removed = bank.forget(ttl_days=90)

    assert removed == 1
    assert [it.title for it in bank._load()] == ["新"]


def test_render_memories(tmp_path):
    assert render_memories([]) == ""
    item = MemoryItem(task_type="api", kind="failure", title="t", lesson="必須項目を確認")
    rendered = render_memories([item])
    assert "過去の教訓" in rendered
    assert "⚠ 必須項目を確認" in rendered
