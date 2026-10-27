#storage.py: operações com o MongoDB.
from pymongo import MongoClient

class MongoStorage:
    def __init__(
            self,
            uri: str,
            database_name: str,
    ):
        self.client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
        )
        self.db = self.client[database_name]

    def ping(self):
        self.client.admin.command('ping')

    def upsert(self, collection_name: str, document: dict):
        document_id = document["id"]

        self.db[collection_name].update_one(
            {"_id": document_id},
            {"$set": document},
            upsert=True,
        )

    def close(self):
        self.client.close()