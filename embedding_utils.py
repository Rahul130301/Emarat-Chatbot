# embedding_utils.py
import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

embed_client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_EMBEDDING_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_EMBEDDING_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_EMBEDDING_API_VERSION"],
)
EMBED_DEPLOYMENT = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

def embed(text: str) -> list[float]:
    resp = embed_client.embeddings.create(model=EMBED_DEPLOYMENT, input=text)
    return resp.data[0].embedding

def embedding_to_json(vec: list[float]) -> str:
    return json.dumps(vec)

def embedding_from_json(s: str) -> list[float]:
    return json.loads(s)