"""サンドボックス自己検証（要件 F-04）。

implementer が生成したコードと tester が生成したテストを、隔離した一時環境で
実際に pytest 実行し、pass/fail を決定論的に判定する＝「LLMが提案・サンドボックスが判定」
のオラクル。

ローカル開発では `uv run --no-project --with ...` でプロジェクトと隔離した
エフェメラル環境を作って実行する。Cloud Run化時は同じ VerificationResult を返す
AgentEngineSandboxCodeExecutor 版に差し替え可能（インターフェースを固定する意図）。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

# 生成コードに Hive の認証情報・設定（GOOGLE_* や APIキー等の環境変数）を晒さないため、
# サンドボックスへは実行に必要な最小限の環境変数だけを渡す（F-04/F-15 多層防御の一部）。
# 注意：これは環境変数の遮断であり、ファイルシステムの隔離ではない。
# 完全な隔離は Cloud Run 化（コンテナ境界）/ AgentEngineSandboxCodeExecutor への
# 差し替えで担保する。
_SANDBOX_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "UV_CACHE_DIR")


def _sandbox_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _SANDBOX_ENV_KEYS if k in os.environ}


class VerificationResult(BaseModel):
    passed: bool = Field(description="pytest が全て通ったか")
    returncode: int = Field(description="pytest プロセスの終了コード")
    output: str = Field(description="stdout/stderr（末尾を抜粋）")

    def headline(self) -> str:
        """結果を1行に要約する（メモリ記録・UI表示用）。失敗時は要因行を抜き出す。"""
        if self.passed:
            return "全テスト通過"
        for line in reversed(self.output.splitlines()):
            stripped = line.strip()
            if stripped.startswith(("E ", "FAILED", "assert")) or "Error" in stripped:
                return stripped[:200]
        return f"テスト失敗 (returncode={self.returncode})"


def verify_fastapi(code: str, test_code: str, timeout: int = 180) -> VerificationResult:
    """生成コード(main.py)とテスト(test_main.py)を隔離環境で実行して判定する。"""
    with tempfile.TemporaryDirectory(prefix="hive-verify-") as d:
        workdir = Path(d)
        (workdir / "main.py").write_text(code, encoding="utf-8")
        (workdir / "test_main.py").write_text(test_code, encoding="utf-8")
        cmd = [
            "uv", "run", "--no-project",
            "--with", "fastapi",
            "--with", "httpx",
            "--with", "pytest",
            "python", "-m", "pytest", "test_main.py", "-q",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_sandbox_env(),
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False, returncode=-1, output=f"TIMEOUT after {timeout}s"
            )
        output = f"{proc.stdout}\n{proc.stderr}".strip()
        return VerificationResult(
            passed=proc.returncode == 0,
            returncode=proc.returncode,
            output=output[-4000:],
        )
