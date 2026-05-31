import asyncio
import contextlib
import contextvars
import os
import re
import uuid
from datetime import date, datetime
from typing import Any

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pymongo.errors import ConfigurationError, PyMongoError

set_tracing_disabled(True)
load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
mongo_uri = os.getenv("MONGO_URI")
mongo_db_name = os.getenv("MONGO_DB_NAME")
mongo_collection_name = os.getenv("MONGO_COLLECTION_NAME", "properties")

if not gemini_api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from .env")

if not mongo_uri:
    raise RuntimeError("MONGO_URI is missing from .env")

client = AsyncOpenAI(
    api_key=gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

mongo_client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)

if mongo_db_name:
    mongo_database = mongo_client[mongo_db_name]
else:
    try:
        mongo_database = mongo_client.get_default_database()
    except ConfigurationError as exc:
        raise RuntimeError(
            "MONGO_DB_NAME is missing from .env and MONGO_URI does not include a database name"
        ) from exc

properties_collection = mongo_database[mongo_collection_name]
captured_properties: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "captured_properties",
    default=None,
)
sessions: dict[str, dict[str, Any]] = {}
sessions_lock = asyncio.Lock()

MAX_SESSION_MESSAGES = 10
SESSION_TTL_SECONDS = 30 * 60
CLEANUP_INTERVAL_SECONDS = 5 * 60

STOP_WORDS = {
    "and",
    "are",
    "for",
    "from",
    "has",
    "have",
    "need",
    "property",
    "rent",
    "rental",
    "show",
    "the",
    "under",
    "with",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _property_summary(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _json_safe(document.get("_id")),
        "title": document.get("title"),
        "description": document.get("description"),
        "propertyType": document.get("propertyType"),
        "price": document.get("price"),
        "bedrooms": document.get("bedrooms"),
        "bathrooms": document.get("bathrooms"),
        "propertySize": document.get("propertySize"),
        "sizeUnit": document.get("sizeUnit"),
        "location": document.get("location"),
        "amenities": _json_safe(document.get("amenities", [])),
        "availableFrom": _json_safe(document.get("availableFrom")),
        "averageRating": document.get("averageRating"),
        "images": [
            image.get("url")
            for image in document.get("images", [])
            if isinstance(image, dict) and image.get("url")
        ],
    }


def _query_terms(query: str) -> list[str]:
    terms = re.findall(r"[a-zA-Z0-9]+", query.casefold())
    return [term for term in terms if len(term) >= 3 and term not in STOP_WORDS]


def _score_property(
    document: dict[str, Any],
    query: str,
    location: str | None,
    property_type: str | None,
    max_price: int | None,
    min_bedrooms: int | None,
    min_bathrooms: int | None,
) -> int:
    score = 0
    query_terms = _query_terms(query)
    searchable_text = " ".join(
        str(document.get(field, ""))
        for field in ("title", "description", "location", "propertyType")
    ).casefold()

    score += sum(1 for term in query_terms if term in searchable_text)
    if location and location.casefold() == str(document.get("location", "")).casefold():
        score += 4
    if property_type and property_type.casefold() == str(document.get("propertyType", "")).casefold():
        score += 3
    if max_price is not None and document.get("price", 0) <= max_price:
        score += 2
    if min_bedrooms is not None and document.get("bedrooms", 0) >= min_bedrooms:
        score += 2
    if min_bathrooms is not None and document.get("bathrooms", 0) >= min_bathrooms:
        score += 1
    if document.get("averageRating", 0):
        score += 1

    return score


async def fetch_rental_properties(
    query: str,
    location: str | None = None,
    property_type: str | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    min_bathrooms: int | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 10))
    mongo_filter: dict[str, Any] = {"isAvailable": True}

    if location:
        mongo_filter["location"] = {"$regex": f"^{re.escape(location)}$", "$options": "i"}
    if property_type:
        mongo_filter["propertyType"] = {"$regex": f"^{re.escape(property_type)}$", "$options": "i"}
    if max_price is not None:
        mongo_filter["price"] = {"$lte": max_price}
    if min_bedrooms is not None:
        mongo_filter["bedrooms"] = {"$gte": min_bedrooms}
    if min_bathrooms is not None:
        mongo_filter["bathrooms"] = {"$gte": min_bathrooms}

    query_terms = _query_terms(query)
    if query_terms:
        mongo_filter["$or"] = [
            {field: {"$regex": re.escape(term), "$options": "i"}}
            for term in query_terms
            for field in ("title", "description", "location", "propertyType", "amenities")
        ]

    projection = {
        "title": 1,
        "description": 1,
        "propertyType": 1,
        "price": 1,
        "bedrooms": 1,
        "bathrooms": 1,
        "propertySize": 1,
        "sizeUnit": 1,
        "location": 1,
        "amenities": 1,
        "availableFrom": 1,
        "averageRating": 1,
        "images.url": 1,
    }

    try:
        cursor = properties_collection.find(mongo_filter, projection).limit(50)
        documents = await cursor.to_list(length=50)
    except PyMongoError as exc:
        return [{"error": f"MongoDB property search failed: {exc}"}]

    documents.sort(
        key=lambda document: _score_property(
            document,
            query,
            location,
            property_type,
            max_price,
            min_bedrooms,
            min_bathrooms,
        ),
        reverse=True,
    )

    return [_property_summary(document) for document in documents[:limit]]


@function_tool
async def search_rental_properties(
    query: str,
    location: str | None = None,
    property_type: str | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    min_bathrooms: int | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search available rental properties in MongoDB for HomeRent.ai users."""

    properties = await fetch_rental_properties(
        query=query,
        location=location,
        property_type=property_type,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        min_bathrooms=min_bathrooms,
        limit=limit,
    )
    capture = captured_properties.get()
    if capture is not None and not any("error" in property_item for property_item in properties):
        capture.clear()
        capture.extend(properties)
    return properties


agent = Agent(
    name="Smith",
    instructions=(
        "Your name is Smith. You are the user's HouseIntel rental assistant. "
        "Help users find rental properties based on their preferences and requirements. "
        "Before recommending specific properties, call search_rental_properties to fetch "
        "current matching listings from MongoDB. Ask concise follow-up questions when the "
        "user has not provided enough criteria such as location, budget, property type, "
        "bedrooms, or bathrooms. Summarize useful property details including location, "
        "price, bedrooms, bathrooms, amenities, availability, and image links when present."
    ),
    model=OpenAIChatCompletionsModel(model="gemini-2.5-flash-lite", openai_client=client),
    tools=[search_rental_properties],
)


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    session_id: str
    message: str
    properties: list[dict[str, Any]]


class DeleteSessionResponse(BaseModel):
    session_id: str
    cleared: bool


def _now() -> datetime:
    return datetime.utcnow()


def _trim_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return messages[-MAX_SESSION_MESSAGES:]


def _remove_expired_sessions(now: datetime) -> None:
    expired_session_ids = [
        session_id
        for session_id, session in sessions.items()
        if (now - session["last_seen"]).total_seconds() > SESSION_TTL_SECONDS
    ]
    for session_id in expired_session_ids:
        sessions.pop(session_id, None)


async def _cleanup_sessions_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        async with sessions_lock:
            _remove_expired_sessions(_now())


async def _run_agent(session_id: str, message: str) -> ChatResponse:
    now = _now()
    async with sessions_lock:
        _remove_expired_sessions(now)
        session = sessions.setdefault(session_id, {"messages": [], "last_seen": now})
        history = list(session["messages"])
        session["last_seen"] = now

    properties: list[dict[str, Any]] = []
    token = captured_properties.set(properties)
    try:
        result = await Runner.run(agent, history + [{"role": "user", "content": message}])
    finally:
        captured_properties.reset(token)

    assistant_message = str(result.final_output)
    updated_messages = _trim_messages(
        history
        + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": assistant_message},
        ]
    )

    async with sessions_lock:
        sessions[session_id] = {"messages": updated_messages, "last_seen": _now()}

    return ChatResponse(session_id=session_id, message=assistant_message, properties=properties)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_sessions_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        mongo_client.close()


app = FastAPI(title="HomeRent.ai Agent API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    session_id = request.session_id or str(uuid.uuid4())
    return await _run_agent(session_id=session_id, message=message)


@app.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str) -> DeleteSessionResponse:
    async with sessions_lock:
        cleared = sessions.pop(session_id, None) is not None
    return DeleteSessionResponse(session_id=session_id, cleared=cleared)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
