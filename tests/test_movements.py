import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.adapters.driving.routers.movements import router as movements_router
from app.adapters.driving.middlewares.ownership_decorator import verify_account_ownership
from app.core.container import get_db

# Create an isolated FastAPI instance to test the movements router logic and schema validations
app = FastAPI()
app.include_router(movements_router)

# Override security dependencies to focus on routing and filtering logic
app.dependency_overrides[verify_account_ownership] = lambda: "ACC-111"
app.dependency_overrides[get_db] = lambda: None

client = TestClient(app)


def test_movements_successful_retrieval():
    # Request movements
    response = client.get("/movements?account_id=ACC-111")
    assert response.status_code == 200
    data = response.json()
    assert "movements" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert data["total"] > 0
    
    # Validate that all movements are from ACC-111
    for mv in data["movements"]:
        assert mv["account_id"] == "ACC-111"

    # Check structure of first movement
    movement = data["movements"][0]
    assert "id" in movement
    assert "type" in movement
    assert "amount" in movement
    assert "currency" in movement
    assert "status" in movement
    assert "created_at" in movement
    assert "description" in movement


def test_movements_type_and_instrument_filtering():
    # Filter by type=FONDEO
    response = client.get("/movements?account_id=ACC-111&type=FONDEO")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    for mv in data["movements"]:
        assert mv["type"] == "FONDEO"

    # Filter by instrument=AAPL
    response_inst = client.get("/movements?account_id=ACC-111&instrument=AAPL")
    assert response_inst.status_code == 200
    data_inst = response_inst.json()
    assert data_inst["total"] == 1
    for mv in data_inst["movements"]:
        assert mv["instrument"] == "AAPL"


def test_movements_export_as_csv():
    response = client.post("/movements/export?account_id=ACC-111&format=CSV")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert "download_url" in data
    assert data["expires_in_seconds"] == 900


def test_movements_invalid_type_validation():
    # Request with invalid type should return 422 Unprocessable Entity
    response = client.get("/movements?account_id=ACC-111&type=INVALID_TYPE")
    assert response.status_code == 422


def test_movements_database_integration():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.adapters.driven.database.models import Base, DBOrder, DBTransfer
    from datetime import datetime
    from decimal import Decimal

    # Set up shared in-memory sqlite for this test to allow thread sharing with TestClient
    engine = create_engine("sqlite:///file:test_movements_db?mode=memory&cache=shared", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Populate DBOrder and DBTransfer
    db_order = DBOrder(
        order_id="TX-DB-ORD-001",
        account_id="ACC-111",
        instrument_id="NVDA",
        side="BUY",
        quantity=Decimal("5.500000"),
        order_type="LIMIT",
        limit_price=Decimal("120.500000"),
        time_in_force="GTC",
        status="FILLED",
        idempotency_key="idemp-key-1",
        created_at=datetime(2024, 3, 15, 12, 0, 0),
        average_filled_price=Decimal("120.000000")
    )
    db_transfer = DBTransfer(
        transfer_id="TR-DB-TRA-002",
        account_id="ACC-111",
        beneficiary_id="clabe-beneficiary-1234",
        amount=Decimal("3500.00"),
        currency="MXN",
        idempotency_key="idemp-key-2",
        status="COMPLETED",
        created_at=datetime(2024, 3, 16, 14, 0, 0)
    )

    session.add(db_order)
    session.add(db_transfer)
    session.commit()

    # Create helper to yield session
    def get_test_db():
        # Keep connection open for the duration of the request
        db_sess = Session()
        try:
            yield db_sess
        finally:
            db_sess.close()

    # Override dependency in app
    app.dependency_overrides[get_db] = get_test_db

    try:
        response = client.get("/movements?account_id=ACC-111")
        assert response.status_code == 200
        data = response.json()
        
        # Verify both mock data and DB data are returned
        movements = data["movements"]
        ids = [m["id"] for m in movements]
        
        assert "TX-DB-ORD-001" in ids
        assert "TR-DB-TRA-002" in ids
        
        # Verify properties of NVDA purchase
        nvda_order = next(m for m in movements if m["id"] == "TX-DB-ORD-001")
        assert nvda_order["instrument"] == "NVDA"
        assert nvda_order["quantity"] == 5.5
        assert nvda_order["price"] == 120.0
        assert nvda_order["amount"] == 660.0  # 5.5 * 120.0
        assert nvda_order["type"] == "TRANSACCION"
        assert nvda_order["status"] == "liquidada"

        # Verify properties of transfer
        transfer_mv = next(m for m in movements if m["id"] == "TR-DB-TRA-002")
        assert transfer_mv["amount"] == 3500.0
        assert transfer_mv["type"] == "RETIRO"
        assert transfer_mv["status"] == "liquidada"
        assert "1234" in transfer_mv["description"]

    finally:
        # Clean up database resources and reset overrides
        session.close()
        app.dependency_overrides[get_db] = lambda: None
