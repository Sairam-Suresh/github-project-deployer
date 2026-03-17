import os
import posixpath
import shutil
import subprocess
import tempfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
	Encoding,
	NoEncryption,
	PrivateFormat,
	PublicFormat,
)


KEY_DIR = os.path.expanduser(
	os.environ.get("GPD_KEY_DIR", "~/.config/github-project-deployer")
)
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, "id_ed25519")
PUBLIC_KEY_PATH = os.path.join(KEY_DIR, "id_ed25519.pub")


def get_repo_short_commit_hash(repo_dir: str | None = None) -> str:
	"""Return short commit hash for the repository, or 'unknown' if unavailable."""
	if repo_dir is None:
		repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

	try:
		return subprocess.run(
			["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"],
			check=True,
			capture_output=True,
			text=True,
		).stdout.strip()
	except Exception:
		return "unknown"


def ensure_ssh_keypair() -> None:
	"""Generate an Ed25519 SSH keypair on first run and always print the public key."""
	os.makedirs(KEY_DIR, mode=0o700, exist_ok=True)

	if not os.path.exists(PRIVATE_KEY_PATH):
		print("[ssh] No keypair found - generating a new Ed25519 keypair...")

		private_key = Ed25519PrivateKey.generate()
		private_bytes = private_key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
		public_bytes = private_key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)

		with open(PRIVATE_KEY_PATH, "wb") as f:
			f.write(private_bytes)
		os.chmod(PRIVATE_KEY_PATH, 0o600)

		with open(PUBLIC_KEY_PATH, "w") as f:
			f.write(public_bytes.decode() + " github-project-deployer\n")
		print("[ssh] Keypair generated and saved to", KEY_DIR)

	with open(PUBLIC_KEY_PATH) as f:
		pub_key = f.read().strip()

	print(
		"[ssh] Public key (add to ~/.ssh/authorized_keys on each target system):\n"
		f"\n  {pub_key}\n"
	)

def sftp_mkdir_p(sftp, remote_dir: str) -> None:
	"""Create remote_dir recursively if needed (POSIX path)."""
	parts = [p for p in remote_dir.split("/") if p]
	current = "/" if remote_dir.startswith("/") else ""
	for part in parts:
		current = posixpath.join(current, part) if current else part
		try:
			sftp.mkdir(current)
		except IOError:
			# Directory already exists (or cannot be created due to perms).
			pass


def put_dir_recursive(sftp, local_dir, remote_dir):
	remote_dir = remote_dir.replace("\\", "/").rstrip("/")
	sftp_mkdir_p(sftp, remote_dir)

	for root, dirs, files in os.walk(local_dir):
		rel_root = os.path.relpath(root, local_dir)
		remote_root = remote_dir if rel_root == "." else posixpath.join(remote_dir, rel_root.replace("\\", "/"))

		# Create remote directories
		for entry in dirs:
			remote_path = posixpath.join(remote_root, entry)
			sftp_mkdir_p(sftp, remote_path)

		# Upload files
		for entry in files:
			local_path = os.path.join(root, entry)
			remote_path = posixpath.join(remote_root, entry)
			print(f"Uploading {local_path} to {remote_path}")
			sftp.put(local_path, remote_path)

def clone_git_repo_into_target_dir_and_verify(git_repo_url: str, target_dir: str):
	"""
	Clone a git repository, verify the last commit author and GPG signature,
	then copy contents to target directory while preserving .venv if it exists.
	
	Args:
		git_repo_url: URL of the git repository to clone
		target_dir: Target directory where contents will be copied
		
	Raises:
		RuntimeError: If author verification or signature checks fail
	"""
	tmp_dir = tempfile.mkdtemp(prefix="gpd_clone_")
	try:
		print(f"[clone_git_repo_into_target_dir_and_verify] Cloning {git_repo_url} to {tmp_dir}")
		subprocess.run(["git", "clone", "--quiet", git_repo_url, tmp_dir], check=True)

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
		if "sairam" not in author_name.lower():
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
		elif signature_marker == "U":
			raise RuntimeError("Last commit is not GPG signed with a valid key")

		# Replace target_dir with new contents
		if os.path.exists(target_dir) and not os.path.isdir(target_dir):
			raise RuntimeError(f"Target path exists and is not a directory: {target_dir}")

		if not os.path.exists(target_dir):
			os.makedirs(target_dir, exist_ok=True)
		else:
			for entry in os.listdir(target_dir):
				entry_path = os.path.join(target_dir, entry)
				if os.path.isdir(entry_path) and not os.path.islink(entry_path):
					shutil.rmtree(entry_path)
				else:
					os.unlink(entry_path)

		shutil.copytree(tmp_dir, target_dir, dirs_exist_ok=True)
		print(f"[clone_git_repo_into_target_dir_and_verify] Updated {target_dir} with latest repository contents.")
	except RuntimeError as e:
		print(f"[clone_git_repo_into_target_dir_and_verify] Error occurred: {e}.")
		raise
	finally:
		shutil.rmtree(tmp_dir, ignore_errors=True)
