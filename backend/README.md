# Certina AI Chatbot Backend

Express backend for the Certina AI Chatbot that implements a RAG (Retrieval-Augmented Generation) workflow using OpenAI embeddings and Chat Completion API.

## Features

- **POST /ingest**: Upload files, create text chunks, compute embeddings, and store in an in-memory vector index
- **POST /query**: Query the indexed documents using semantic search and get AI-generated answers
- **GET /health**: Health check endpoint to verify server status and indexed chunks count

## Prerequisites

- Node.js (v14 or higher)
- npm or yarn
- OpenAI API key (get one from https://platform.openai.com/api-keys)

## Setup

1. **Install dependencies:**

```bash
cd backend
npm install
```

2. **Configure environment variables:**

Copy the `.env.example` file to `.env` and add your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env` and set your API key:

```
OPENAI_API_KEY=sk-your-actual-api-key-here
PORT=3000
```

## Running the Server

**Development mode:**

```bash
npm start
```

The server will start on `http://localhost:3000` (or the PORT specified in .env).

## API Endpoints

### POST /ingest

Upload and index files for semantic search.

**Request body:**
```json
{
  "files": [
    {
      "name": "example.txt",
      "content": "File content here..."
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully indexed 10 chunks from 1 file(s)",
  "totalChunks": 10
}
```

### POST /query

Query the indexed documents and get AI-generated answers.

**Request body:**
```json
{
  "question": "What is the main topic of the documents?"
}
```

**Response:**
```json
{
  "answer": "Based on the provided context, the main topic is...",
  "sources": [
    {
      "fileName": "example.txt",
      "chunkIndex": 0,
      "similarity": 0.8542
    }
  ]
}
```

### GET /health

Check server health and index status.

**Response:**
```json
{
  "status": "ok",
  "indexedChunks": 10,
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

## Using with the Frontend

1. Make sure the backend is running on `http://localhost:3000`
2. Open `certina-ai-chatbot.html` in your browser
3. The frontend is configured to use `API_BASE = http://localhost:3000`
4. Upload files through the UI - they will be sent to `/ingest`
5. Ask questions - they will be sent to `/query`

## Technical Details

### Text Chunking

- **Strategy**: Character-based chunking with overlap
- **Chunk size**: 500 characters
- **Overlap**: 50 characters
- This ensures context is preserved across chunks

### Vector Index

- **Storage**: In-memory (suitable for demos, resets on server restart)
- **Embedding model**: `text-embedding-ada-002` (OpenAI)
- **Similarity metric**: Cosine similarity
- **Top-k retrieval**: Returns 3 most similar chunks

### Chat Completion

- **Model**: `gpt-3.5-turbo`
- **Temperature**: 0.7
- **Max tokens**: 500
- Context is built from top-k retrieved chunks

## Important Notes

- **In-memory storage**: All indexed data is stored in memory and will be lost when the server restarts. This is intentional for simplicity and demo purposes.
- **API costs**: Each ingestion and query operation calls OpenAI APIs and incurs costs. Monitor your usage on the OpenAI platform.
- **File size limits**: The server accepts JSON payloads up to 50MB. Very large files may take longer to process.
- **CORS**: CORS is enabled for all origins. In production, restrict this to specific domains.

## Error Handling

The server includes basic error handling and logging:
- All operations are logged to the console
- Errors return appropriate HTTP status codes (400, 500)
- Missing API keys are detected on startup

## Troubleshooting

**"OPENAI_API_KEY not found" warning:**
- Make sure you created a `.env` file in the backend directory
- Verify the API key is correctly set in the `.env` file
- Restart the server after modifying `.env`

**"No documents indexed" error:**
- Upload files through the frontend first
- Check the `/health` endpoint to verify chunks are indexed
- Review server logs for ingestion errors

**Embedding or completion errors:**
- Verify your OpenAI API key is valid and has available credits
- Check the OpenAI API status page for service issues
- Review server console logs for detailed error messages
