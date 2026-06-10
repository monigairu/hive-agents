"""shared/security_patterns.py（F-15 第1層・決定論的パターン検査）の単体テスト。"""

from __future__ import annotations

from shared.security_patterns import (
    SecurityFinding,
    SecurityReport,
    merge_review,
    scan_code,
)

CLEAN_FASTAPI = '''\
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
items: dict[int, dict] = {}


class Item(BaseModel):
    name: str


@app.post("/items", status_code=201)
def create(item: Item):
    item_id = len(items) + 1
    items[item_id] = item.model_dump()
    return {"id": item_id, **items[item_id]}
'''


def test_clean_code_has_no_findings():
    assert scan_code(CLEAN_FASTAPI) == []


def test_detects_eval_with_line_number():
    code = "x = 1\nresult = eval(user_input)\n"
    findings = scan_code(code)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].line == 2
    assert findings[0].file_path == "main.py"


def test_detects_os_system_and_shell_true():
    code = 'import os\nos.system(cmd)\nsubprocess.run(cmd, shell=True)\n'
    severities = [f.severity for f in scan_code(code)]
    assert severities == ["critical", "critical"]


def test_detects_hardcoded_stripe_key():
    code = 'STRIPE = "sk_live_abcdefgh12345678"\n'
    findings = scan_code(code)
    assert any("Stripe" in f.issue for f in findings)


def test_detects_sql_fstring_injection():
    code = 'cur.execute(f"SELECT * FROM users WHERE id = {uid}")\n'
    findings = scan_code(code)
    assert findings and findings[0].severity == "critical"
    assert "SQL" in findings[0].issue


def test_comment_lines_are_ignored():
    code = "# eval(user_input) は使わないこと\nx = 1\n"
    assert scan_code(code) == []


def test_important_and_minor_do_not_fail_the_review():
    code = 'h = hashlib.md5(data)\napp.run(debug=True)\n'
    report = merge_review(scan_code(code), None)
    assert report.passed  # critical なしなら合格（報告は残る）
    assert len(report.findings) == 2


def test_pattern_critical_overrides_llm_pass():
    """LLMが「問題なし」と言ってもパターン層がNGならNG。"""
    pattern = scan_code("result = eval(user_input)\n")
    llm = SecurityReport(passed=True, findings=[], summary="問題なし")
    report = merge_review(pattern, llm)
    assert not report.passed


def test_merge_combines_llm_findings_with_detected_by():
    llm = SecurityReport(
        passed=False,
        findings=[
            SecurityFinding(
                severity="critical", line=5, issue="認可チェック漏れ", recommendation="所有者を確認する"
            )
        ],
        summary="critical 1件",
    )
    report = merge_review([], llm)
    assert not report.passed
    assert report.findings[0].detected_by == "llm"


def test_headline_and_summary():
    report = merge_review(scan_code("result = eval(x)\n"), None)
    assert "main.py:1" in report.headline()
    assert "critical 1件" in report.summary
    clean = merge_review([], None)
    assert clean.passed
    assert clean.summary == "問題なし"
    assert clean.headline() == "セキュリティ監査通過"


def test_findings_sorted_by_severity_then_line():
    code = "app.run(debug=True)\nresult = eval(x)\n"
    report = merge_review(scan_code(code), None)
    assert [f.severity for f in report.findings] == ["critical", "minor"]
