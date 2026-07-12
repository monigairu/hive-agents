"""Google認証＋週間利用制限（公開デプロイ用のコスト安全弁）。

Claudeの利用制限と同じ考え方を採る：
- **個人ごとの週間上限**（HIVE_WEEKLY_LIMIT・既定30回/週）で1ユーザの独占を防ぐ
- **全体の週間上限**（HIVE_GLOBAL_WEEKLY_LIMIT・既定300回/週）で
  アカウントを量産されても総コストが頭打ちになるようにする
- 管理者（HIVE_ADMIN_EMAILS）は無制限。審査員は各自のGoogleアカウントで
  個人枠を持つので、審査に必要な余裕は個人上限×審査員数だけ確保される

有効化は HIVE_OAUTH_CLIENT_ID をセットするだけ（未セット＝ローカル開発では
認証も制限も掛からず、従来どおり動く）。

カウンタは Firestore（(default)データベース・コレクション hive_quota）に
週単位のドキュメントで持つ。Firestoreが使えない環境ではプロセス内メモリに
フォールバックする（インスタンス再起動でリセットされるが、安全弁としては機能する）。
週の区切りは日本時間の月曜0時（ISO週番号）。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_CLIENT_ID = os.environ.get("HIVE_OAUTH_CLIENT_ID", "")
_LIMIT_USER = int(os.environ.get("HIVE_WEEKLY_LIMIT", "30"))
_LIMIT_GLOBAL = int(os.environ.get("HIVE_GLOBAL_WEEKLY_LIMIT", "300"))
_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("HIVE_ADMIN_EMAILS", "").split(",")
    if e.strip()
}

_JST = timezone(timedelta(hours=9))

# Firestore クライアント（遅延初期化）。使えない場合は False を入れて以後スキップ
_db = None
_mem: dict[str, int] = {}  # Firestore不通時のフォールバック
_lock = threading.Lock()


def auth_enabled() -> bool:
    """HIVE_OAUTH_CLIENT_ID がセットされていれば認証＋制限が有効。"""
    return bool(_CLIENT_ID)


def week_key(now: datetime | None = None) -> str:
    """日本時間のISO週キー（例: '2026-W28'）。月曜0時JSTでリセットされる。"""
    now = now or datetime.now(_JST)
    iso = now.astimezone(_JST).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@dataclass
class User:
    sub: str
    email: str
    name: str


def verify_token(token: str) -> User | None:
    """GoogleのIDトークンを検証してユーザ情報を返す。無効なら None。"""
    if not token:
        return None
    try:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token as ga_id_token

        info = ga_id_token.verify_oauth2_token(token, ga_requests.Request(), _CLIENT_ID)
        return User(
            sub=str(info["sub"]),
            email=str(info.get("email", "")).lower(),
            name=str(info.get("name", "") or info.get("email", "")),
        )
    except Exception as exc:  # noqa: BLE001 - 検証失敗はすべて「未ログイン」扱い
        logger.info("IDトークン検証に失敗: %s", exc)
        return None


@dataclass
class Verdict:
    allowed: bool
    message: str = ""
    remaining: int | None = None  # None = 無制限（管理者）
    limit: int | None = None


def _firestore():
    """Firestoreクライアントを遅延生成。使えない環境では None（メモリに切替）。"""
    global _db
    if _db is None:
        try:
            from google.cloud import firestore

            _db = firestore.Client()
        except Exception as exc:  # noqa: BLE001 - 未設定環境ではメモリで代替
            logger.warning("Firestore無効（メモリカウンタで代替）: %s", exc)
            _db = False
    return _db or None


def _disable_firestore(exc: Exception) -> None:
    """操作に失敗したら以後メモリカウンタに切り替える（再起動で復帰を再試行）。"""
    global _db
    logger.warning("Firestore操作に失敗（メモリカウンタに切替）: %s", exc)
    _db = False


def _read_count(doc_id: str) -> int:
    db = _firestore()
    if db is not None:
        try:
            snap = db.collection("hive_quota").document(doc_id).get()
            return int(snap.get("count") or 0) if snap.exists else 0
        except Exception as exc:  # noqa: BLE001
            _disable_firestore(exc)
    return _mem.get(doc_id, 0)


def _increment(doc_id: str, email: str = "") -> None:
    db = _firestore()
    if db is not None:
        try:
            from google.cloud.firestore_v1 import Increment

            payload: dict = {"count": Increment(1)}
            if email:
                payload["email"] = email
            db.collection("hive_quota").document(doc_id).set(payload, merge=True)
            return
        except Exception as exc:  # noqa: BLE001
            _disable_firestore(exc)
    with _lock:
        _mem[doc_id] = _mem.get(doc_id, 0) + 1


def consume(user: User) -> Verdict:
    """1発注ぶんの利用枠を消費する。上限超過なら拒否（カウントしない）。"""
    if user.email in _ADMIN_EMAILS:
        return Verdict(allowed=True, remaining=None, limit=None)

    wk = week_key()
    user_doc = f"{wk}_{user.sub}"
    global_doc = f"{wk}__global"
    try:
        used = _read_count(user_doc)
        if used >= _LIMIT_USER:
            return Verdict(
                allowed=False,
                message=(
                    f"今週の発注枠（{_LIMIT_USER}回）を使い切りました。"
                    "毎週月曜0時（日本時間）にリセットされます"
                ),
            )
        if _read_count(global_doc) >= _LIMIT_GLOBAL:
            return Verdict(
                allowed=False,
                message="サービス全体の今週の発注枠に達しました。来週また試してください",
            )
        _increment(user_doc, user.email)
        _increment(global_doc)
        return Verdict(
            allowed=True, remaining=_LIMIT_USER - used - 1, limit=_LIMIT_USER
        )
    except Exception as exc:  # noqa: BLE001 - カウンタ障害で発注を止めない（fail-open）
        logger.warning("クォータ確認に失敗（今回は許可）: %s", exc)
        return Verdict(allowed=True, remaining=None, limit=_LIMIT_USER)
