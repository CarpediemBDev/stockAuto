#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors: list[str] = []

    backend_dockerfile = root / "backend" / "Dockerfile"
    backend_prod_env = root / "backend" / ".env.prod.example"
    frontend_local_env = root / "frontend" / ".env.local.example"
    frontend_dev_env = root / "frontend" / ".env.dev.example"
    frontend_prod_env = root / "frontend" / ".env.prod.example"
    next_config = root / "frontend" / "next.config.ts"

    require(backend_dockerfile.exists(), "backend/Dockerfile is missing", errors)
    if backend_dockerfile.exists():
        text = backend_dockerfile.read_text(encoding="utf-8")
        require("ENV APP_ENV=prod" in text, "backend Dockerfile must default APP_ENV=prod", errors)
        require("ENV PORT=" in text, "backend Dockerfile must define a default PORT", errors)
        require("${PORT:-" in text or "$PORT" in text, "backend Dockerfile must bind uvicorn to injected PORT", errors)

    require(backend_prod_env.exists(), "backend/.env.prod.example is missing", errors)
    if backend_prod_env.exists():
        text = backend_prod_env.read_text(encoding="utf-8")
        for key in ("APP_ENV=prod", "JWT_SECRET_KEY=", "REDIS_URL=", "ALLOWED_ORIGINS="):
            require(key in text, f"backend/.env.prod.example missing {key}", errors)

    for env_file in (frontend_local_env, frontend_dev_env, frontend_prod_env):
        require(env_file.exists(), f"{env_file.relative_to(root)} is missing", errors)
        if env_file.exists():
            text = env_file.read_text(encoding="utf-8")
            require("NEXT_PUBLIC_API_BASE=/api/v1" in text, f"{env_file.name} must keep same-origin API base", errors)
            require("BACKEND_API_ORIGIN=" in text, f"{env_file.name} missing BACKEND_API_ORIGIN", errors)
            require("NEXT_PUBLIC_APP_ENV=" in text, f"{env_file.name} missing NEXT_PUBLIC_APP_ENV", errors)

    require(next_config.exists(), "frontend/next.config.ts is missing", errors)
    if next_config.exists():
        text = next_config.read_text(encoding="utf-8")
        require("BACKEND_API_ORIGIN" in text, "next.config.ts must use BACKEND_API_ORIGIN rewrite target", errors)
        require("/api/v1/:path*" in text, "next.config.ts must rewrite /api/v1/:path*", errors)

    if errors:
        print("Release artifact check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Release artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
