import os
import zipfile

from skillops.catalog import load_catalog
from skillops.package import package_skills


def test_only_web_skills_packaged(repo, tmp_path):
    repo.add_skill("dev", "foo")
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "x", "metadata": {"web": "false"}})
    out = package_skills(load_catalog(repo.root), tmp_path / "dist")
    assert [p.name for p in out] == ["foo.zip"]


def test_zip_layout(repo, tmp_path):
    repo.add_skill("dev", "foo", files={"references/a.md": "a"})
    [z] = package_skills(load_catalog(repo.root), tmp_path / "dist")
    assert sorted(zipfile.ZipFile(z).namelist()) == ["foo/SKILL.md", "foo/references/a.md"]


def test_zip_excludes_junk_and_keeps_exec_bit(repo, tmp_path):
    d = repo.add_skill(
        "dev", "foo",
        frontmatter={"name": "foo", "description": "x", "metadata": {"web": "true"}},
        files={"scripts/run.sh": "echo\n", "scripts/__pycache__/x.pyc": "", ".DS_Store": "", "scripts/y.pyc": ""},
    )
    (d / "scripts/run.sh").chmod(0o755)
    [z] = package_skills(load_catalog(repo.root), tmp_path / "dist")
    zf = zipfile.ZipFile(z)
    assert sorted(zf.namelist()) == ["foo/SKILL.md", "foo/scripts/run.sh"]
    assert (zf.getinfo("foo/scripts/run.sh").external_attr >> 16) & 0o111
    assert not (zf.getinfo("foo/SKILL.md").external_attr >> 16) & 0o111


def test_zip_is_deterministic(repo, tmp_path):
    d = repo.add_skill("dev", "foo", files={"references/a.md": "a"})
    [z1] = package_skills(load_catalog(repo.root), tmp_path / "d1")
    os.utime(d / "references/a.md", (1_000_000_000, 1_000_000_000))
    [z2] = package_skills(load_catalog(repo.root), tmp_path / "d2")
    assert z1.read_bytes() == z2.read_bytes()


def test_stale_zips_removed(repo, tmp_path):
    out = tmp_path / "dist"
    out.mkdir()
    (out / "old.zip").write_bytes(b"x")
    repo.add_skill("dev", "foo")
    package_skills(load_catalog(repo.root), out)
    assert not (out / "old.zip").exists()
    assert (out / "foo.zip").exists()
