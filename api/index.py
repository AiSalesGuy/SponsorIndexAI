from http.server import BaseHTTPRequestHandler
import json
import os
import csv
from datetime import datetime
import urllib.request
import urllib.parse

# Instead of pandas, use basic CSV processing
NEWSLETTERS = []
try:
    # Get the absolute path to the CSV file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, '..', 'backend', 'data', 'context.csv')
    
    # Load CSV data without pandas
    with open(csv_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            NEWSLETTERS.append(row)
    print(f"Successfully loaded {len(NEWSLETTERS)} newsletters")
except Exception as e:
    print(f"Error loading CSV: {str(e)}")
    # Provide some default data if CSV loading fails
    NEWSLETTERS = [
        {"Name": "Sample Tech Newsletter", "Category": "Tech", "Subscribers": "10000", "Price": "$500"},
        {"Name": "Sample Finance Newsletter", "Category": "Finance & Investing", "Subscribers": "5000", "Price": "$300"}
    ]

def search_newsletters(query, category=None):
    """Simple search function to replace pandas filtering"""
    results = []
    query = query.lower()
    
    for newsletter in NEWSLETTERS:
        # Filter by category if specified
        if category and newsletter.get('Category') != category:
            continue
        
        # Simple keyword matching
        if (query in newsletter.get('Name', '').lower() or 
            query in newsletter.get('Description', '').lower() or
            query in newsletter.get('Category', '').lower()):
            results.append(newsletter)
    
    return results[:20]  # Limit to 20 results

def call_openai_api(message, context=None):
    """Make a call to OpenAI API"""
    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return "Error: OpenAI API key not found in environment variables."
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Prepare the prompt
        system_message = "You are a helpful AI assistant that provides information about newsletters. Format the response in a clear, structured way with categories, subscriber counts, prices, and audience information. Always include this disclaimer at the end of your response: 'Keep in mind these subscriber numbers and starting prices are approximate.\n**For specific details, past performance data, newsletter funnel tips, and a FREE Custom Proposal**, pick a time to speak to a representative. [Click Here](https://sponsorindex.setmore.com)'"
        
        # Add context if available
        if context:
            context_str = "Here's information about some newsletters that might be relevant to your question:\n"
            for item in context:
                item_str = ", ".join([f"{k}: {v}" for k, v in item.items() if k != 'Description'])
                context_str += f"- {item_str}\n"
            message = f"{message}\n\nContext: {context_str}"
        
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": message}
            ],
            "max_tokens": 500
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            return response_data['choices'][0]['message']['content']
    
    except Exception as e:
        return f"I apologize, but I encountered an error: {str(e)}"

