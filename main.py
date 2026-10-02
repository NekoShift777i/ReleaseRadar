from providers.github import get_latest_release
from logger import setup_logging
from config import load_config
from datetime import datetime, timezone
from database import (
    initialize_database, 
    get_or_create_software_state,
    update_software_check,
)

import logging

setup_logging()
logger = logging.getLogger(__name__)



def main() -> None:
    logger.info("ReleaseRadar started")

    initialize_database()

    config = load_config()

    for software in config["software"]:
        if not software["enabled"]:
            logger.info(
                "%s is disabled",
                software["name"],
            )
            continue

        try:
            state = get_or_create_software_state(
                    software["id"],
                    software["current_version"],
                )

            logger.info(
                "%s Current version: %s",
                software["name"],
                state["current_version"]
            )

            include_prerelease = (
                software["channel"] == "prerelease"
            )

            release = get_latest_release(
                    software["repository"],
                    include_prerelease=include_prerelease,
                )

            logger.info(
                "%s latest version: %s",
                software["name"],
                release.version,
            )

            update_software_check(
                software["id"],
                release.version,
                datetime.now(timezone.utc).isoformat(),
            )

            print()
            print(f"Software: {software['name']}")
            print(f"Version: {release.version}")
            print(f"Pre-release: {release.prerelease}")
            print(f"URL: {release.url}")

        except Exception:
            logger.exception(
                "Failed to check %s",
                software["name"],
            )

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("ReleaseRadar crashed")
        raise