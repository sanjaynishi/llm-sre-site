#!/usr/bin/env bash
set -euo pipefail

BUCKET="llm-sre-agent-config-dev-830330555687"
DEST_PREFIX="knowledge/vectors/dev/chroma"
SRC_DIR="rag_store_dev"

if [ ! -d "$SRC_DIR" ]; then
  echo "ERROR: local dir not found: $SRC_DIR"
  exit 1
fi

echo "Uploading ${SRC_DIR} -> s3://${BUCKET}/${DEST_PREFIX}/"
aws s3 sync "$SRC_DIR" "s3://${BUCKET}/${DEST_PREFIX}/" --delete

echo "Done."
aws s3 ls "s3://${BUCKET}/${DEST_PREFIX}/" | head