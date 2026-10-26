from cli import main


def test_cli_build_and_check(repo, capsys):
    repo.add_skill("dev", "foo")
    assert main(["--root", str(repo.root), "build"]) == 0
    assert main(["--root", str(repo.root), "check"]) == 0
    assert "0 個錯誤" in capsys.readouterr().out


def test_cli_check_fails_on_error(repo, capsys):
    repo.add_skill("dev", "foo", frontmatter={"name": "other", "description": "測試用 skill，" + "說明" * 30})
    main(["--root", str(repo.root), "build"])
    assert main(["--root", str(repo.root), "check"]) == 1
    assert "ERROR plugins/dev/skills/foo" in capsys.readouterr().out


def test_cli_catalog_error(repo, capsys):
    (repo.root / "plugins" / "ghost").mkdir(parents=True)
    assert main(["--root", str(repo.root), "build"]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_cli_warnings_do_not_fail(repo, capsys):
    repo.add_skill("dev", "foo", frontmatter={"name": "foo", "description": "短"})
    main(["--root", str(repo.root), "build"])
    assert main(["--root", str(repo.root), "check"]) == 0
    assert "WARN" in capsys.readouterr().out
