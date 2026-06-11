import pytest
from datetime import date
from src.database.enum import UserRole, OrderStatus
from src.database.schema import Order
from database_api import Session
from tests.utils import auth_header_for

def test_reproduce_order_revert_bug(client):
    # 1. Find a Booked order created by seed
    with Session() as session:
        order = session.query(Order).filter(Order.status == OrderStatus.BOOKED).first()
        assert order is not None
        order_id = order.id
        original_booking_date = order.booking_date
        assert original_booking_date is not None

    # 2. Simulate the faulty PUT request from the frontend
    # status: 'Acquired', confirmed: false, but keep booking_date
    payload = {
        "id": order_id,
        "status": "Acquired",
        "confirmed": False,
        "booking_date": original_booking_date.isoformat(),
        # Add other required fields if necessary to avoid validation errors
        "address": order.address,
        "addressee": order.addressee,
        "cap": order.cap,
        "type": order.type.value,
        "user_id": order.user_id
    }
    
    response = client.put(f'/order/{order_id}', json=payload, headers=auth_header_for('admin', role=UserRole.ADMIN))
    assert response.status_code == 200
    
    # 3. Verify the status
    with Session() as session:
        updated_order = session.query(Order).get(order_id)
        # BEFORE FIX: This will fail because it reverted to ACQUIRED
        # AFTER FIX: This should pass
        assert updated_order.status == OrderStatus.BOOKED
