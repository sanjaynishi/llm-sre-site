import json
import os
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

# =====================
# Environment variables
# =====================
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "").lstrip("/")     # e.g. knowledge/
RUNBOOKS_PREFIX = os.environ.get("RUNBOOKS_PREFIX", "runbooks/").lstrip("/")
AGENTS_KEY = os.environ.get("AGENTS_KEY", "agents.json")

# =====================
# Helpers
# =====================
def _s3_key(path: str) -> str:
    """
    Build full S3 key using S3_PREFIX.
    """
    if not S3_PREFIX:
        return path.lstrip("/")
    return f"{S3_PREFIX.rstrip('/')}/{path.lstrip('/')}"

def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
            "access-control-allow-methods": "GET,POST,OPTIONS",
            "access-control-allow-headers": "*",
        },
        "body": json.dumps(body),
    }

def _get_object_text(bucket: str, key: str) -> str:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read().decode("utf-8", errors="replace")

def _get_object_json(bucket: str, key: str) -> dict:
    return json.loads(_get_object_text(bucket, key))


# =====================
# Lambda handler
# =====================
def handler(event, context):
    # Handle CORS preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _response(200, {"ok": True})

    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")

    try:
        # -----------------
        # Health check
        # -----------------
        if path == "/health":
            return _response(200, {
                "status": "ok",
                "bucket": S3_BUCKET,
                "prefix": S3_PREFIX
            })

        # -----------------
        # List runbooks
        # GET /runbooks
        # -----------------
        if path == "/runbooks" and method == "GET":
            prefix = _s3_key(RUNBOOKS_PREFIX)

            resp = s3.list_objects_v2(
                Bucket=S3_BUCKET,
                Prefix=prefix
            )

            runbooks = []
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(".pdf"):
                    runbooks.append({
                        "name": key.split("/")[-1],
                        "key": key,
                        "size": obj.get("Size", 0),
                        "last_modified": obj["LastModified"].isoformat()
                    })

            runbooks.sort(key=lambda x: x["name"].lower())
            return _response(200, {
                "bucket": S3_BUCKET,
                "prefix": prefix,
                "runbooks": runbooks
            })

        # -----------------
        # Get runbook content
        # GET /doc?name=FILE.pdf
        # GET /doc?key=full/s3/key.pdf
        # -----------------
        if path == "/doc" and method == "GET":
            qs = event.get("queryStringParameters") or {}

            # Option 1: full key provided
            if "key" in qs:
                key = qs["key"]
                content = _get_object_text(S3_BUCKET, key)
                return _response(200, {"key": key, "content": content})

            # Option 2: filename provided
            if "name" in qs:
                filename = qs["name"]
                prefix = _s3_key(RUNBOOKS_PREFIX)

                resp = s3.list_objects_v2(
                    Bucket=S3_BUCKET,
                    Prefix=prefix
                )

                for obj in resp.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(filename):
                        content = _get_object_text(S3_BUCKET, key)
                        return _response(200, {"key": key, "content": content})

                return _response(404, {"error": f"Runbook not found: {filename}"})

            return _response(400, {"error": "Provide ?name=<file.pdf> or ?key=<s3-key>"})

        # -----------------
        # Agents (optional)
        # GET /agents
        # -----------------
        if path == "/agents" and method == "GET":
            key = _s3_key(AGENTS_KEY)
            data = _get_object_json(S3_BUCKET, key)
            return _response(200, data)

        return _response(404, {"error": f"Route not found: {method} {path}"})

    except ClientError as e:
        return _response(500, {"error": "AWS error", "detail": str(e)})
    except Exception as e:
        return _response(500, {"error": "Unhandled error", "detail": str(e)})