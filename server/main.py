import os
import shlex
import socket

from fastapi import FastAPI, File, HTTPException, UploadFile
import uvicorn
import tempfile
import paramiko
from utils import (
    PRIVATE_KEY_PATH,
    clone_git_repo_into_target_dir_and_verify,
    ensure_ssh_keypair,
    get_repo_short_commit_hash,
    put_dir_recursive,
    run_checked_command,
    validate_services_security_opt,
)

app = FastAPI()

UPDATER_HOMELAB_CONTROL_PLANE_ADDR = os.environ.get("UPDATER_HOMELAB_CONTROL_PLANE_ADDR")
UPDATER_HOMELAB_CONTROL_PLANE_USERNAME = os.environ.get("UPDATER_HOMELAB_CONTROL_PLANE_USERNAME")
UPDATER_HOMELAB_CONTROL_PLANE_PORT = int(os.environ.get("UPDATER_HOMELAB_CONTROL_PLANE_PORT"))

UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_ADDR = os.environ.get("UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_ADDR")
UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_USERNAME = os.environ.get("UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_USERNAME")
UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_PORT = int(os.environ.get("UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_PORT"))

UPDATER_HOMELAB_S_CODER_ADDR = os.environ.get("UPDATER_HOMELAB_S_CODER_ADDR")
UPDATER_HOMELAB_S_CODER_USERNAME = os.environ.get("UPDATER_HOMELAB_S_CODER_USERNAME")
UPDATER_HOMELAB_S_CODER_PORT = int(os.environ.get("UPDATER_HOMELAB_S_CODER_PORT"))

@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "commit_short_hash": get_repo_short_commit_hash(),
    }

@app.get("/update")
def reload_server(file: UploadFile = File(None)):
    archive_name = None
    if file and getattr(file, "filename", None):
        archive_name = os.path.basename(file.filename)
        if not archive_name.endswith(".tar.gz"):
            raise HTTPException(status_code=400, detail="Uploaded file must be a .tar.gz archive")

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None

    with tempfile.TemporaryDirectory() as git_repo_temp_storage:
        clone_git_repo_into_target_dir_and_verify(
            git_repo_url="https://github.com/Sairam-Suresh/homelab.git",
            target_dir=git_repo_temp_storage
        )

        try:
            hostname = UPDATER_HOMELAB_CONTROL_PLANE_ADDR
            port = UPDATER_HOMELAB_CONTROL_PLANE_PORT
            username = UPDATER_HOMELAB_CONTROL_PLANE_USERNAME

            pkey = paramiko.Ed25519Key.from_private_key_file(PRIVATE_KEY_PATH)
            ssh_client.connect(hostname, port, username=username, pkey=pkey)

            # Always resolve remote home and open SFTP (we need SFTP to transfer the directory)
            remote_home_stdout, _ = run_checked_command(
                ssh_client,
                'printf %s "$HOME"',
                "Resolving remote home directory",
            )
            remote_home = remote_home_stdout.strip() or "/home/sairamsuresh"
            remote_archive_path = f"{remote_home}/{archive_name}" if archive_name else None
            remote_homelab_updater_dir = f"{remote_home}/homelab_updater"

            # Open SFTP regardless of whether an image archive was provided
            sftp = ssh_client.open_sftp()

            # If an archive was uploaded, push and load the podman image
            if archive_name and file is not None:
                file.file.seek(0)
                sftp.putfo(file.file, remote_archive_path)

                load_cmd = f"podman load < {shlex.quote(remote_archive_path)}"
                run_checked_command(ssh_client, f"bash -lc {shlex.quote(load_cmd)}", "Loading podman image")

            # Always update the remote directory and run the updater script
            put_dir_recursive(sftp, f"{git_repo_temp_storage}/s-homelab-updater", remote_homelab_updater_dir)

            compose_cmd = (
                f"cd {shlex.quote(remote_homelab_updater_dir)} && "
                "chmod +x ./start.sh && ./start.sh"
            )
            run_checked_command(ssh_client, f"bash -lc {shlex.quote(compose_cmd)}", "Restarting homelab updater stack")

            return {
                "status": "updated",
            }
        except paramiko.AuthenticationException as e:
            print(f"Authentication failed: {e}")
            raise HTTPException(status_code=401, detail=f"Authentication failed: {e}") from e
        except Exception as e:
            print(f"Failed to update homelab panel: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update homelab panel: {e}") from e
        finally:
            if sftp:
                sftp.close()
            ssh_client.close()

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
            hostname = UPDATER_HOMELAB_CONTROL_PLANE_ADDR
            port = UPDATER_HOMELAB_CONTROL_PLANE_PORT
            username = UPDATER_HOMELAB_CONTROL_PLANE_USERNAME

            pkey = paramiko.Ed25519Key.from_private_key_file(PRIVATE_KEY_PATH)
            ssh_client.connect(hostname, port, username=username, pkey=pkey)
            sftp = ssh_client.open_sftp()

            remote_home_stdout, _ = run_checked_command(
                ssh_client,
                'printf %s "$HOME"',
                "Resolving remote home directory",
            )
            remote_home = remote_home_stdout.strip() or "/home/sairamsuresh"
            remote_homelab_dir = f"{remote_home}/homelab"

            run_checked_command(
                ssh_client,
                f"mv {shlex.quote(remote_homelab_dir)} {shlex.quote(f'{remote_home}/homelab_backup')}",
                "Backing up existing homelab directory",
            )
            put_dir_recursive(sftp, f"{git_repo_temp_storage}/control-plane", remote_homelab_dir)
            stdout_text, stderr_text = run_checked_command(
                ssh_client,
                f"bash -lc {shlex.quote(f'cd {remote_homelab_dir} && chmod +x ./start.sh && ./start.sh')}",
                "Starting homelab control-plane",
            )
            print("STDOUT:", stdout_text)
            print("STDERR:", stderr_text)

            sftp.close()
            ssh_client.close()
        except paramiko.AuthenticationException as e:
            print(e)
            print("Authentication failed. Please verify your credentials.")
        except Exception as e:
            print(f"An error occurred: {e}")

