/**
 * fullstack成果物の「起動キット」（要件 F-04 出荷基準・v2.11）。
 *
 * 成果物を受け取るのはコマンドを使わない人なので、
 * `uvicorn main:app --port 8001` は手順として成立しない。
 * main.py と同じフォルダに置いてダブルクリックするだけで
 * APIが起動するスクリプトを同梱する（main.py 側は `python main.py` で
 * 起動できることを機械チェック済み＝shared/sandbox.py: check_selfstart）。
 *
 * 依存は必ず venv（.venv）に入れる。最近のPython（PEP 668）は
 * システム領域への `pip install` を `externally-managed-environment` で
 * 拒否するため、venvを経由しないと初回起動でいきなり失敗する（実測で確認）。
 * 副次的に、利用者のPCのPython環境を汚さない利点もある。
 *
 * 「Pythonが入っていること」だけは越えられない前提なので、
 * 画面ではその前提を隠さず明示する（UIの案内文を参照）。
 */

/**
 * Windows: start.bat（ダブルクリックで起動）
 *
 * - chcp 65001: コマンドプロンプトの既定はShift-JISのため、
 *   UTF-8で保存したこのファイルの日本語が文字化けする。先頭で切り替える
 * - errorlevel: pythonが異常終了したときだけ原因を案内する
 *   （正常に停止したとき＝Ctrl+Cにも失敗と出さない）
 * - 改行はCRLF（Windowsのbatはこれを期待する）
 */
export const START_BAT = [
  "@echo off",
  "chcp 65001 >nul",
  'cd /d "%~dp0"',
  "echo APIサーバーを準備しています（初回だけ少し時間がかかります）...",
  "",
  "set PY=",
  "python -m venv .venv >nul 2>&1",
  "REM venvが作れても pip が動くとは限らない。動くかどうかで判定する",
  ".venv\\Scripts\\python.exe -m pip --version >nul 2>&1 && set PY=.venv\\Scripts\\python.exe",
  'if not defined PY (',
  "  python -m pip --version >nul 2>&1 && set PY=python",
  ")",
  'if not defined PY (',
  "  echo.",
  "  echo Pythonが見つかりませんでした。",
  "  echo python.org からPythonをインストールし、もう一度お試しください。",
  "  pause",
  "  exit /b 1",
  ")",
  "",
  "%PY% -m pip install --quiet --disable-pip-version-check fastapi uvicorn",
  "if errorlevel 1 (",
  "  echo.",
  "  echo 必要な部品（fastapi / uvicorn）を入れられませんでした。",
  "  pause",
  "  exit /b 1",
  ")",
  "",
  "echo APIサーバーを起動します。この黒い画面は閉じないでください。",
  "%PY% main.py",
  "if errorlevel 1 (",
  "  echo.",
  "  echo 起動に失敗しました。main.py が同じフォルダにあるか確認してください。",
  ")",
  "pause",
].join("\r\n");

/**
 * macOS / Linux: start.command（ダブルクリックで起動）
 *
 * 初回のみ実行許可が要る（右クリック→開く）。この前提はUIで明示している。
 * Pythonが無いときは黙って落ちず、何をすればよいかを表示する。
 */
export const START_COMMAND = [
  "#!/bin/bash",
  'cd "$(dirname "$0")"',
  "if ! command -v python3 >/dev/null 2>&1; then",
  '  echo "Python3 が見つかりません。python.org からインストールしてください。"',
  '  read -p "Enterキーで閉じます"',
  "  exit 1",
  "fi",
  'echo "APIサーバーを準備しています（初回だけ少し時間がかかります）..."',
  "",
  "# venvが作れても pip が入っていないことがある（Debian系で python3-venv 未導入）。",
  "# 「作れたか」ではなく「pipが動くか」で判定する（実測でこの穴に落ちた）",
  "PY=''",
  "python3 -m venv .venv >/dev/null 2>&1",
  "if .venv/bin/python -m pip --version >/dev/null 2>&1; then",
  "  PY='.venv/bin/python'",
  "elif python3 -m pip --version >/dev/null 2>&1; then",
  "  PY='python3'  # venvが使えない環境はシステムのpipに頼る",
  "fi",
  'if [ -z "$PY" ]; then',
  '  echo "Pythonの部品（pip / venv）が足りません。python.org のPythonを入れ直すと解決します。"',
  '  read -p "Enterキーで閉じます"',
  "  exit 1",
  "fi",
  "",
  "# 素直に入らなければ、PEP 668（externally-managed-environment）を許可して再試行する",
  'if ! $PY -m pip install --quiet --disable-pip-version-check fastapi uvicorn 2>/dev/null; then',
  '  if ! $PY -m pip install --quiet --disable-pip-version-check --user --break-system-packages fastapi uvicorn; then',
  '    echo "必要な部品（fastapi / uvicorn）を入れられませんでした。"',
  '    read -p "Enterキーで閉じます"',
  "    exit 1",
  "  fi",
  "fi",
  "",
  'echo "APIサーバーを起動します。このウィンドウは閉じないでください。"',
  '$PY main.py',
].join("\n");
