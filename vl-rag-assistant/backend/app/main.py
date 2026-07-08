from fastapi import FastAPI, Response

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

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
