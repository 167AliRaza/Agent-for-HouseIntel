# Agent for HouseIntel 🏠

An intelligent rental property search assistant powered by AI agents. This project provides a FastAPI-based backend for HomeRent.ai that helps users find rental properties using natural language queries with real-time MongoDB integration.

**Live Demo:** https://house-intel-ashen.vercel.app

## Overview

Agent for HouseIntel is an AI-powered rental property search system that combines:
- **OpenAI Agent Framework** for intelligent conversation and decision-making
- **Google's Gemini 2.5 Flash Lite** model for natural language understanding
- **MongoDB** for persistent property data storage
- **FastAPI** for a modern, async REST API
- **Session Management** for maintaining conversation context

The system uses an intelligent agent named "Smith" that understands user requirements and performs targeted property searches based on preferences like location, budget, bedrooms, bathrooms, and property type.

## Features

✨ **Key Features:**
- 🤖 AI-powered conversational assistant for property search
- 🔍 Advanced filtering by location, price, bedrooms, bathrooms, and property type
- 📊 Smart relevance scoring for search results
- 💬 Session-based conversation history (max 10 messages per session)
- 🧹 Automatic session cleanup after 30 minutes of inactivity
- 🔄 Async/concurrent request handling
- 🛡️ CORS-enabled for frontend integration
- 📱 REST API with health checks

## Tech Stack

- **Language:** Python 3.13+
- **Framework:** FastAPI
- **Database:** MongoDB (Motor async driver)
- **AI/ML:** OpenAI Agents, Google Gemini 2.5 Flash Lite
- **Server:** Uvicorn
- **Package Manager:** UV

## Prerequisites

Before running this project, ensure you have:

- Python 3.13 or higher
- MongoDB instance (local or cloud-hosted like MongoDB Atlas)
- Google Gemini API key
- Internet connection for API calls

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/167AliRaza/Agent-for-HouseIntel.git
   cd Agent-for-HouseIntel
   ```

2. **Install dependencies using UV:**
   ```bash
   uv sync
   ```
   
   Or with pip:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create a `.env` file** in the project root:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/
   MONGO_DB_NAME=your_database_name
   MONGO_COLLECTION_NAME=properties
   ```

   **Environment Variables:**
   - `GEMINI_API_KEY`: Your Google Gemini API key (required)
   - `MONGO_URI`: MongoDB connection URI (required)
   - `MONGO_DB_NAME`: Database name (optional if included in MONGO_URI)
   - `MONGO_COLLECTION_NAME`: Collection name for properties (default: `properties`)

## Running the Server

Start the development server:
```bash
python main.py
```

The API will be available at `http://127.0.0.1:8000`

Access the interactive API documentation:
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## API Endpoints

### 1. Health Check
**GET** `/health`

Check if the server is running.

**Response:**
```json
{
  "status": "ok"
}
```

### 2. Chat with Agent
**POST** `/chat`

Send a message to the rental property search agent.

**Request Body:**
```json
{
  "session_id": "optional-session-uuid",
  "message": "I'm looking for a 2-bedroom apartment in downtown with a maximum budget of $2000/month"
}
```

**Response:**
```json
{
  "session_id": "uuid-string",
  "message": "I found 3 rental properties matching your criteria...",
  "properties": [
    {
      "id": "mongodb-object-id",
      "title": "Cozy Downtown Apartment",
      "description": "Beautiful 2-bedroom apartment in downtown",
      "propertyType": "Apartment",
      "price": 1800,
      "bedrooms": 2,
      "bathrooms": 1,
      "propertySize": 850,
      "sizeUnit": "sqft",
      "location": "Downtown",
      "amenities": ["WiFi", "Parking", "Gym"],
      "availableFrom": "2026-06-15",
      "averageRating": 4.5,
      "images": ["url1", "url2"]
    }
  ]
}
```

### 3. Delete Session
**DELETE** `/sessions/{session_id}`

Clear a specific session and its history.

**Response:**
```json
{
  "session_id": "uuid-string",
  "cleared": true
}
```

## Agent Capabilities

The "Smith" agent is designed to:
- Understand natural language queries about rental properties
- Ask clarifying questions when insufficient criteria are provided
- Fetch matching properties from MongoDB based on user preferences
- Filter by: location, budget (max price), property type, bedrooms, bathrooms
- Score and rank results based on relevance
- Maintain conversation context across multiple messages (up to 10 messages per session)
- Provide helpful summaries including pricing, amenities, availability, and images

### Search Query Examples
- "Find me a 3-bedroom house in Brooklyn under $3000/month"
- "Show me pet-friendly apartments in downtown with at least 2 bathrooms"
- "I need a studio near the park with utilities included"
- "Any luxury apartments with a gym in the financial district?"

## MongoDB Schema

Expected property document structure in MongoDB:

```json
{
  "_id": ObjectId,
  "title": "String",
  "description": "String",
  "propertyType": "String (e.g., Apartment, House, Condo)",
  "price": Number,
  "bedrooms": Number,
  "bathrooms": Number,
  "propertySize": Number,
  "sizeUnit": "String (e.g., sqft, sqm)",
  "location": "String",
  "amenities": [String],
  "availableFrom": "Date",
  "isAvailable": Boolean,
  "averageRating": Number,
  "images": [
    {
      "url": "String",
      "alt": "String"
    }
  ]
}
```

## Configuration

### Session Management
- **Max Messages per Session:** 10 (configurable via `MAX_SESSION_MESSAGES`)
- **Session TTL:** 30 minutes (configurable via `SESSION_TTL_SECONDS`)
- **Cleanup Interval:** 5 minutes (configurable via `CLEANUP_INTERVAL_SECONDS`)

### Search Filtering
- **Max Results:** Limited to 50 properties per MongoDB query, then top 5 returned
- **Stop Words:** Common words filtered from queries to improve search quality

## Performance Considerations

- **Async Operations:** All MongoDB queries and API calls are asynchronous
- **Connection Pooling:** Motor handles MongoDB connection pooling
- **Context Variables:** Uses `contextvars` for thread-safe property capture across async contexts
- **Session Cleanup:** Background task automatically removes expired sessions

## Error Handling

The API gracefully handles:
- Missing or invalid API keys
- MongoDB connection failures
- Invalid requests (empty messages)
- Session timeouts
- Database errors with informative error responses

## Development

### Running Tests
```bash
# Add pytest to your environment first
uv pip install pytest pytest-asyncio
pytest
```

### Code Structure
- `main.py` - Main application file containing:
  - Database configuration
  - Agent setup and instructions
  - FastAPI routes
  - Session management logic
  - Property search and scoring logic
- `properties.json` - Sample property data
- `pyproject.toml` - Project metadata and dependencies
- `.env` - Environment configuration (not committed)

## License

This project is open source. Check the repository for license details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues, questions, or suggestions, please open an issue on the GitHub repository.

---

**Built with ❤️ by 167AliRaza**
