#!/usr/bin/env python3
"""Structural checks for the skill. Standard library only; exits non-zero on any finding.

Checks: relative Markdown links and their anchors, reference-style links with no
definition, the SKILL.md frontmatter, and both plugin manifests agreeing on name and version.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "patterns-and-refactoring"
MAX_DESCRIPTION = 1024

INLINE_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)")
REFERENCE_LINK = re.compile(r"(?<![\]\\`])\[([A-Z][^\]\n]{2,})\](?![(\[:])")
DEFINITION = re.compile(r"^\[([^\]]+)\]:\s", re.MULTILINE)
FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
ALERT = re.compile(r"^!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)$")


def slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\]\([^)]*\)", "", heading.strip())
    text = re.sub(r"[`*_\[\]]", "", text).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set:
    body = FENCE.sub("", path.read_text(encoding="utf-8"))
    return {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+)$", body, re.MULTILINE)}


def check_links(path: Path) -> list:
    findings = []
    text = path.read_text(encoding="utf-8")
    prose = INLINE_CODE.sub("", FENCE.sub("", text))
    rel = path.relative_to(ROOT)

    for target in INLINE_LINK.findall(prose):
        if re.match(r"[a-z]+:", target):
            continue
        file_part, _, anchor = target.partition("#")
        resolved = (path.parent / file_part).resolve() if file_part else path
        if not resolved.exists():
            findings.append(f"{rel}: broken link -> {target}")
        elif anchor and resolved.is_file() and anchor not in anchors(resolved):
            findings.append(f"{rel}: broken anchor -> {target}")

    defined = {d.lower() for d in DEFINITION.findall(text)}
    for label in REFERENCE_LINK.findall(prose):
        if label.lower() not in defined and not ALERT.match(label):
            findings.append(f"{rel}: undefined reference link -> [{label}]")
    return findings


def check_frontmatter() -> list:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return ["SKILL.md: missing frontmatter"]
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    findings = []
    if fields.get("name") != SKILL_DIR.name:
        findings.append(f"SKILL.md: name does not match folder {SKILL_DIR.name}")
    description = fields.get("description", "")
    if not description.startswith("Use "):
        findings.append("SKILL.md: description must start with a trigger ('Use ...')")
    if len(description) > MAX_DESCRIPTION:
        findings.append(f"SKILL.md: description is {len(description)} chars, limit {MAX_DESCRIPTION}")
    return findings


def check_manifests() -> list:
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    entry = market["plugins"][0]
    return [
        f"manifests disagree on {key}: {plugin.get(key)} vs {entry.get(key)}"
        for key in ("name", "version", "homepage", "repository")
        if plugin.get(key) != entry.get(key)
    ]


def main() -> int:
    documents = [ROOT / "README.md", ROOT / "CLAUDE.md.snippet.md", *SKILL_DIR.rglob("*.md")]
    evals = ROOT / "evals"
    if evals.exists():
        documents.append(evals / "README.md")
    findings = [f for doc in documents for f in check_links(doc)]
    findings += check_frontmatter() + check_manifests()
    for finding in findings:
        print(finding)
    print(f"{len(documents)} documents checked, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
