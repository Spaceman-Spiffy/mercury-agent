"""Fork guard: an externally managed checkout booted from its in-tree venv keeps that venv.

The stamp's ``updateMechanism: external`` says PM does not own this install's dependencies.
PM still commits a generation whenever a sync runs, holding only what PM knows to install, and
selecting it at the next cold start drops every runtime installed into the in-tree venv by hand.
"""
import json
import os
import sys

import pytest


@pytest.fixture
def install(tmp_path, monkeypatch):
    """A checkout with an in-tree venv and a generation PM committed for it."""
    from pm.environments import install_state_dir, runtime_facts_path, site_packages

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    generation = install_state_dir(repo) / "environments" / "generation" / "venv"
    generation.mkdir(parents=True)
    # pyvenv.cfg first: the layout keys its site-packages path off the recorded version.
    (generation / "pyvenv.cfg").write_text("version = 3.11")
    site_packages(generation).mkdir(parents=True)
    runtime_facts_path(repo).write_text(json.dumps({"packages": {"venv": {"environment": str(generation)}}}))

    def in_tree_venv(name="venv"):
        venv = repo / name
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("version = 3.11")
        return venv

    def stamp(text):
        (repo / "install-stamp.json").write_text(text)

    def boot_from(prefix, base=None):
        monkeypatch.setattr(sys, "prefix", str(prefix))
        monkeypatch.setattr(sys, "base_prefix", str(base or tmp_path / "base-python"))

    return repo, generation.resolve(), in_tree_venv, stamp, boot_from


EXTERNAL = json.dumps({"updateMechanism": "external"})


@pytest.mark.parametrize("layout", ["venv", ".venv"])
def test_external_checkout_on_its_in_tree_venv_ignores_the_committed_generation(install, layout):
    from pm.environments import committed_venv, selected_venv

    repo, generation, in_tree_venv, stamp, boot_from = install
    stamp(EXTERNAL)
    boot_from(in_tree_venv(layout))

    assert committed_venv(repo) is None
    # PM's own bookkeeping still reads the record: a sync compares against what it committed.
    assert selected_venv(repo) == generation


def test_boot_keeps_the_in_tree_venv_packages(install, monkeypatch):
    from pm.environments import activate_dependencies

    repo, _generation, in_tree_venv, stamp, boot_from = install
    stamp(EXTERNAL)
    boot_from(in_tree_venv())
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("PYTHONPATH", "kept")
    monkeypatch.setenv("VIRTUAL_ENV", "kept")
    before = list(sys.path)

    activate_dependencies(repo)

    assert sys.path == before
    assert os.environ["PYTHONPATH"] == "kept"
    assert os.environ["VIRTUAL_ENV"] == "kept"


def test_cron_worker_pins_the_tree_only(install):
    from cron.scheduler_worker_env import _committed_dependency_site_packages

    repo, _generation, in_tree_venv, stamp, boot_from = install
    stamp(EXTERNAL)
    boot_from(in_tree_venv())

    assert _committed_dependency_site_packages(repo) is None


@pytest.mark.parametrize("stamp_text", [
    json.dumps({"updateMechanism": "self"}),
    json.dumps({"updateMechanism": None}),
    json.dumps(["external"]),
    "not json",
    None,
])
def test_only_an_external_stamp_qualifies(install, stamp_text):
    from pm.environments import committed_venv

    repo, generation, in_tree_venv, stamp, boot_from = install
    if stamp_text is not None:
        stamp(stamp_text)
    boot_from(in_tree_venv())

    assert committed_venv(repo) == generation


def test_another_venv_still_selects_the_generation(install, tmp_path):
    from pm.environments import committed_venv

    repo, generation, in_tree_venv, stamp, boot_from = install
    stamp(EXTERNAL)
    in_tree_venv()
    boot_from(tmp_path / "some-other-venv")

    assert committed_venv(repo) == generation


def test_store_python_still_selects_the_generation(install, tmp_path):
    """Not a venv interpreter: it has no packages of its own, so it needs the committed generation."""
    from pm.environments import committed_venv

    repo, generation, in_tree_venv, stamp, boot_from = install
    stamp(EXTERNAL)
    in_tree_venv()
    boot_from(tmp_path / "store-python", base=tmp_path / "store-python")

    assert committed_venv(repo) == generation
