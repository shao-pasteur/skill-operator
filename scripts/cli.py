"""Command-line entry point: uv run python scripts/cli.py <command>."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skillops.build import check_generated, write_generated  # noqa: E402
from skillops.catalog import CatalogError, load_catalog  # noqa: E402
from skillops.validate import Issue, validate_catalog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def print_issues(issues: list[Issue]) -> int:
    for issue in sorted(issues, key=lambda i: (i.path, i.level)):
        label = "ERROR" if issue.level == "error" else "WARN "
        print(f"{label} {issue.path}: {issue.message}")
    n_errors = sum(i.level == "error" for i in issues)
    print(f"{n_errors} 個錯誤，{len(issues) - n_errors} 個警告")
    return 1 if n_errors else 0


def cmd_build(args: argparse.Namespace) -> int:
    for rel in write_generated(load_catalog(args.root)):
        print(f"更新 {rel}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.root)
    return print_issues(validate_catalog(catalog) + check_generated(catalog))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillops", description="skill-operator 的管理工具")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repo 根目錄")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="產生所有 manifest 與 README 目錄").set_defaults(func=cmd_build)
    sub.add_parser("check", help="驗證 skill 與產生檔").set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CatalogError as e:
        print(f"ERROR {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
