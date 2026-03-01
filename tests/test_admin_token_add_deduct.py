"""
Test admin token add/deduct endpoints.
Run from project root: python tests/test_admin_token_add_deduct.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Ensure we have an admin email for the test
os.environ.setdefault("ADMIN_EMAIL", "admin@test.local")


def test_admin_add_and_deduct_tokens():
    import database
    import models
    from fastapi.testclient import TestClient
    from main import app, get_current_user, get_admin_user

    db = database.SessionLocal()
    admin_user = None
    target_user = None
    try:
        # Create admin user (must match ADMIN_EMAIL)
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@test.local")
        admin_user = db.query(models.User).filter(models.User.email == admin_email).first()
        if not admin_user:
            admin_user = models.User(
                email=admin_email,
                plan_tier="trial",
                rebalance_interval=30,
            )
            admin_user.referral_code = "admin-ref"
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

        # Create target user with initial balance
        target_email = f"token-adjust-target-{id(db)}@test.local"
        target_user = models.User(
            email=target_email,
            plan_tier="trial",
            rebalance_interval=30,
        )
        target_user.referral_code = "target-ref"
        db.add(target_user)
        db.commit()
        db.refresh(target_user)
        target_id = target_user.id

        # Initial balance: 100
        db.add(models.UserTokenBalance(
            user_id=target_id,
            tokens_remaining=100.0,
            purchased_tokens=100.0,
            last_gross_usd_used=0.0,
        ))
        db.commit()

        def override_get_current_user():
            return db.query(models.User).filter(models.User.id == admin_user.id).first()

        app.dependency_overrides[get_current_user] = override_get_current_user
        client = TestClient(app)

        try:
            # Add 50 tokens
            r_add = client.post(
                f"/admin/users/{target_id}/tokens/add",
                json={"amount": 50},
            )
            assert r_add.status_code == 200, (r_add.status_code, r_add.text)
            data_add = r_add.json()
            assert "tokens_remaining" in data_add
            assert data_add["tokens_remaining"] == 150.0  # 100 + 50

            # Deduct 30 tokens
            r_deduct = client.post(
                f"/admin/users/{target_id}/tokens/deduct",
                json={"amount": 30},
            )
            assert r_deduct.status_code == 200, (r_deduct.status_code, r_deduct.text)
            data_deduct = r_deduct.json()
            assert data_deduct["tokens_remaining"] == 120.0  # 150 - 30

            # Validate invalid amount
            r_bad = client.post(f"/admin/users/{target_id}/tokens/add", json={"amount": 0})
            assert r_bad.status_code == 400
            r_bad2 = client.post(f"/admin/users/{target_id}/tokens/deduct", json={"amount": -1})
            assert r_bad2.status_code == 400

            print("admin add/deduct tokens: OK")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
    finally:
        if target_user is not None:
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == target_user.id).delete()
            db.query(models.User).filter(models.User.id == target_user.id).delete()
            db.commit()
        db.close()


if __name__ == "__main__":
    test_admin_add_and_deduct_tokens()
    print("All tests passed.")
