import os
import socket

from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

@app.get("/update")
def reload_server():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect("/tmp/github-project-deployer.sock")
        sock.sendall(b"update")
    finally:
        sock.close()
    return {"status": "reload message sent"}

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "2345")),
        workers=int(os.environ.get("UVICORN_WORKERS", "2")),
    )