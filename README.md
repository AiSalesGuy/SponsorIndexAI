# Claude Chatbot with Context

This is an embeddable chatbot that uses the Claude API and leverages pre-loaded CSV data for context-aware responses.

## Setup

### Backend Setup

1. Create a `data` directory in the backend folder and place your CSV file there as `context.csv`:
```bash
mkdir backend/data
# Copy your CSV file to backend/data/context.csv
```

2. Install Python dependencies:
```bash
cd backend
pip install -r ../requirements.txt
```

3. Create a `.env` file in the backend directory and add your Anthropic API key:
```
ANTHROPIC_API_KEY=your_api_key_here
```

4. Start the backend server:
```bash
python main.py
```

The backend server will run on `http://localhost:8000`.

### Frontend Setup

The frontend is a single HTML file that can be served from any web server or opened directly in a browser. You can find it in `frontend/index.html`.

## Embedding the Chatbot

To embed the chatbot in your website, use an iframe:

```html
<iframe 
    src="path_to_your_hosted_frontend/index.html" 
    width="100%" 
    height="600px" 
    frameborder="0"
></iframe>
```

## Features

- Pre-loaded CSV data for context
- Real-time chat interface
- Claude API integration for intelligent responses
- Responsive design
- Easy to embed in any website

## Notes

- The CSV data is loaded when the server starts
- The chatbot will only use information from the pre-loaded CSV file to answer questions
- To update the context data, replace the CSV file and restart the server 