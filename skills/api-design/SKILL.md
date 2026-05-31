---
name: api-design
description: REST APIの設計指針。リソースモデリング、エンドポイント命名、CRUDの網羅性、エラー設計。designer が利用。
metadata:
  layer: design
  reusable_for: [api]
---

# API設計の指針

発注内容から REST API の設計仕様を起こすときの原則。

## リソースモデリング
- 「名詞（リソース）」を中心に設計する。動詞はHTTPメソッドで表す。
- 複数形のコレクション名を使う（`/tasks`, `/users`）。
- 1リソースの属性は最小限から始め、必須/任意を明確にする。

## エンドポイント命名（CRUDの網羅）
CRUD要求では必ず次の5つを過不足なく定義する：
- `POST /{resources}` … 作成（201 Created）
- `GET /{resources}` … 一覧取得（200）
- `GET /{resources}/{id}` … 単体取得（200 / 無ければ404）
- `PUT /{resources}/{id}` … 更新（200 / 無ければ404）
- `DELETE /{resources}/{id}` … 削除（204 No Content / 無ければ404）

## エラー設計
- 存在しないIDへのアクセスは 404 を返す方針を notes に明記する。
- バリデーションは Pydantic に任せる前提（422 は自動）。

## 出力（DesignSpec）の品質基準
- overview: 何を作るか1〜2文。
- endpoints: 上記を「メソッド パス 説明」の形式で漏れなく。
- file_structure: MVPは単一 `main.py` 完結を基本に。
- notes: 永続化方針（MVPはインメモリ）・データモデル・エラー方針を書く。
