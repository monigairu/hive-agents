---
name: security
description: 生成コードのセキュリティ監査チェックリストと深刻度の判定基準。security-reviewer が利用。
metadata:
  layer: verification
  reusable_for: [api, script, any-python]
---

# セキュリティ監査指針（FastAPI / Python 生成コード向け）

## チェック観点（必ず全観点を確認する）
- **インジェクション**：SQL（f-string・%・.format の埋め込み）、コマンド（os.system・shell=True）
- **任意コード実行**：eval / exec / pickle / yaml.load（SafeLoaderなし）
- **認可・認証**：他人のリソースをIDだけで操作できる（IDOR）、更新・削除に所有者チェックがない
- **SSRF**：ユーザー入力のURLをそのまま fetch / requests に渡す
- **秘密情報の露出**：APIキー・パスワードのハードコード、エラー応答への内部情報（スタックトレース・SQL）混入
- **弱い暗号**：MD5/SHA1でのパスワードハッシュ、自作トークン生成に random を使用
- **危険な設定**：debug=True、CORS全オリジン許可、TLS検証無効（verify=False）

## 深刻度の判定基準（3分類・必ずこのどれかを付ける）
- **critical**：外部から悪用可能で被害が直接出る（インジェクション・任意コード実行・本番キー露出・認可バイパス）→ マージ前に必ず修正
- **important**：悪用には条件が要るが修正すべき（弱いハッシュ・TLS無効・認証情報らしき定数）
- **minor**：意見が分かれる・環境依存（debug=True・CORS全開放・情報過多なエラー）

## レポートのルール
- すべての指摘に **file_path と line（提示された行番号）** を必ず付ける
- 問題がなければ `passed=true`・`findings=[]`・`summary="問題なし"` と素直に報告する。「念のため」で問題を発明しない
- **コードの修正はしない**。報告だけを行う（修正は実装担当に差し戻される）

## 前提（誤検知を防ぐ）
- 対象はデモ用の生成コード：インメモリ永続化・単一ファイル・認証なしのCRUD API は設計どおりであり、
  設計仕様に認証・認可の要件が無い場合、「認証が無い」こと自体は critical にしない（最大 minor）
- FastAPI/Pydantic のバリデーションが効いている入力は、それだけで脆弱と判定しない
