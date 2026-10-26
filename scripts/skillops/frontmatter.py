"""Parse the YAML frontmatter at the top of a SKILL.md file."""

import yaml


class FrontmatterError(ValueError):
    pass


def parse_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("SKILL.md 開頭必須是 '---' 的 frontmatter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FrontmatterError("找不到 frontmatter 結尾的 '---'") from None
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as e:
        raise FrontmatterError(f"frontmatter 不是合法的 YAML：{e}") from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter 必須是 key: value 形式的 mapping")
    return data, "\n".join(lines[end + 1:])
