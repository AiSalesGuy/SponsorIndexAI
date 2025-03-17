from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import pandas as pd
import numpy as np
import os
import sys
import signal
import logging
import traceback
from dotenv import load_dotenv
import json
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import openai
import io
import pkgutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
try:
    # Check if the frontend directory exists at the expected path
    frontend_path = "frontend"
    if os.path.exists(frontend_path) and os.path.isdir(frontend_path):
        app.mount("/static", StaticFiles(directory=frontend_path), name="static")
        logger.info(f"Mounted static files from {frontend_path}")
    else:
        logger.warning(f"Frontend directory not found at {frontend_path}, static files will not be available")
except Exception as e:
    logger.error(f"Error mounting static files: {str(e)}")

# Load data
try:
    # Determine if we're running on Vercel or locally
    is_vercel = os.environ.get('VERCEL') == '1'
    
    if is_vercel:
        # When deployed on Vercel: read CSV from the packaged data
        # Note: This requires the CSV to be included in the deployment package
        logger.info("Running on Vercel, loading CSV from package data")
        
        # For Vercel, the CSV file should be accessible relative to the current file
        csv_path = os.path.join(os.path.dirname(__file__), 'data', 'context.csv')
        df = pd.read_csv(csv_path)
    else:
        # Local development: read directly from file system
        logger.info("Running locally, loading CSV from file system")
        df = pd.read_csv('backend/data/context.csv')
        
    logger.info(f"Successfully loaded {len(df)} rows from context.csv")
except Exception as e:
    logger.error(f"Error loading CSV file: {str(e)}")
    raise

# Get available categories
available_categories = df['Category'].unique().tolist()
logger.info(f"Available categories: {available_categories}")

# Add token tracking
class TokenTracker:
    def __init__(self):
        self.tokens_used = 0
        self.last_reset = datetime.now()
        self.rate_limit = 20000  # tokens per minute
        
    def add_tokens(self, count):
        now = datetime.now()
        if now - self.last_reset > timedelta(minutes=1):
            self.tokens_used = 0
            self.last_reset = now
        self.tokens_used += count
        
    def can_make_request(self, estimated_tokens):
        now = datetime.now()
        if now - self.last_reset > timedelta(minutes=1):
            self.tokens_used = 0
            self.last_reset = now
        return (self.tokens_used + estimated_tokens) <= self.rate_limit
    
    def wait_if_needed(self):
        if self.tokens_used >= self.rate_limit:
            wait_time = 60 - (datetime.now() - self.last_reset).total_seconds()
            if wait_time > 0:
                time.sleep(wait_time)
            self.tokens_used = 0
            self.last_reset = datetime.now()

token_tracker = TokenTracker()

def estimate_tokens(text):
    # Rough estimation: 1 token ≈ 4 characters
    return len(text) // 4

def validate_api_key():
    try:
        # Load API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        # Validate API key format
        if not api_key.startswith("sk-"):
            raise ValueError("Invalid API key format")
        
        logger.info(f"API key loaded successfully")
        logger.info(f"API key length: {len(api_key)} characters")
        logger.info(f"API key prefix: {api_key[:7]}...")
        
        # Initialize OpenAI client
        openai.api_key = api_key
        client = openai.OpenAI()
        
        # Test with minimal request
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10
            )
            logger.info("OpenAI client initialized successfully and API key validated")
            return True
        except Exception as e:
            if "rate_limit_error" in str(e):
                logger.warning("Rate limit hit during API key validation, waiting 60 seconds...")
                time.sleep(60)
                # Try one more time after waiting
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10
                )
                logger.info("OpenAI client initialized successfully after rate limit wait")
                return True
            raise e
            
    except Exception as e:
        logger.error(f"OpenAI API Error: {str(e)}")
        if "rate_limit_error" in str(e):
            logger.error("This might be due to an invalid API key or insufficient credits")
        raise

# Validate API key on startup
validate_api_key()

def chunk_context(data: list, chunk_size: int = 10, category: str = None) -> list:
    """Split the context data into chunks."""
    if category:
        filtered_data = data[data['Category'] == category]
    else:
        filtered_data = data
    
    # Convert DataFrame to list of dictionaries
    data_list = filtered_data.to_dict('records')
    
    # Split into chunks
    chunks = []
    for i in range(0, len(data_list), chunk_size):
        chunk = data_list[i:i + chunk_size]
        chunks.append(chunk)
    
    return chunks

