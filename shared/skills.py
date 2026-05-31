"""SkillToolset の汎用ローダー（要件 F-07）。

スキルは共有カタログ `skills/<name>/SKILL.md`（+ references/assets/scripts）に置き、
どのAgent・どのタスク種別からでも名前で選んで装着できる。

- 仕組みは完全汎用（このローダーは特定タスクに依存しない）
- スキルは合成可能な粒度（python-style / pytest はタスク横断で再利用）
- 新タスク種別の追加 = skills/ にSKILL.mdを足してAgentにマッピングするだけ（コード変更不要）

3層構造（ADK公式 SkillToolset）：
- L1 メタデータ（SKILL.md frontmatter）… 起動時に list_skills で全件提示
- L2 インストラクション（SKILL.md 本文）… Agentが必要時に load_skill
- L3 リソース（references/ 等）… L2が要求時に load_skill_resource
"""

from __future__ import annotations

from pathlib import Path

from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

# リポジトリ直下の共有スキルカタログ
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def skill_toolset(*names: str) -> SkillToolset:
    """指定した名前のスキルを共有カタログから読み込み、SkillToolset を返す。

    例: skill_toolset("python-style", "fastapi")
    """
    skills = [load_skill_from_dir(SKILLS_DIR / name) for name in names]
    return SkillToolset(skills=skills)
