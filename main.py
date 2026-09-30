from providers.github import get_latest_release
from logger import setup_logging
from config import load_config

import logging

release = get_latest_release("XTLS/Xray-core")

setup_logging()
logger = logging.getLogger(__name__)



def main() -> None:
    logger.info("ReleaseRadar started")

    config = load_config()
    software = config["software"][0]

    if not software["enabled"]:
        logger.info(
            "%s is disabled",
            software["name"],
        )
        return

    include_prerelease = software["channel"] == "prerelease"

    release = get_latest_release(
        software["repository"],
        include_prerelease=include_prerelease
    )

    logger.info(
        "%s latest version: %s",
        software["name"],
        release.version,
    )

    print()
    print(f"Software: {software['name']}")
    print(f"Version: {release.version}")
    print(f"Pre-release: {release.prerelease}")
    print(f"URL: {release.url}")

if __name__ == "__main__":
    main()