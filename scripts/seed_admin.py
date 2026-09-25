import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.utils.security import hash_password


def seed_admin():
    app = create_app()  # goes through the same config/db wiring as the real app

    with app.app_context():
        admin_email = "admin@rica.local"
        admin_username = "admin"

        try:
            existing = db.user.find_unique(where={"email": admin_email})

            if existing:
                print(f"Admin account ({admin_email}) already exists.")
                print(f"  username: {existing.username}")
                print(f"  role: {existing.role}")
                print(f"  isActive: {existing.isActive}")
                print(f"  hash prefix: {existing.passwordHash[:7]}")
            else:
                admin = db.user.create(
                    data={
                        "email": admin_email,
                        "username": admin_username,   # required + unique in schema
                        "fullName": "System Admin",
                        "passwordHash": hash_password("ChangeMe123!"),
                        "role": "ADMIN",
                        "isActive": True,
                        "mustChangePassword": False,  # bootstrap admin can log in immediately
                    }
                )
                print(f"Admin created successfully with ID: {admin.id}")
                print("Login with:")
                print(f"  identifier: {admin_email}  (or username: {admin_username})")
                print("  password:   ChangeMe123!")

        except Exception as e:
            print(f"Error creating admin user: {e}")


if __name__ == "__main__":
    seed_admin()
