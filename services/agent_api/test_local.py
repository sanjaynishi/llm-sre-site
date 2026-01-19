from app import lambda_handler
import json

# Simulate API Gateway HTTP API event
event = {
    "requestContext": {
        "http": {
            "method": "POST"
        }
    },
    "rawPath": "/api/agent/run",
    "headers": {
        "content-type": "application/json"
    },
    "body": json.dumps({
        "agent_id": "agent-weather",
        "location": "London, UK"
    }),
    "isBase64Encoded": False
}

response = lambda_handler(event, None)

print("STATUS:", response["statusCode"])
print("HEADERS:", response["headers"])
print("BODY (truncated):")
print(response["body"][:800])