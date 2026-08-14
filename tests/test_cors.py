from fastapi.testclient import TestClient
from app.main import app

def test_cors_headers_with_origin():
    client = TestClient(app)
    # Perform a request with an Origin header in the configured list
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_headers_with_disallowed_origin():
    client = TestClient(app)
    # Perform a request with an Origin header NOT in the configured list
    response = client.get(
        "/health",
        headers={"Origin": "http://malicious-site.com"}
    )
    assert response.status_code == 200
    # Starlette's CORSMiddleware does NOT include CORS headers if the origin is not allowed
    assert "access-control-allow-origin" not in response.headers
