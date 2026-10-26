from src.motogp_data_lab.storage import MongoStorage

storage = MongoStorage()

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