@app.get("/update/homelab_website_admin_panel")
def update_homelab_panel(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded file name")

    archive_name = os.path.basename(file.filename)
    if not archive_name.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .tar.gz archive")

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None

    try:
        hostname = UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_ADDR
        port = UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_PORT
        username = UPDATER_HOMELAB_WEBSITE_ADMIN_PANEL_USERNAME

        pkey = paramiko.Ed25519Key.from_private_key_file(PRIVATE_KEY_PATH)
        ssh_client.connect(hostname, port, username=username, pkey=pkey)

        sftp = ssh_client.open_sftp()
        file.file.seek(0)

        remote_home_stdout, _ = run_checked_command(
            ssh_client,
            'printf %s "$HOME"',
            "Resolving remote home directory",
        )
        remote_home = remote_home_stdout.strip() or "/home/sairamsuresh"
        remote_archive_path = f"{remote_home}/{archive_name}"
        remote_homelab_dir = f"{remote_home}/homelab"

        sftp.putfo(file.file, remote_archive_path)

        load_cmd = f"podman load < {shlex.quote(remote_archive_path)}"
        run_checked_command(ssh_client, f"bash -lc {shlex.quote(load_cmd)}", "Loading podman image")

        compose_cmd = (
            f"cd {shlex.quote(remote_homelab_dir)} && "
            "podman-compose down && podman-compose up -d"
        )
        run_checked_command(ssh_client, f"bash -lc {shlex.quote(compose_cmd)}", "Restarting homelab stack")

        return {
            "status": "updated",
        }
    except paramiko.AuthenticationException as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update homelab panel: {e}") from e
    finally:
        if sftp:
            sftp.close()
        ssh_client.close()

@app.get("/update/s-coder")
def update_homelab_coder_service():
    print("The Homelab Coder Service is being updated...")

    with tempfile.TemporaryDirectory() as git_repo_temp_storage:
        clone_git_repo_into_target_dir_and_verify(
            git_repo_url="https://github.com/Sairam-Suresh/homelab.git",
            target_dir=git_repo_temp_storage,
        )

        deploy_src_dir = os.path.join(git_repo_temp_storage, "s-coder")
        compose_candidates = [
            os.path.join(deploy_src_dir, "docker-compose.yml"),
            os.path.join(deploy_src_dir, "docker-compose.yaml"),
        ]

        compose_file_path = next((path for path in compose_candidates if os.path.isfile(path)), None)
        if not compose_file_path:
            raise HTTPException(
                status_code=404,
                detail="Could not find docker-compose.yml or docker-compose.yaml in ./s-coder",
            )

        with open(compose_file_path, "r", encoding="utf-8") as f:
            compose_text = f.read()
        is_valid, reason = validate_services_security_opt(compose_text)
        if not is_valid:
            raise HTTPException(status_code=422, detail=f"Compose policy check failed: {reason}")

        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        sftp = None

        try:
            hostname = UPDATER_HOMELAB_S_CODER_ADDR
            port = UPDATER_HOMELAB_S_CODER_PORT
            username = UPDATER_HOMELAB_S_CODER_USERNAME

            pkey = paramiko.Ed25519Key.from_private_key_file(PRIVATE_KEY_PATH)
            ssh_client.connect(hostname, port, username=username, pkey=pkey)
            sftp = ssh_client.open_sftp()

            remote_home_stdout, _ = run_checked_command(
                ssh_client,
                'printf %s "$HOME"',
                "Resolving remote home directory",
            )
            remote_home = remote_home_stdout.strip() or "/home/sairamsuresh"
            remote_s_coder_dir = f"{remote_home}/homelab/"
            remote_backup_dir = f"{remote_home}/homelab_back/"

            backup_cmd = (
                f"if [ -d {shlex.quote(remote_s_coder_dir)} ]; then "
                f"rm -rf {shlex.quote(remote_backup_dir)} && "
                f"mv {shlex.quote(remote_s_coder_dir)} {shlex.quote(remote_backup_dir)}; "
                "fi"
            )
            run_checked_command(
                ssh_client,
                f"bash -lc {shlex.quote(backup_cmd)}",
                "Backing up existing s-coder directory",
            )

            put_dir_recursive(sftp, deploy_src_dir, remote_s_coder_dir)

            compose_cmd = (
                f"cd {shlex.quote(remote_s_coder_dir)} && "
                "podman-compose down && podman-compose up -d --build"
            )
            run_checked_command(
                ssh_client,
                f"bash -lc {shlex.quote(compose_cmd)}",
                "Restarting coder stack",
            )

            return {
                "status": "updated",
                "service": "s-coder",
            }
        except paramiko.AuthenticationException as e:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {e}") from e
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update homelab coder service: {e}") from e
        finally:
            if sftp:
                sftp.close()
            ssh_client.close()

if __name__ == "__main__":
    ensure_ssh_keypair()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "2345")),
        workers=int(os.environ.get("UVICORN_WORKERS", "2")),
        timeout_worker_healthcheck=15
    )