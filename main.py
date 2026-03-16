# main.py
# This script will launch the payload and also expose a unix socket at which an update command can be sent to, which will
# trigger a reload of the payload.


import os
import socket
import stat
import subprocess
from sys import stdout
from time import sleep
import shutil
import tempfile
from git import Repo, GitCommandError, InvalidGitRepositoryError

SOCKET_PATH = os.environ.get("GPD_SOCKET_PATH", "/tmp/github-project-deployer.sock")


# Socket Utilities
def _cleanup_socket_file(path: str) -> None:
	# Remove an old socket left behind after an unclean shutdown.
	if not os.path.exists(path):
		return

	mode = os.lstat(path).st_mode
	if stat.S_ISSOCK(mode):
		os.unlink(path)
		return

	raise RuntimeError(f"Refusing to remove non-socket path: {path}")


def start_unix_socket_server(path: str = SOCKET_PATH, backlog: int = 5) -> socket.socket:
	_cleanup_socket_file(path)

	server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
	server.bind(path)
	server.listen(backlog)

	print(f"[main] Unix socket server listening at {path}")
	return server


# Reloading Logic
def reload_files():
    GIT_REPO_URL = "https://github.com/Sairam-Suresh/github-project-deployer.git"  # Replace with your repo
    TARGET_DIR = "/tmp/github_project_deployer_payload"
	
    tmp_dir = tempfile.mkdtemp(prefix="gpd_clone_")
    try:
        print(f"[reload_files] Cloning {GIT_REPO_URL} to {tmp_dir}")
        repo = Repo.clone_from(GIT_REPO_URL, tmp_dir)
        commit = repo.head.commit

        # Check author
        if commit.author.email != "sairam-suresh@users.noreply.github.com" and commit.author.name.lower() != "sairam-suresh":
            raise RuntimeError("Last commit not authored by sairam-suresh")

        # Check signature
        if not commit.gpgsig:
            raise RuntimeError("Last commit is not GPG signed")

        # Optionally, verify signature validity (requires git installed)
        try:
            result = repo.git.verify_commit(commit.hexsha)
            if "Good signature" not in result:
                raise RuntimeError("Commit signature is not valid")
        except GitCommandError as e:
            raise RuntimeError(f"Signature verification failed: {e}")

        # Replace TARGET_DIR with new contents
        # if os.path.exists(TARGET_DIR):
        #     shutil.rmtree(TARGET_DIR)
        # shutil.copytree(tmp_dir, TARGET_DIR, dirs_exist_ok=True)
        # print(f"[reload_files] Updated {TARGET_DIR} with latest repository contents.")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# Main Server
def serve_forever(server: socket.socket) -> None:
	process = subprocess.Popen(["python3", "server.py"], stdout=stdout, stderr=stdout)
	print("Running");
	while True:
		conn, _ = server.accept()

		with conn:
			raw_command = conn.recv(1024)
			command = raw_command.decode("utf-8", errors="ignore").strip().lower()

			if command == "update":
				print("[main] Received update command. Triggering payload reload in a second...")
				sleep(1)
				process.terminate()
				process.wait()
				reload_files();
				process = subprocess.Popen(["python", "server.py"])
				print("[main] Payload reloaded.")
				continue

			if command == "shutdown":
				print("[main] Received shutdown command. Exiting...")
				break

			conn.sendall(b"ERR: unknown command\n")


if __name__ == "__main__":
	server_socket = start_unix_socket_server()
	try:
		serve_forever(server_socket)
	finally:
		server_socket.close()
		_cleanup_socket_file(SOCKET_PATH)

