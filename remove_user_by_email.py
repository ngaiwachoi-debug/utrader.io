"""
Remove the account for choiwangai@gmail.com (user row + api_vault + related logs).
Run once: python remove_user_by_email.py
"""
from database import SessionLocal
import models

EMAIL = "choiwangai@gmail.com"

def main():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user:
            print(f"No account found for {EMAIL}")
            return
        user_id = user.id
        # Delete vault first (FK user_id)
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        if vault:
            db.delete(vault)
            print("Removed API vault for user.")
        # Delete performance logs for this user
        db.query(models.PerformanceLog).filter(models.PerformanceLog.user_id == user_id).delete()
        # Delete user
        db.delete(user)
        db.commit()
        print(f"Account for {EMAIL} (user_id={user_id}) has been removed.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
