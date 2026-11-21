import os
import sys
import webbrowser
import threading
import time
import uvicorn

def open_browser():
    time.sleep(1.2)
    print("\nOpening web dashboard at http://localhost:8000 ...")
    webbrowser.open("http://localhost:8000")

def main():
    print("=" * 60)
    print(" Zepp Health Data Bridge & Probe Server")
    print("=" * 60)
    print("Starting server on http://localhost:8000 ...")
    
    # Launch browser automatically in a background thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Start FastAPI server
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False, app_dir=os.path.dirname(__file__))

if __name__ == "__main__":
    main()
