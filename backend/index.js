const express = require('express');
const cors = require('cors');
const OpenAI = require('openai');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors()); // Note: CORS enabled for all origins for local dev - restrict in production
app.use(express.json({ limit: '50mb' }));

// Initialize OpenAI (will be null if no API key is provided)
let openai = null;
if (process.env.OPENAI_API_KEY) {
  openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY,
  });
} else {
  console.warn('[WARNING] OPENAI_API_KEY not set - API endpoints will not work');
}

// In-memory vector index
let vectorIndex = [];

// Helper function: chunk text with overlap
function chunkText(text, chunkSize = 500, overlap = 50) {
  const chunks = [];
  let start = 0;
  
  while (start < text.length) {
    const end = Math.min(start + chunkSize, text.length);
    chunks.push(text.slice(start, end));
    start += chunkSize - overlap;
  }
  
  return chunks;
}

// Helper function: compute cosine similarity
function cosineSimilarity(a, b) {
  let dotProduct = 0;
  let normA = 0;
  let normB = 0;
  
  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  
  return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

// POST /ingest - Receive files, chunk, compute embeddings, store in index
app.post('/ingest', async (req, res) => {
  try {
    if (!openai) {
      return res.status(503).json({ error: 'OpenAI API key not configured. Please set OPENAI_API_KEY in .env file.' });
    }
    
    const { files } = req.body;
    
    if (!files || !Array.isArray(files) || files.length === 0) {
      return res.status(400).json({ error: 'No files provided' });
    }
    
    console.log(`[INGEST] Processing ${files.length} file(s)...`);
    
    // Clear previous index (intentional for demo purposes - re-ingesting replaces all data)
    // In production, you might want to implement append-only indexing or a clear endpoint
    vectorIndex = [];
    
    let totalChunks = 0;
    
    // Process each file
    for (const file of files) {
      const { name, content } = file;
      
      if (!name || !content) {
        console.log(`[INGEST] Skipping file with missing name or content`);
        continue;
      }
      
      console.log(`[INGEST] Processing file: ${name}`);
      
      // Chunk the content
      const chunks = chunkText(content);
      console.log(`[INGEST] Created ${chunks.length} chunks from ${name}`);
      
      // Compute embeddings for each chunk
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        
        try {
          const embeddingResponse = await openai.embeddings.create({
            model: 'text-embedding-ada-002',
            input: chunk,
          });
          
          const embedding = embeddingResponse.data[0].embedding;
          
          // Store in index
          vectorIndex.push({
            fileName: name,
            chunkIndex: i,
            content: chunk,
            embedding: embedding,
          });
          
          totalChunks++;
        } catch (error) {
          console.error(`[INGEST] Error computing embedding for chunk ${i} of ${name}:`, error.message);
        }
      }
    }
    
    console.log(`[INGEST] Successfully indexed ${totalChunks} chunks from ${files.length} file(s)`);
    
    res.json({
      success: true,
      message: `Successfully indexed ${totalChunks} chunks from ${files.length} file(s)`,
      totalChunks: totalChunks,
    });
    
  } catch (error) {
    console.error('[INGEST] Error:', error);
    res.status(500).json({ error: 'Internal server error during ingestion', details: error.message });
  }
});

// POST /query - Receive question, find similar chunks, call Chat Completion
app.post('/query', async (req, res) => {
  try {
    if (!openai) {
      return res.status(503).json({ error: 'OpenAI API key not configured. Please set OPENAI_API_KEY in .env file.' });
    }
    
    const { question } = req.body;
    
    if (!question) {
      return res.status(400).json({ error: 'No question provided' });
    }
    
    if (vectorIndex.length === 0) {
      return res.status(400).json({ 
        error: 'No documents indexed. Please upload and ingest files first.',
      });
    }
    
    console.log(`[QUERY] Processing question: "${question}"`);
    
    // Compute embedding for the question
    const questionEmbeddingResponse = await openai.embeddings.create({
      model: 'text-embedding-ada-002',
      input: question,
    });
    
    const questionEmbedding = questionEmbeddingResponse.data[0].embedding;
    
    // Find top-k similar chunks
    const k = 3;
    const similarities = vectorIndex.map((item, index) => ({
      index,
      similarity: cosineSimilarity(questionEmbedding, item.embedding),
      ...item,
    }));
    
    // Sort by similarity (descending) and take top-k
    similarities.sort((a, b) => b.similarity - a.similarity);
    const topChunks = similarities.slice(0, k);
    
    console.log(`[QUERY] Top ${k} similar chunks found`);
    topChunks.forEach((chunk, i) => {
      console.log(`  ${i + 1}. ${chunk.fileName} (chunk ${chunk.chunkIndex}), similarity: ${chunk.similarity.toFixed(4)}`);
    });
    
    // Build context from top chunks
    const context = topChunks
      .map(chunk => `From ${chunk.fileName}:\n${chunk.content}`)
      .join('\n\n---\n\n');
    
    // Call OpenAI Chat Completion
    const chatResponse = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'You are a helpful assistant that answers questions based on the provided context. If the context does not contain enough information to answer the question, say so clearly.',
        },
        {
          role: 'user',
          content: `Context:\n${context}\n\nQuestion: ${question}`,
        },
      ],
      temperature: 0.7,
      max_tokens: 500,
    });
    
    const answer = chatResponse.choices[0].message.content;
    
    console.log(`[QUERY] Generated answer: ${answer.substring(0, 100)}...`);
    
    res.json({
      answer: answer,
      sources: topChunks.map(chunk => ({
        fileName: chunk.fileName,
        chunkIndex: chunk.chunkIndex,
        similarity: chunk.similarity,
      })),
    });
    
  } catch (error) {
    console.error('[QUERY] Error:', error);
    res.status(500).json({ error: 'Internal server error during query', details: error.message });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    indexedChunks: vectorIndex.length,
    timestamp: new Date().toISOString(),
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`[SERVER] Certina AI Chatbot Backend running on http://localhost:${PORT}`);
  console.log(`[SERVER] Endpoints available:`);
  console.log(`  - POST /ingest - Upload and index documents`);
  console.log(`  - POST /query - Query indexed documents`);
  console.log(`  - GET /health - Health check`);
  
  if (!process.env.OPENAI_API_KEY) {
    console.warn('[WARNING] OPENAI_API_KEY not found in environment variables!');
    console.warn('[WARNING] Please set it in a .env file or environment before using the endpoints.');
  }
});
