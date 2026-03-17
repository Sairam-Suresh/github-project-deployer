import os
import socket

from fastapi import FastAPI
import uvicorn
import tempfile
import paramiko
from utils import clone_git_repo_into_target_dir_and_verify, put_dir_recursive
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat
)

app = FastAPI()

# SSH key management
_KEY_DIR = os.path.expanduser(
    os.environ.get("GPD_KEY_DIR", "~/.config/github-project-deployer")
)
_PRIVATE_KEY_PATH = os.path.join(_KEY_DIR, "id_ed25519")
_PUBLIC_KEY_PATH = os.path.join(_KEY_DIR, "id_ed25519.pub")


def _ensure_ssh_keypair() -> None:
    """Generate an Ed25519 SSH keypair on first run and always print the public key."""
    os.makedirs(_KEY_DIR, mode=0o700, exist_ok=True)

    if not os.path.exists(_PRIVATE_KEY_PATH):
        print("[ssh] No keypair found — generating a new Ed25519 keypair...")

        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
        public_bytes = private_key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)

        with open(_PRIVATE_KEY_PATH, "wb") as f:
            f.write(private_bytes)
        os.chmod(_PRIVATE_KEY_PATH, 0o600)

        with open(_PUBLIC_KEY_PATH, "w") as f:
            f.write(public_bytes.decode() + " github-project-deployer\n")
        print("[ssh] Keypair generated and saved to", _KEY_DIR)

    with open(_PUBLIC_KEY_PATH) as f:
        pub_key = f.read().strip()

    print(
        "[ssh] Public key (add to ~/.ssh/authorized_keys on each target system):\n"
        f"\n  {pub_key}\n"
    )

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
            hostname = "raspberrypi"
            port = 22
            username = "sairamsuresh"

            pkey = paramiko.Ed25519Key.from_private_key_file(_PRIVATE_KEY_PATH)
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
    _ensure_ssh_keypair()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "2345")),
        workers=int(os.environ.get("UVICORN_WORKERS", "2")),
        timeout_worker_healthcheck=15
    )