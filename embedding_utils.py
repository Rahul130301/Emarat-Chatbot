# embedding_utils.py
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

embed_client = OpenAI(
    base_url=os.environ["AZURE_OPENAI_EMBEDDING_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_EMBEDDING_API_KEY"],
)
EMBED_DEPLOYMENT = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

def embed(text: str) -> list[float]:
    resp = embed_client.embeddings.create(model=EMBED_DEPLOYMENT, input=text)
    return resp.data[0].embedding

def embedding_to_json(vec: list[float]) -> str:
    return json.dumps(vec)

def embedding_from_json(s: str) -> list[float]:
    return json.loads(s)