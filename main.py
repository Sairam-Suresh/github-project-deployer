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
# For this to work, the file at nano ~/.config/git/allowed_signers must be configured like so:
# EMAIL <SSH HASH>

# Then, configure git:
# git config --global gpg.format ssh
# git config --global gpg.ssh.allowedSignersFile ~/.config/git/allowed_signers
def reload_files():
	GIT_REPO_URL = "https://github.com/Sairam-Suresh/github-project-deployer.git"  # Replace with your repo
	TARGET_DIR = "."

	tmp_dir = tempfile.mkdtemp(prefix="gpd_clone_")
	try:
		print(f"[reload_files] Cloning {GIT_REPO_URL} to {tmp_dir}")
		subprocess.run(["git", "clone", "--quiet", GIT_REPO_URL, tmp_dir], check=True)

		author_email = subprocess.run(
			["git", "-C", tmp_dir, "show", "-s", "--format=%ae", "HEAD"],
			check=True,
			capture_output=True,
			text=True,
		).stdout.strip()
		author_name = subprocess.run(
			["git", "-C", tmp_dir, "show", "-s", "--format=%an", "HEAD"],
			check=True,
			capture_output=True,
			text=True,
		).stdout.strip()

		# Check author
		if author_email != "sairam278.suresh@gmail.com" and author_name.lower() != "Sairam Suresh":
			raise RuntimeError("Last commit not authored by sairam-suresh")

		signature_marker = subprocess.run(
			["git", "-C", tmp_dir, "show", "-s", "--format=%G?", "HEAD"],
			check=True,
			capture_output=True,
			text=True,
		).stdout.strip()

		# Check signature marker is present (not "N" for no signature)
		if signature_marker == "N":
			raise RuntimeError("Last commit is not GPG signed")

		try:
			result = subprocess.run(
				["git", "-C", tmp_dir, "verify-commit", "HEAD"],
				check=True,
				capture_output=True,
				text=True,
			)
			verify_output = f"{result.stdout}\n{result.stderr}"
			if "Good" not in verify_output:
				raise RuntimeError("Commit signature is not valid")
		except subprocess.CalledProcessError as e:
			raise RuntimeError(f"Signature verification failed: {e}")

		# Replace TARGET_DIR with new contents
		if os.path.exists(TARGET_DIR) and not os.path.isdir(TARGET_DIR):
			raise RuntimeError(f"Target path exists and is not a directory: {TARGET_DIR}")

		if not os.path.exists(TARGET_DIR):
			os.makedirs(TARGET_DIR, exist_ok=True)
		else:
			for entry in os.listdir(TARGET_DIR):
				if entry == ".venv":
					continue
				entry_path = os.path.join(TARGET_DIR, entry)
				if os.path.isdir(entry_path) and not os.path.islink(entry_path):
					shutil.rmtree(entry_path)
				else:
					os.unlink(entry_path)

		shutil.copytree(tmp_dir, TARGET_DIR, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".venv"))
		print(f"[reload_files] Updated {TARGET_DIR} with latest repository contents.")
	except RuntimeError as e:
		print(f"[reload_files] Error occurred: {e}. Server was not reloaded.")
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
				print("[main] Payload started.")
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

