import os
import socket

from fastapi import FastAPI
import uvicorn
import tempfile
import paramiko
from utils import (
    PRIVATE_KEY_PATH,
    clone_git_repo_into_target_dir_and_verify,
    ensure_ssh_keypair,
    get_repo_short_commit_hash,
    put_dir_recursive,
)

app = FastAPI()

@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "commit_short_hash": get_repo_short_commit_hash(),
    }

@app.get("/update")
def reload_server():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect("/tmp/github-project-deployer.sock")
        sock.sendall(b"update")
    finally:
        sock.close()
    return {"status": "reload message sent"}

@app.get("/update/homelab_control_plane")
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
            hostname = "100.98.133.70"
            port = 22
            username = "sairamsuresh"

            pkey = paramiko.Ed25519Key.from_private_key_file(PRIVATE_KEY_PATH)
            ssh_client.connect(hostname, port, username=username, pkey=pkey)
            sftp = ssh_client.open_sftp()

            stdin, stdout, stderr = ssh_client.exec_command("printf %s \"$HOME\"")
            remote_home = stdout.read().decode().strip() or "/home/sairamsuresh"
            remote_homelab_dir = f"{remote_home}/homelab"

            ssh_client.exec_command(f"mv -r {remote_homelab_dir} {remote_home}/homelab_backup")
            put_dir_recursive(sftp, f"{git_repo_temp_storage}/control-plane", remote_homelab_dir)
            ssh_client.exec_command(f"cd {remote_homelab_dir} && chmod +x ./start.sh && ./start.sh")

            sftp.close()
            ssh_client.close()
        except paramiko.AuthenticationException as e:
            print(e)
            print("Authentication failed. Please verify your credentials.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    ensure_ssh_keypair()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "2345")),
        workers=int(os.environ.get("UVICORN_WORKERS", "2")),
        timeout_worker_healthcheck=15
    )