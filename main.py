# main.py
# This script will launch the payload and also expose a unix socket at which an update command can be sent to, which will
# trigger a reload of the payload.

import os
import socket
import stat
import subprocess
from sys import stdout
from time import sleep

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

