import argparse
import os


VALID_PROFILES = ("local", "dev", "prod")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StockAuto competitive user seed initializer",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        default="local",
        choices=VALID_PROFILES,
        help="Target runtime profile. prod is blocked for safety.",
    )
    return parser.parse_args(argv)


def ensure_seed_profile_allowed(profile: str) -> None:
    if profile == "prod":
        raise RuntimeError("prod 환경에서는 경쟁 계정 시딩을 실행할 수 없습니다.")


def run_seed(profile: str) -> None:
    ensure_seed_profile_allowed(profile)
    os.environ["APP_ENV"] = profile

    from app.core.migrator import (
        run_migrations_programmatically,
        seed_competitive_users,
    )

    run_migrations_programmatically()
    seed_competitive_users()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    profile = args.profile.lower().strip()

    print("=" * 60)
    print("StockAuto competitive user seed init")
    print(f"PROFILE: {profile.upper()}")
    print("=" * 60)

    run_seed(profile)
    print("Competitive user seed completed.")


if __name__ == "__main__":
    main()
