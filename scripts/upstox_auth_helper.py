#!/usr/bin/env python3
"""
Upstox API OAuth2 Authentication Helper.
Starts a temporary server to handle redirect callback, fetches access token,
and writes it to .env automatically.
"""
import sys
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import webbrowser

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from data.upstox_client import make_client_from_env, UpstoxCreds, UpstoxClient
from utils.logger import setup_logger, get_logger

setup_logger(level="INFO")
log = get_logger()

# Shared server instance & auth code holder
AUTH_CODE = None
REDIRECT_PORT = 5000

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global AUTH_CODE
        # Parse query params
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        if parsed_url.path == '/callback' and 'code' in query_params:
            AUTH_CODE = query_params['code'][0]
            
            # Send successful response
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Upstox Authentication Successful</title>
                <style>
                    body {
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                        color: #ffffff;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .card {
                        background: rgba(255, 255, 255, 0.1);
                        backdrop-filter: blur(10px);
                        border-radius: 16px;
                        padding: 40px;
                        max-width: 500px;
                        text-align: center;
                        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }
                    h1 {
                        color: #4fc3f7;
                        margin-bottom: 20px;
                    }
                    p {
                        font-size: 1.1em;
                        line-height: 1.6;
                        color: #e0e0e0;
                    }
                    code {
                        background-color: rgba(0,0,0,0.3);
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-family: 'Courier New', Courier, monospace;
                        color: #ffb74d;
                    }
                    .footer {
                        margin-top: 30px;
                        font-size: 0.9em;
                        color: #b0bec5;
                    }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>Authentication Successful!</h1>
                    <p>Upstox authorization code captured successfully.</p>
                    <p>The code has been exchanged and saved to your <code>.env</code> file.</p>
                    <p>You can close this window now and return to the console.</p>
                    <div class="footer">NIFTY Options Trading System Engine</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Invalid callback parameters.")

    def log_message(self, format, *args):
        # Suppress default server logs in stderr
        pass

def run_auth_flow():
    global AUTH_CODE
    
    # Initialize Upstox client from .env credentials
    client = make_client_from_env()
    
    if not client.creds.api_key or not client.creds.api_secret:
        log.error("ERROR: UPSTOX_API_KEY and UPSTOX_API_SECRET must be set in your .env file.")
        sys.exit(1)
        
    login_url = client.build_login_url()
    
    log.info("Starting temporary HTTP callback server on port {}...", REDIRECT_PORT)
    server = HTTPServer(('localhost', REDIRECT_PORT), OAuthCallbackHandler)
    
    log.info("Opening authorization URL in browser...")
    log.info("URL: {}", login_url)
    
    webbrowser.open(login_url)
    
    print("\n" + "=" * 80)
    print("  PLEASE LOG IN TO UPSTOX VIA YOUR OPEN BROWSER TAB.")
    print("  ONCE REDIRECTED, THE ACCESS TOKEN WILL AUTOMATICALLY BE CAPTURED.")
    print("=" * 80 + "\n")
    
    # Handle single request (the redirect callback)
    server.handle_request()
    
    if AUTH_CODE:
        log.info("Authorization code received: {}", AUTH_CODE)
        log.info("Exchanging authorization code for access token...")
        success = client.exchange_code_for_token(AUTH_CODE)
        
        if success:
            log.info("✓ Success! UPSTOX_ACCESS_TOKEN has been updated in your .env file.")
            
            # Verify validity by running verification test
            from test_upstox_auth import test_upstox_auth
            print("\nVerifying the new access token...")
            if test_upstox_auth():
                log.info("✓ Token validated! Ready for Live Mode execution.")
            else:
                log.error("✗ Token validation failed. The access token might be incorrect.")
        else:
            log.error("✗ Failed to exchange authorization code for access token.")
    else:
        log.error("✗ No authorization code received.")
        
if __name__ == '__main__':
    run_auth_flow()
