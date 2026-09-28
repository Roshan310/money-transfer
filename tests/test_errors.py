import logging

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import StatementError

from app.main import app, create_app


def test_unexpected_error_is_json_and_logged(caplog) -> None:
    application = create_app()

    @application.get("/failure")
    def fail():
        raise RuntimeError("Private failure information")

    with caplog.at_level(logging.ERROR, logger="app.errors"):
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get("/failure")
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"detail": "Internal server error"}
    assert "Private failure information" not in response.text
    assert "Unhandled error for GET /failure" in caplog.text
    assert "Private failure information" in caplog.text


def test_database_error_parameters_are_not_logged(caplog) -> None:
    application = create_app()

    @application.get("/database-failure")
    def fail():
        raise StatementError(
            "Database operation failed",
            "INSERT INTO transfers VALUES (:key)",
            {"key": "private-idempotency-key"},
            RuntimeError("Database operation failed"),
            hide_parameters=True,
        )

    with caplog.at_level(logging.ERROR, logger="app.errors"):
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get("/database-failure")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "private-idempotency-key" not in caplog.text
    assert "SQL parameters hidden" in caplog.text


def test_http_and_validation_errors_keep_existing_contract() -> None:
    application = create_app()

    @application.get("/conflict")
    def conflict():
        raise HTTPException(status_code=409, detail="Existing conflict")

    with TestClient(application) as client:
        assert client.get("/conflict").json() == {"detail": "Existing conflict"}
        response = client.post("/api/v1/accounts", json={})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
        assert client.get("/missing-route").json() == {"detail": "Not Found"}


def test_openapi_documents_history_and_errors() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    history = schema["paths"]["/api/v1/accounts/{account_id}/transactions"]["get"]
    assert set(history["responses"]) == {"200", "404", "422", "500"}
    assert history["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    parameters = {
        parameter["name"]: parameter["schema"] for parameter in history["parameters"]
    }
    assert parameters["limit"]["default"] == 20
    assert parameters["limit"]["maximum"] == 100
    assert parameters["offset"]["minimum"] == 0
    assert "Idempotency-Key" in {
        parameter["name"]
        for parameter in schema["paths"]["/api/v1/transfers"]["post"]["parameters"]
    }


def test_existing_root_endpoint_is_preserved() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Welcome to the Money Transfer System! Everything is working fine."
    }
