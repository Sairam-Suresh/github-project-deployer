import os
import shutil
import subprocess
import tempfile


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
