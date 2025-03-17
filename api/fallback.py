from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {
            "status": "ok",
            "message": "Fallback API is running", 
            "timestamp": str(datetime.now())
        }
        self.wfile.write(json.dumps(response).encode())
        return
        
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        # Simple fallback response
        response = {
            "response": "I'm currently experiencing high demand. Please try again in a moment."
        }
        self.wfile.write(json.dumps(response).encode()) 