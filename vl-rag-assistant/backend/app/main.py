from fastapi import FastAPI

app = FastAPI(
    title="Vancouver Laser RAG Assistant API",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Vancouver Laser RAG Assistant API is running."
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }