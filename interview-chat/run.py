"""Start the app: python run.py  (then open http://localhost:8000/hr)"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("interview_bot.api:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8000)))
