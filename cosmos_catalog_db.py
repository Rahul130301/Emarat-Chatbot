# cosmos_catalog_db.py
import os
from azure.cosmos import CosmosClient
from dotenv import load_dotenv

load_dotenv(override=True)

_client = None
_database = None

def get_cosmos_database():
    global _client, _database
    if _database is None:
        _client = CosmosClient(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_KEY"])
        _database = _client.create_database_if_not_exists(id="catalogs")
    return _database

def get_container(name: str):
    return get_cosmos_database().get_container_client(name)