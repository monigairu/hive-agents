"""サンドボックス自己検証（要件 F-04）。

implementer が生成したコードと tester が生成したテストを、隔離した一時環境で
実際に pytest 実行し、pass/fail を決定論的に判定する＝「LLMが提案・サンドボックスが判定」
のオラクル。

ローカル開発では `uv run --no-project --with ...` でプロジェクトと隔離した
エフェメラル環境を作って実行する。Cloud Run化時は同じ VerificationResult を返す
AgentEngineSandboxCodeExecutor 版に差し替え可能（インターフェースを固定する意図）。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    passed: bool = Field(description="pytest が全て通ったか")
    returncode: int = Field(description="pytest プロセスの終了コード")
    output: str = Field(description="stdout/stderr（末尾を抜粋）")


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
