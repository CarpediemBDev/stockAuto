from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_dockerfile_defaults_to_prod_profile():
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV APP_ENV=prod" in dockerfile
    assert "ENV PORT=8000" in dockerfile
    assert "--port ${PORT:-8000}" in dockerfile


def test_backend_prod_env_example_declares_runtime_profile():
    env_example = (REPO_ROOT / "backend" / ".env.prod.example").read_text(encoding="utf-8")

    assert "APP_ENV=prod" in env_example
    assert "PORT=8000" in env_example
