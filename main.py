from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
from api.routes import router
from models.db import init_db

app = FastAPI(title="Req-to-Code POC V2")

# Setup static files and UI
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/review", response_class=HTMLResponse)
def serve_review_ui():
    with open("static/review.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/analysis", response_class=HTMLResponse)
def serve_analysis_ui():
    with open("static/analysis.html", "r", encoding="utf-8") as f:
        return f.read()

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=5035, reload=True)
