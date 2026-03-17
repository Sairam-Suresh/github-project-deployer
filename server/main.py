import os
import socket

from fastapi import FastAPI
import uvicorn
import tempfile
import paramiko
from utils import clone_git_repo_into_target_dir_and_verify

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

@app.get("/update/homelab_e")
def update_homelab_efficiency_server():
    print("The Homelab Efficiency Server (Raspberry Pi) is being updated...")

    with tempfile.TemporaryDirectory() as git_repo_temp_storage:
        clone_git_repo_into_target_dir_and_verify(
            git_repo_url="https://github.com/Sairam-Suresh/homelab.git",
            target_dir=git_repo_temp_storage
        )

        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            hostname = 'raspberry-pi'
            port = 22
            username = 'your_username'
            password = 'your_password'

            ssh_client.connect(hostname, port, username, password)
            sftp = ssh_client.open_sftp()

            ssh_client.exec_command("mv -r ~/homelab ~/homelab_backup")
            sftp.put(f"{git_repo_temp_storage}/control-plane", "~/homelab")
            ssh_client.exec_command("cd ~/homelab && chmod +x ./start.sh && ./start.sh")

            sftp.close()
            ssh_client.close()
        except paramiko.AuthenticationException:
            print("Authentication failed. Please verify your credentials.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "2345")),
        workers=int(os.environ.get("UVICORN_WORKERS", "2")),
    )