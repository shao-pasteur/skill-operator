"""Command-line entry point: uv run python scripts/cli.py <command>."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skillops.build import check_generated, generated_files, write_generated  # noqa: E402
from skillops.catalog import CatalogError, load_catalog  # noqa: E402
from skillops.package import package_skills  # noqa: E402
from skillops.release_notes import (  # noqa: E402
    changed_skill_names,
    git_changed_paths,
    render_release_notes,
)
from skillops.scaffold import ScaffoldError, import_skill, new_skill  # noqa: E402
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


def unstaged_paths(root: Path, paths: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", *paths],
        capture_output=True, text=True, check=True,
    )
    # Column 2 is the worktree state; "??" marks untracked files.
    return sorted(line[3:] for line in result.stdout.splitlines() if line[1] != " ")


def cmd_precommit(args: argparse.Namespace) -> int:
    removed = write_generated(load_catalog(args.root))
    catalog = load_catalog(args.root)
    pending = unstaged_paths(args.root, sorted(set(generated_files(catalog)) | set(removed)))
    if pending:
        print("產生檔有變動但還沒加入這次 commit，請執行：")
        print("  git add " + " ".join(pending))
        return 1
    return cmd_check(args)


def cmd_package(args: argparse.Namespace) -> int:
    out_dir = args.out if args.out.is_absolute() else args.root / args.out
    for path in package_skills(load_catalog(args.root), out_dir):
        print(path)
    return 0


def cmd_release_notes(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.root)
    paths = git_changed_paths(args.root, args.base, args.head)
    changed = None if paths is None else changed_skill_names(catalog, paths)
    print(render_release_notes(catalog, changed), end="")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    print(new_skill(args.root, args.category, args.name))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    dest = import_skill(args.root, args.src, args.category)
    print(f"已複製到 {dest}")
    rel = dest.relative_to(args.root).as_posix() + "/"
    issues = [i for i in validate_catalog(load_catalog(args.root)) if i.path.startswith(rel)]
    return print_issues(issues)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillops", description="skill-operator 的管理工具")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repo 根目錄")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="產生所有 manifest 與 README 目錄").set_defaults(func=cmd_build)
    sub.add_parser("check", help="驗證 skill 與產生檔").set_defaults(func=cmd_check)
    package = sub.add_parser("package", help="打包網頁版 zip")
    package.add_argument("--out", type=Path, default=Path("dist"), help="輸出資料夾（相對於 repo 根目錄）")
    package.set_defaults(func=cmd_package)
    notes = sub.add_parser("release-notes", help="產生 latest Release 的說明")
    notes.add_argument("--base", default=None, help="上一次 push 的 commit；省略代表全部視為有變動")
    notes.add_argument("--head", default="HEAD")
    notes.set_defaults(func=cmd_release_notes)
    sub.add_parser("precommit", help="pre-commit hook：build、確認產生檔已加入 commit、再 check").set_defaults(
        func=cmd_precommit
    )
    new = sub.add_parser("new", help="從樣板建立新 skill")
    new.add_argument("--category", required=True)
    new.add_argument("--name", required=True)
    new.set_defaults(func=cmd_new)
    imp = sub.add_parser("import", help="把既有的 skill 資料夾複製進 repo 並驗證")
    imp.add_argument("--src", type=Path, required=True)
    imp.add_argument("--category", required=True)
    imp.set_defaults(func=cmd_import)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CatalogError, ScaffoldError) as e:
        print(f"ERROR {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
