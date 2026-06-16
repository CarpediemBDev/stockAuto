import os

import pytest

import seed_init


def test_seed_init_defaults_to_local_profile():
    args = seed_init.parse_args([])

    assert args.profile == "local"


def test_seed_init_blocks_prod_before_changing_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")

    with pytest.raises(RuntimeError, match="prod 환경"):
        seed_init.run_seed("prod")

    assert os.environ["APP_ENV"] == "local"
