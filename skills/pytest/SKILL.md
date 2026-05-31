---
name: pytest
description: pytestでテストを書く一般指針とFastAPI TestClientの使い方。テスト全般で再利用可能。tester が利用。
metadata:
  layer: verification
  reusable_for: [api, script, any-python]
---

# pytest テスト指針（テスト全般で再利用）

## 一般原則
- テスト関数は `test_` で始める。1テスト1意図。
- Arrange-Act-Assert の順で書く。
- 実装に存在しない機能はテストしない（設計の妄想を検証しない）。

## FastAPI のテスト（TestClient）
- `from fastapi.testclient import TestClient` / `client = TestClient(app)`。
- `from main import app` を前提に書く（生成物は main.py / テストは test_main.py）。
- 実行コマンドは `pytest test_main.py`（main.py を直接 pytest に渡さない）。

## CRUD のライフサイクル検証（推奨パターン）
作成→一覧→単体取得→更新→削除→削除後404、を1本の流れで検証する：
- create: status 201、返り値に id がある
- list: 200、作成したものが含まれる
- get: 200、内容一致
- update: 200、変更が反映
- delete: 204
- get(削除後): 404

## 出力形式
- test_code は生のPythonのみ（コードフェンスで囲まない）。
- how_to_run と summary を埋める。
