"""Create the private source-document bucket for local development."""

import time

from app.core.config import get_settings
from app.infrastructure.resources import Infrastructure


def main() -> None:
    settings = get_settings()
    resources = Infrastructure.from_settings(settings)
    for attempt in range(30):
        try:
            if not resources.minio.bucket_exists(resources.bucket):
                resources.minio.make_bucket(resources.bucket)
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)
    print(f"Bucket ready: {resources.bucket}")


if __name__ == "__main__":
    main()
