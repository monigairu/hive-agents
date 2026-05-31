---
name: fastapi
description: FastAPIでCRUD APIを実装するための具体パターン（Pydanticモデル・ステータスコード・エラー処理）。APIタスクで implementer が利用。
metadata:
  layer: implementation
  reusable_for: [api]
---

# FastAPI 実装パターン

設計仕様(DesignSpec)から動くFastAPIコードを生成するときの定石。詳細な雛形は
references/crud-example.md を必要なら参照（load_skill_resource）。

## 基本構成（単一 main.py）
- `app = FastAPI()` を定義。
- リクエスト/レスポンスは Pydantic モデルで分離する：
  - `XxxCreate`（作成入力）/ `XxxUpdate`（部分更新・全項目 Optional）/ `Xxx`（レスポンス・id付き）
- 永続化はインメモリ `dict[int, Model]` ＋ 連番ID（MVP方針）。

## ステータスコード
- 作成：`status_code=201`
- 削除：`status_code=204` で本文なし（`return None`）
- 見つからない：`raise HTTPException(status_code=404, detail="...")`

## 更新（PUT）
- 既存を取得→無ければ404→`update.dict(exclude_unset=True)` で部分更新をマージ。

## 注意
- `if __name__ == "__main__":` での uvicorn 起動は任意（how_to_verify では `uvicorn main:app` を案内）。
- 設計の endpoints を全て実装する。
