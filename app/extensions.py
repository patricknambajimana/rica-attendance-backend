"""
Single source of truth for shared instances: the Prisma client and the JWT
manager. Every other module must import `db` and `jwt` from here — never
create a second Prisma() instance elsewhere, or you end up with two clients
that don't share a connection (a common cause of "it works in the seed
script but not in the API" bugs).
"""
from flask_jwt_extended import JWTManager
from prisma import Prisma

db = Prisma()
jwt = JWTManager()
