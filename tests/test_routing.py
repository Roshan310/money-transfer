from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_openapi_contains_only_versioned_business_routes() -> None:
    schema = create_app().openapi()
    operations = {
        (method, path)
        for path, methods in schema["paths"].items()
        for method in methods
    }
    assert operations == {
        ("post", "/api/v1/accounts"),
        ("get", "/api/v1/accounts"),
        ("get", "/api/v1/accounts/{account_id}"),
        ("get", "/api/v1/accounts/{account_id}/transactions"),
        ("post", "/api/v1/transfers"),
    }
    operation_ids = [
        operation["operationId"]
        for methods in schema["paths"].values()
        for operation in methods.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/accounts"),
        ("GET", "/accounts"),
        ("GET", f"/accounts/{uuid4()}"),
        ("GET", f"/accounts/{uuid4()}/transactions"),
        ("POST", "/transfers"),
    ],
)
def test_unversioned_business_routes_are_removed(method: str, path: str) -> None:
    with TestClient(create_app()) as client:
        response = client.request(method, path, follow_redirects=False)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_documentation_urls_are_preserved(path: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 200
