"""
Backwards compatibility file for deployments expecting app.py
This simply imports the app from main.py
"""

from main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)