class handler(BaseHTTPRequestHandler):
    def setup_cors(self):
        """Set up CORS headers for cross-origin requests"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        self.send_response(200)
        self.setup_cors()
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/api/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.setup_cors()
            self.end_headers()
            response = {
                "status": "ok",
                "message": "API is running", 
                "timestamp": str(datetime.now()),
                "newsletters_loaded": len(NEWSLETTERS)
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            # Serve static HTML
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.setup_cors()
            self.end_headers()
            
            # Try to read the HTML file
            try:
                html_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
                with open(html_path, 'r', encoding='utf-8') as file:
                    html_content = file.read()
                self.wfile.write(html_content.encode())
            except Exception as e:
                # Fallback HTML
                html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>SponsorIndex AI</title>
                    <style>
                        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                        .chat-box { border: 1px solid #ccc; padding: 10px; height: 300px; overflow-y: auto; margin-bottom: 10px; }
                        .input-box { display: flex; }
                        input { flex-grow: 1; padding: 8px; }
                        button { padding: 8px 16px; background: #007BFF; color: white; border: none; cursor: pointer; }
                        .message { margin-bottom: 10px; }
                        .user { font-weight: bold; }
                        .error { color: red; }
                    </style>
                </head>
                <body>
                    <h1>SponsorIndex AI</h1>
                    <div class="chat-box" id="chatBox"></div>
                    <div class="input-box">
                        <input type="text" id="messageInput" placeholder="Ask about newsletters...">
                        <button id="sendButton" onclick="sendMessage()">Send</button>
                    </div>
                    <script>
                        function escapeHtml(unsafe) {
                            return unsafe
                                .replace(/&/g, "&amp;")
                                .replace(/</g, "&lt;")
                                .replace(/>/g, "&gt;")
                                .replace(/"/g, "&quot;")
                                .replace(/'/g, "&#039;");
                        }
                        
                        function sendMessage() {
                            const input = document.getElementById('messageInput');
                            const message = input.value.trim();
                            if (!message) return;
                            
                            // Disable input during processing
                            const sendButton = document.getElementById('sendButton');
                            input.disabled = true;
                            sendButton.disabled = true;
                            
                            // Add user message to chat
                            addMessage(`<span class="user">You:</span> ${escapeHtml(message)}`, false);
                            input.value = '';
                            
                            // Add typing indicator
                            const typingId = 'typing-indicator';
                            addMessage(`<span class="typing">AI is thinking...</span>`, false, typingId);
                            
                            // Call API
                            fetch('/chat', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ message })
                            })
                            .then(response => {
                                // First check if response is ok
                                if (!response.ok) {
                                    throw new Error(`Server responded with status: ${response.status}`);
                                }
                                
                                // Then check content type
                                const contentType = response.headers.get('content-type');
                                if (!contentType || !contentType.includes('application/json')) {
                                    // If not JSON, get text and throw error
                                    return response.text().then(text => {
                                        throw new Error('Received non-JSON response: ' + text.substring(0, 50) + '...');
                                    });
                                }
                                
                                return response.json();
                            })
                            .then(data => {
                                // Remove typing indicator
                                removeMessage(typingId);
                                
                                // Process markdown in response
                                let formattedResponse = data.response;
                                
                                // Basic Markdown processing
                                // Convert **bold**
                                formattedResponse = formattedResponse.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                                
                                // Convert [text](url) to links
                                formattedResponse = formattedResponse.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
                                
                                // Convert line breaks to <br>
                                formattedResponse = formattedResponse.replace(/\\n/g, '<br>');
                                formattedResponse = formattedResponse.replace(/\n/g, '<br>');
                                
                                addMessage(`<span class="ai">AI:</span> ${formattedResponse}`, true);
                            })
                            .catch(error => {
                                // Remove typing indicator
                                removeMessage(typingId);
                                
                                // Show error
                                addMessage(`<span class="error">Error: ${error.message}</span>`, false);
                                console.error('Error:', error);
                            })
                            .finally(() => {
                                // Re-enable input
                                input.disabled = false;
                                sendButton.disabled = false;
                                input.focus();
                            });
                        }
                        
                        function addMessage(html, isHtml, id) {
                            const chatBox = document.getElementById('chatBox');
                            const messageElement = document.createElement('div');
                            messageElement.className = 'message';
                            if (id) messageElement.id = id;
                            
                            if (isHtml) {
                                messageElement.innerHTML = html;
                            } else {
                                messageElement.innerHTML = html;
                            }
                            
                            chatBox.appendChild(messageElement);
                            chatBox.scrollTop = chatBox.scrollHeight;
                        }
                        
                        function removeMessage(id) {
                            const element = document.getElementById(id);
                            if (element) element.remove();
                        }
                        
                        // Allow sending by pressing Enter
                        document.getElementById('messageInput').addEventListener('keypress', function(e) {
                            if (e.key === 'Enter') sendMessage();
                        });
                    </script>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
        
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/chat':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                json_data = json.loads(post_data)
                
                message = json_data.get('message', '')
                
                # Process the message
                relevant_data = search_newsletters(message)
                response_text = call_openai_api(message, relevant_data)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.setup_cors()
                self.end_headers()
                
                # Send response
                response = {
                    "response": response_text
                }
                self.wfile.write(json.dumps(response).encode())
            except Exception as e:
                # Return error as JSON
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.setup_cors()
                self.end_headers()
                
                error_response = {
                    "error": str(e),
                    "message": "An error occurred processing your request"
                }
                self.wfile.write(json.dumps(error_response).encode())
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.setup_cors()
            self.end_headers()
            response = {"error": "Not Found"}
            self.wfile.write(json.dumps(response).encode()) 