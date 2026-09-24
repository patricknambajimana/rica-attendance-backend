from app.db import db
from app.security import hash_password

def seed_admin():
    # 1. Connect to Prisma DB
    if not db.is_connected():
        db.connect()

    admin_email = "admin@rica.local"

    try:
        # 2. Check if admin user already exists
        existing_admin = db.user.find_unique(where={"email": admin_email})

        if existing_admin:
            print(f"Admin account ({admin_email}) already exists. Skipping creation.")
        else:
            # 3. Create initial Admin user
            admin = db.user.create(
                data={
                    "email": admin_email,
                    "fullName": "System Admin",
                    "passwordHash": hash_password("ChangeMe123!"),
                    "role": "ADMIN",
                }
            )
            print(f"Admin created successfully with ID: {admin.id}")

    except Exception as e:
        print(f"Error creating admin user: {e}")

    finally:
        # 4. Safely disconnect
        if db.is_connected():
            db.disconnect()

if __name__ == "__main__":
    seed_admin()