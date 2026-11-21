import os
import sys
import subprocess

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    print("=" * 65)
    print(" ⚡ Amazfit Health Lens — ChatGPT MCP Server Launcher")
    print("=" * 65)
    print("Starting MCP Server over SSE on port 8001 ...")
    print("\n[NEXT STEP TO CONNECT TO CHATGPT]:")
    print("1. In another terminal, expose port 8001 via a free HTTPS tunnel:")
    print("   npx localtunnel --port 8001")
    print("   (Or with ngrok: ngrok http 8001)")
    print("\n2. In ChatGPT's 'Add custom MCP server' dialog:")
    print("   - Name: Amazfit Health Lens")
    print("   - Connection: Server URL")
    print("   - URL: https://<your-tunnel-url>/sse")
    print("   - Authentication: None")
    print("=" * 65 + "\n")
    
    cmd = [sys.executable, os.path.join(CURRENT_DIR, "mcp_server.py"), "--transport", "sse", "--port", "8001"]
    subprocess.run(cmd)

if __name__ == "__main__":
    main()
