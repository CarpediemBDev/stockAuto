import os
import sys

import run


def test_local_launcher_scopes_reload_and_keeps_current_python(monkeypatch):
    captured = {}

    monkeypatch.setattr(sys, "argv", ["run.py", "local"])
    monkeypatch.setattr(
        run.multiprocessing,
        "set_executable",
        lambda executable: captured.update(executable=executable),
    )
    monkeypatch.setattr(
        run.uvicorn,
        "run",
        lambda app, **options: captured.update(app=app, options=options),
    )

    run.main()

    expected_app_dir = os.path.join(
        os.path.dirname(os.path.abspath(run.__file__)),
        "app",
    )
    assert captured["executable"] == sys.executable
    assert captured["app"] == "app.main:app"
    assert captured["options"]["reload"] is False
    assert captured["options"]["reload_dirs"] is None
    assert captured["options"]["env_file"] == ".env.local"


def test_prod_launcher_disables_reload(monkeypatch):
    captured = {}

    monkeypatch.setattr(sys, "argv", ["run.py", "prod"])
    monkeypatch.setattr(run.multiprocessing, "set_executable", lambda _executable: None)
    monkeypatch.setattr(
        run.uvicorn,
        "run",
        lambda app, **options: captured.update(app=app, options=options),
    )

    run.main()

    assert captured["options"]["reload"] is False
    assert captured["options"]["reload_dirs"] is None
    assert captured["options"]["env_file"] == ".env.prod"
