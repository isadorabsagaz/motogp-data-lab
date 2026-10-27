from src.motogp_data_lab.storage import MongoStorage
from src.motogp_data_lab import config

storage = MongoStorage(config.MONGO_URI, config.MONGO_DB)

try:
    storage.ping()

    storage.upsert(
        "test",
        {
            "id": "teste-001",
            "message": "MongoDB connected to Python",
        },
    )

    print("Document recorded correctly")

finally:
    storage.close()