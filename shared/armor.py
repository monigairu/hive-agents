"""Model Armor 実行時防御（要件 F-11・セマンティックFW）。

F-15（コード生成時の監査）とは別レイヤーの多層防御：
- 入口（プロンプト防御）：発注文がモデルに到達する前に、プロンプトインジェクション・
  ジェイルブレイク・悪性URLを検査し、検出したら実行そのものを止める
- 出口（出力保護）：納品物にクレジットカード番号・APIキー等の機密データが
  混ざっていないか最終検査する（報告のみ・納品は止めない）

設計原則：
- フェイルオープン：SDK未導入・API未有効化・権限不足の環境では検査をスキップして
  通常運転を続ける。セキュリティ機能の不調で本体を止めない（intakeと同じ思想）
- 判定はUIに開示する：ブロック・通過・スキップのいずれもSSEイベントで見せる

事前準備（1回だけ）: ./scripts/setup_model_armor.sh を実行してテンプレートを作る。
"""

from __future__ import annotations

import os
import threading

from pydantic import BaseModel, Field

# Model Armor はリージョナルAPI（globalエンドポイントは無い）。
# Vertex 側の GOOGLE_CLOUD_LOCATION=global とは独立に持つ
_LOCATION = os.environ.get("HIVE_ARMOR_LOCATION", "us-central1")
_TEMPLATE = os.environ.get("HIVE_ARMOR_TEMPLATE", "hive-guard")
_TIMEOUT = float(os.environ.get("HIVE_ARMOR_TIMEOUT", "10"))

# フィルタ名 → UI表示ラベル（Model Armor の filter_results のキーに対応）
_FILTER_LABELS = {
    "pi_and_jailbreak": "プロンプトインジェクション/ジェイルブレイク",
    "malicious_uris": "悪性URL",
    "rai": "有害コンテンツ",
    "sdp": "機密データ（PII・APIキー等）",
    "csam": "児童保護フィルタ",
}


class ArmorVerdict(BaseModel):
    """1回の検査の判定。checked=False はスキップ（環境未整備など）を表す。"""

    allowed: bool = Field(default=True, description="実行を続けてよいか")
    checked: bool = Field(default=False, description="実際にAPIで検査できたか")
    matched: list[str] = Field(default_factory=list, description="検出フィルタの表示ラベル")
    note: str = Field(default="", description="スキップ理由などの補足")


def armor_on() -> bool:
    """F-11 のオン/オフ（HIVE_ARMOR=0 で丸ごと無効化）。"""
    return os.environ.get("HIVE_ARMOR", "1") != "0"


# クライアントは1プロセス1個。生成失敗（SDK無し等）は理由ごと記憶して以後スキップ
_lock = threading.Lock()
_client = None
_disabled_reason: str | None = None


def _get_client():
    global _client, _disabled_reason
    with _lock:
        if _client is not None or _disabled_reason is not None:
            return _client
        try:
            from google.api_core.client_options import ClientOptions
            from google.cloud import modelarmor_v1

            _client = modelarmor_v1.ModelArmorClient(
                transport="rest",
                client_options=ClientOptions(
                    api_endpoint=f"modelarmor.{_LOCATION}.rep.googleapis.com"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - SDK未導入等はスキップ運転に倒す
            _disabled_reason = f"Model Armor無効（{type(exc).__name__}）"
        return _client


def _template_name() -> str:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    return f"projects/{project}/locations/{_LOCATION}/templates/{_TEMPLATE}"


def _state_name(value) -> str:
    """proto enum / 文字列のどちらでも比較できるよう名前に正規化する。"""
    return getattr(value, "name", None) or str(value)


def _parse(result) -> ArmorVerdict:
    """SanitizeResponse.sanitization_result を判定に変換する。"""
    blocked = _state_name(result.filter_match_state) == "MATCH_FOUND"
    matched: list[str] = []
    if blocked:
        for key, fr in dict(result.filter_results).items():
            # 各フィルタ結果は oneof。中のサブ結果の match_state を総当たりで見る
            hit = any(
                _state_name(getattr(getattr(fr, sub, None), "match_state", ""))
                == "MATCH_FOUND"
                for sub in (
                    "rai_filter_result",
                    "sdp_filter_result",
                    "pi_and_jailbreak_filter_result",
                    "malicious_uri_filter_result",
                    "csam_filter_filter_result",
                )
            )
            if hit:
                matched.append(_FILTER_LABELS.get(key, key))
        if not matched:
            matched.append("安全フィルタ")
    return ArmorVerdict(allowed=not blocked, checked=True, matched=matched)


def _sanitize(text: str, *, is_response: bool) -> ArmorVerdict:
    client = _get_client()
    if client is None:
        return ArmorVerdict(checked=False, note=_disabled_reason or "未初期化")
    from google.cloud import modelarmor_v1

    data = modelarmor_v1.DataItem(text=text)
    if is_response:
        request = modelarmor_v1.SanitizeModelResponseRequest(
            name=_template_name(), model_response_data=data
        )
        response = client.sanitize_model_response(request=request, timeout=_TIMEOUT)
    else:
        request = modelarmor_v1.SanitizeUserPromptRequest(
            name=_template_name(), user_prompt_data=data
        )
        response = client.sanitize_user_prompt(request=request, timeout=_TIMEOUT)
    return _parse(response.sanitization_result)


def sanitize_prompt(text: str) -> ArmorVerdict:
    """入口防御：発注文を検査する。ブロック時 allowed=False（実行を止める）。"""
    try:
        return _sanitize(text, is_response=False)
    except Exception as exc:  # noqa: BLE001 - API未有効化・権限不足はスキップに倒す
        return ArmorVerdict(checked=False, note=f"検査スキップ（{type(exc).__name__}）")


def sanitize_response(text: str) -> ArmorVerdict:
    """出口保護：納品物を検査する。検出しても報告のみ（納品は止めない）。"""
    try:
        return _sanitize(text, is_response=True)
    except Exception as exc:  # noqa: BLE001
        return ArmorVerdict(checked=False, note=f"検査スキップ（{type(exc).__name__}）")
