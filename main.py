from providers.github import get_latest_release
from logger import setup_logging

import logging

release = get_latest_release("XTLS/Xray-core")

setup_logging()
logger = logging.getLogger(__name__)



def main() -> None:
    logger.info("ReleaseRadar started")

    release = get_latest_release(
        "XTLS/Xray-core",
        include_prerelease=True,
    )

    logger.info(
        "Xray-core latest version: %s",
        release.version,
    )

print(f"Version: {release.version}")
print(f"Pre-release: {release.prerelease}")
print(f"URL: {release.url}")

if __name__ == "__main__":
    main()