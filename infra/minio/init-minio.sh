#!/bin/sh
set -eu

mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing "local/$MINIO_RAW_BUCKET"
mc mb --ignore-existing "local/$MINIO_MEDIA_BUCKET"
mc mb --ignore-existing "local/$MINIO_EXPORTS_BUCKET"

# Raw unredacted payloads have the architecture-mandated 90-day retention.
mc ilm rule add --expire-days 90 "local/$MINIO_RAW_BUCKET"

