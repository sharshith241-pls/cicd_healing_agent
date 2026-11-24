#!/usr/bin/env python3
import os
import http.server
import socketserver
from pathlib import Path

# Serve files from the directory containing this launcher so the project can
# be moved without requiring a source-code change.
os.chdir(Path(__file__).resolve().parent)

PORT = 8000
Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Working directory: {os.getcwd()}")
    print(f"Serving on http://localhost:{PORT}")
    print(f"Frontend available at: http://localhost:{PORT}/frontend.html")
    httpd.serve_forever()
