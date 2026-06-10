"""決定論的セキュリティパターン検査（要件 F-15・第1層）。

security-reviewer Agent（LLM・第2層）が見落としても確実に拾う、コスト$0の土台。
既知の危険パターンを正規表現で機械的に検出する。

最終判定は merge_review() が両層の和集合で行い、
「LLMがOKと言ってもツールがNGならNG」を実現する。
critical が1件でもあれば不合格＝implementer に差し戻す（F-04のループに乗せる）。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# 深刻度（要件 F-15：レビュー出力フォーマット）
# critical  … マージ前に必ず直す（差し戻し対象）
# important … 直すべき（報告のみ・差し戻しはしない）
# minor     … 意見が分かれる・レビュアー判断（報告のみ）
_SEVERITY_ORDER = {"critical": 0, "important": 1, "minor": 2}


class SecurityFinding(BaseModel):
    """1件の指摘。すべての指摘にファイルパスと行番号を必須で付ける（F-15）。"""

    severity: str = Field(description='"critical" | "important" | "minor"')
    file_path: str = Field(default="main.py", description="該当ファイル")
    line: int = Field(description="該当行番号")
    issue: str = Field(description="何が問題か")
    recommendation: str = Field(default="", description="推奨する直し方")
    detected_by: str = Field(default="pattern", description='"pattern" | "llm"')


class SecurityReport(BaseModel):
    """監査の最終レポート（パターン層とLLM層のマージ結果）。"""

    passed: bool = Field(description="critical の指摘が無ければ true")
    findings: list[SecurityFinding] = Field(default_factory=list)
    summary: str = Field(default="")

    def criticals(self) -> list[SecurityFinding]:
        return [f for f in self.findings if f.severity == "critical"]

    def headline(self) -> str:
        """結果を1行に要約する（差し戻し理由・メモリ記録・UI表示用）。"""
        if self.passed:
            return "セキュリティ監査通過"
        top = self.criticals()[0]
        return f"{top.file_path}:{top.line} {top.issue}"[:200]

    def render(self, limit: int = 10) -> str:
        """implementer への差し戻しプロンプト用に指摘を整形する。"""
        lines = [
            f"- [{f.severity}] {f.file_path}:{f.line} {f.issue}"
            + (f" → 推奨: {f.recommendation}" if f.recommendation else "")
            for f in self.findings[:limit]
        ]
        return "\n".join(lines)


# 既知の危険パターン（FastAPI/Python の生成コード向け）。
# (正規表現, 深刻度, 問題, 推奨する直し方)
# 注意: 以下の eval / os.system 等はすべて「検出対象の文字列パターン」であり、
# このモジュールが実行するわけではない（スキャナ定義）。
_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    # --- 任意コード実行・コマンドインジェクション ---
    (re.compile(r"\beval\s*\("), "critical",
     "eval() の使用（任意コード実行）", "ast.literal_eval か明示的なパースに置き換える"),
    (re.compile(r"\bexec\s*\("), "critical",
     "exec() の使用（任意コード実行）", "動的コード実行を使わない設計にする"),
    (re.compile(r"os\.system\s*\("), "critical",
     "os.system() の使用（コマンドインジェクション）", "subprocess.run をリスト引数・shell=False で使う"),
    (re.compile(r"subprocess\.\w+\s*\(.*shell\s*=\s*True"), "critical",
     "subprocess の shell=True（コマンドインジェクション）", "shell=False とリスト引数にする"),
    (re.compile(r"pickle\.loads?\s*\("), "critical",
     "pickle の逆直列化（任意コード実行）", "json 等の安全な形式を使う"),
    # --- SQLインジェクション ---
    (re.compile(r"execute(?:many)?\s*\(\s*f[\"']"), "critical",
     "SQL文へのf-string埋め込み（SQLインジェクション）", "プレースホルダとパラメータバインドを使う"),
    (re.compile(r"execute(?:many)?\s*\(\s*[\"'][^\"']*[\"']\s*%"), "critical",
     "SQL文の%整形（SQLインジェクション）", "プレースホルダとパラメータバインドを使う"),
    (re.compile(r"execute(?:many)?\s*\(.*\.format\s*\("), "critical",
     "SQL文への .format() 埋め込み（SQLインジェクション）", "プレースホルダとパラメータバインドを使う"),
    # --- 秘密情報のハードコード ---
    (re.compile(r"sk_live_[0-9a-zA-Z]{8,}"), "critical",
     "Stripe本番キーのハードコード", "環境変数 / Secret Manager に移す"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "critical",
     "AWSアクセスキーのハードコード", "環境変数 / Secret Manager に移す"),
    (re.compile(r"ghp_[0-9a-zA-Z]{20,}"), "critical",
     "GitHubトークンのハードコード", "環境変数 / Secret Manager に移す"),
    (re.compile(r"(?i)\b(?:api_key|apikey|secret_key|password|auth_token)\s*=\s*[\"'][^\"']{8,}[\"']"),
     "important",
     "認証情報らしき文字列のハードコード", "環境変数から読み込む"),
    # --- 弱い暗号・危険な設定 ---
    (re.compile(r"hashlib\.(?:md5|sha1)\s*\("), "important",
     "弱いハッシュ関数（MD5/SHA1）", "パスワードは bcrypt/argon2、その他は sha256 以上を使う"),
    (re.compile(r"verify\s*=\s*False"), "important",
     "TLS証明書検証の無効化", "verify=True に戻す"),
    (re.compile(r"yaml\.load\s*\((?![^)]*SafeLoader)"), "important",
     "yaml.load の使用（任意オブジェクト生成）", "yaml.safe_load を使う"),
    (re.compile(r"\bdebug\s*=\s*True"), "minor",
     "debug=True（スタックトレース等の情報漏えい）", "本番では無効化する"),
    (re.compile(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']"), "minor",
     "CORSが全オリジン許可", "必要なオリジンに限定する"),
]


def scan_code(code: str, file_path: str = "main.py") -> list[SecurityFinding]:
    """コードを行単位で走査し、既知の危険パターンの指摘一覧を返す（第1層・$0）。"""
    findings: list[SecurityFinding] = []
    for lineno, line in enumerate(code.splitlines(), start=1):
        if line.strip().startswith("#"):
            continue
        for pattern, severity, issue, recommendation in _PATTERNS:
            if pattern.search(line):
                findings.append(
                    SecurityFinding(
                        severity=severity,
                        file_path=file_path,
                        line=lineno,
                        issue=issue,
                        recommendation=recommendation,
                    )
                )
    return findings


def merge_review(
    pattern_findings: list[SecurityFinding],
    llm_report: SecurityReport | None,
) -> SecurityReport:
    """パターン層とLLM層の指摘をマージして最終判定を出す。

    - passed は「critical が0件」でのみ true（LLMがOKでもパターンがNGならNG）
    - important / minor は報告に残すが差し戻し条件にはしない
    """
    findings = list(pattern_findings)
    if llm_report:
        findings += [
            f.model_copy(update={"detected_by": "llm"}) for f in llm_report.findings
        ]
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.line))
    counts = {
        sev: sum(1 for f in findings if f.severity == sev)
        for sev in ("critical", "important", "minor")
    }
    passed = counts["critical"] == 0
    if not findings:
        summary = "問題なし"
    else:
        summary = " / ".join(f"{sev} {n}件" for sev, n in counts.items() if n)
    return SecurityReport(passed=passed, findings=findings, summary=summary)