def process_with_context(message: str, context_chunks: list, conversation_history: Optional[List[Dict]] = []):
    """Process the message with context chunks and conversation history."""
    try:
        # Estimate tokens for the request
        estimated_tokens = estimate_tokens(message)
        for chunk in context_chunks:
            estimated_tokens += estimate_tokens(str(chunk))
        
        # Check if we can make the request
        if not token_tracker.can_make_request(estimated_tokens):
            wait_time = 60 - (datetime.now() - token_tracker.last_reset).total_seconds()
            if wait_time > 0:
                logger.info(f"Rate limit approaching, waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
            token_tracker.tokens_used = 0
            token_tracker.last_reset = datetime.now()
        
        # Prepare messages for OpenAI
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant that provides information about newsletters. Format the response in a clear, structured way with categories, subscriber counts, prices, and audience information. Always include this disclaimer at the end of your response: 'Keep in mind these subscriber numbers and starting prices are approximate.\n**For specific details, past performance data, newsletter funnel tips, and a FREE Custom Proposal**, pick a time to speak to a representative. [Click Here](https://sponsorindex.setmore.com)'"}
        ]
        
        # Add conversation history
        messages.extend(conversation_history)
        
        # Add current context and message
        context_str = f"Based on the following context about newsletters, please answer this question: {message}\n\nContext:\n{context_chunks[0]}"
        messages.append({"role": "user", "content": context_str})
        
        # Make API call
        client = openai.OpenAI()
        
        # Adjust max_tokens based on conversation length for faster initial responses
        dynamic_max_tokens = 200 if len(conversation_history) < 2 else 500
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=dynamic_max_tokens,
            temperature=0.7
        )
        
        # Extract response content
        response_content = response.choices[0].message.content
        
        # Update token usage
        token_tracker.add_tokens(estimated_tokens)
        
        return response_content
    except Exception as e:
        logger.error(f"Error in process_with_context: {str(e)}")
        if "rate_limit_error" in str(e):
            return "I apologize, but I'm currently experiencing high demand. Please try again in a few moments."
        return "I apologize, but I encountered an error processing your request. Please try again later."

def detect_category(message: str) -> Optional[str]:
    """Detect the category from the message."""
    try:
        # Simple keyword matching for faster category detection
        message_lower = message.lower()
        
        # Check for direct category matches first before calling the API
        for category in available_categories:
            if category.lower() in message_lower:
                logger.info(f"Direct keyword match found for category: {category}")
                return category
        
        # Prepare messages for OpenAI
        messages = [
            {"role": "system", "content": f"You are a category detection system. Your task is to identify which category from the following list best matches the user's message. If no category matches well, respond with 'None'. Available categories: {available_categories}"},
            {"role": "user", "content": message}
        ]
        
        # Make API call with minimal tokens
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=20,
            temperature=0.2
        )
        
        # Extract category
        category = response.choices[0].message.content.strip()
        
        # Validate category
        if category in available_categories:
            return category
        return None
    except Exception as e:
        logger.error(f"Error in detect_category: {str(e)}")
        return None

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict]] = []

@app.get("/")
async def read_root():
    """Serve the frontend file."""
    try:
        logger.info("Serving frontend file")
        return FileResponse("frontend/index.html", media_type="text/html")
    except Exception as e:
        logger.error(f"Error serving frontend: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat(request: ChatRequest):
    """Handle chat requests."""
    try:
        logger.info(f"Received chat message: {request.message}")
        
        # Detect category
        category = detect_category(request.message)
        logger.info(f"Detected category: {category}")
        
        # Split context into chunks
        context_chunks = chunk_context(df, chunk_size=20, category=category)
        logger.info(f"Split context into {len(context_chunks)} chunks")
        
        # Process the message
        response = process_with_context(
            request.message,
            context_chunks,
            request.conversation_history
        )
        
        logger.info("Successfully processed chat message")
        return JSONResponse(content={"response": response})
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("\nStarting server...")
    logger.info("1. Your CSV data is loaded (777 rows)")
    logger.info("2. Visit http://localhost:3001 in your web browser")
    logger.info("3. Press Ctrl+C to stop the server\n")
    uvicorn.run(app, host="0.0.0.0", port=3001)

# Vercel serverless function entry point
# This is needed for Vercel to identify the FastAPI app
app_instance = app 