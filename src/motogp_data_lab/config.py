#config.py: configuração por variáveis de ambiente.
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "motogp")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")