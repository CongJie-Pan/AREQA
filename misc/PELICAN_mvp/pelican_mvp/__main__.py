import uvicorn

if __name__ == "__main__":
    uvicorn.run("pelican_mvp.server:app", host="127.0.0.1", port=8000)
