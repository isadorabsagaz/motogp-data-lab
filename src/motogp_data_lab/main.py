from src.motogp_data_lab.ingestion import collect_season
from src.motogp_data_lab.storage import MongoStorage

def main():
    storage = MongoStorage()

    try:
        storage.ping()
        print("MongoDB connected")

        collect_season(storage)
        print("Season Collection completed")

    finally:
        storage.close()

if __name__ == "__main__":
    main()