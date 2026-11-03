#storage.py: operações com o MongoDB.
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne

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

    def ensure_indexes(self):
        # create_index é idempotente: se o índice já existe igual, não faz nada.
        # O _id já tem índice automático, por isso não aparece aqui.

        # Sessões de um evento (referência aninhada, dot notation)
        self.db["sessions"].create_index("event.id")

        # Classificação de uma sessão
        self.db["classification"].create_index("session_id")

        # Histórico de um piloto (também atende consultas só por rider_id)
        self.db["classification"].create_index(
            [("rider_id", 1), ("season_year", 1)],
        )

    def upsert(self, collection_name: str, document: dict):
        document_id = document["id"]

        self.db[collection_name].update_one(
            {"_id": document_id},
            {"$set": document},
            upsert=True,
        )

    def upsert_many(self, collection_name: str, documents: list, source_endpoint: str):
        if not documents:
            return None

        operations = []
        # Calculado uma vez: todos os documentos desta chamada recebem o mesmo horário.
        now = datetime.now(timezone.utc)

        for doc in documents:
            document_id = doc["id"]
            operations.append(
                UpdateOne(
                    {"_id": document_id},
                    {
                        # Dados da API + endpoint de origem. Valores idênticos não contam como modified.
                        "$set": {**doc, "_source_endpoint": source_endpoint},
                        # Só grava na criação; em reexecuções mantém a data original.
                        "$setOnInsert": {"_ingested_at": now},
                    },
                    upsert=True
                )
            )

        return self.db[collection_name].bulk_write(operations, ordered=False)

    def close(self):
        self.client.close()
