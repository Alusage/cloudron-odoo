"""
SSH Helper - Remote operations via SSH/SCP
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

from .cli import (
    print_step,
    print_success,
    print_error,
    print_warning,
    print_info,
    with_progress_bar,
)


class SSHHelper:
    """Helper class for SSH/SCP operations"""

    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        key_file: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize SSH connection parameters

        Args:
            host: Remote host
            user: SSH user
            port: SSH port
            key_file: Path to private key file
            password: SSH password (if no key)
        """
        if not HAS_PARAMIKO:
            raise ImportError("paramiko is required for SSH operations. Install with: pip install paramiko")

        self.host = host
        self.user = user
        self.port = port
        self.key_file = key_file
        self.password = password
        self._client: Optional[paramiko.SSHClient] = None

    def connect(self) -> bool:
        """
        Establish SSH connection

        Returns:
            True if connected successfully
        """
        print_step(f"Connecting to {self.user}@{self.host}:{self.port}...")

        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.user,
            }

            if self.key_file:
                connect_kwargs["key_filename"] = self.key_file
            elif self.password:
                connect_kwargs["password"] = self.password
            else:
                # Try default SSH agent
                connect_kwargs["allow_agent"] = True
                connect_kwargs["look_for_keys"] = True

            self._client.connect(**connect_kwargs)
            print_success(f"Connected to {self.host}")
            return True

        except Exception as e:
            print_error(f"SSH connection failed: {e}")
            return False

    def disconnect(self):
        """Close SSH connection"""
        if self._client:
            self._client.close()
            self._client = None

    def exec_command(self, cmd: str) -> Tuple[int, str, str]:
        """
        Execute command on remote host

        Args:
            cmd: Command to execute

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not self._client:
            raise RuntimeError("Not connected")

        print_info(f"Remote: {cmd}")

        stdin, stdout, stderr = self._client.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()

        return exit_code, stdout.read().decode(), stderr.read().decode()

    def download(self, remote_path: str, local_path: Path) -> bool:
        """
        Download file from remote host via SCP

        Args:
            remote_path: Path on remote host
            local_path: Local destination path

        Returns:
            True if successful
        """
        if not self._client:
            raise RuntimeError("Not connected")

        print_step(f"Downloading {remote_path}...")

        try:
            sftp = self._client.open_sftp()

            # Get file size for progress bar
            remote_stat = sftp.stat(remote_path)
            total_size = remote_stat.st_size

            def download_action(progress, task_id):
                def callback(transferred, total):
                    progress.update(task_id, completed=transferred)

                sftp.get(remote_path, str(local_path), callback=callback)

            with_progress_bar(f"Downloading {Path(remote_path).name}", total_size, download_action)

            sftp.close()
            print_success(f"Downloaded to {local_path}")
            return True

        except Exception as e:
            print_error(f"Download failed: {e}")
            return False

    def upload(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload file to remote host via SCP

        Args:
            local_path: Local file path
            remote_path: Path on remote host

        Returns:
            True if successful
        """
        if not self._client:
            raise RuntimeError("Not connected")

        print_step(f"Uploading {local_path}...")

        try:
            sftp = self._client.open_sftp()

            # Get file size for progress bar
            total_size = local_path.stat().st_size

            def upload_action(progress, task_id):
                def callback(transferred, total):
                    progress.update(task_id, completed=transferred)

                sftp.put(str(local_path), remote_path, callback=callback)

            with_progress_bar(f"Uploading {local_path.name}", total_size, upload_action)

            sftp.close()
            print_success(f"Uploaded to {remote_path}")
            return True

        except Exception as e:
            print_error(f"Upload failed: {e}")
            return False

    def remote_backup(
        self,
        database: str,
        output_path: Path,
        master_password: str,
        db_only: bool = False,
    ) -> bool:
        """
        Create backup on remote Odoo instance via SSH

        Args:
            database: Database name
            output_path: Local path to save backup
            master_password: Odoo master password
            db_only: Only backup database

        Returns:
            True if successful
        """
        if not self._client:
            raise RuntimeError("Not connected")

        print_step(f"Creating remote backup of '{database}'...")

        # Create backup on remote
        backup_format = "dump" if db_only else "zip"
        remote_tmp = f"/tmp/odoo_backup_{database}.{backup_format}"

        # Use odoo-bin to create backup
        cmd = f"python3 /app/odoo/odoo-bin db backup {database} {remote_tmp}"
        if db_only:
            cmd += " --format=dump"

        exit_code, stdout, stderr = self.exec_command(cmd)

        if exit_code != 0:
            print_error(f"Remote backup failed: {stderr}")
            return False

        # Download backup
        if not self.download(remote_tmp, output_path):
            return False

        # Cleanup remote
        self.exec_command(f"rm -f {remote_tmp}")

        return True

    def remote_restore(
        self,
        backup_file: Path,
        database: str,
        master_password: str,
        db_only: bool = False,
        merge_filestore: bool = False,
    ) -> bool:
        """
        Restore backup to remote Odoo instance via SSH

        Args:
            backup_file: Local backup file path
            database: Database name
            master_password: Odoo master password
            db_only: Only restore database
            merge_filestore: Merge filestore

        Returns:
            True if successful
        """
        if not self._client:
            raise RuntimeError("Not connected")

        print_step(f"Restoring backup to remote '{database}'...")

        # Upload backup
        remote_tmp = f"/tmp/{backup_file.name}"
        if not self.upload(backup_file, remote_tmp):
            return False

        # Restore on remote
        cmd = f"python3 /app/odoo/odoo-bin db restore {database} {remote_tmp}"
        if db_only:
            cmd += " --db-only"

        exit_code, stdout, stderr = self.exec_command(cmd)

        # Cleanup remote
        self.exec_command(f"rm -f {remote_tmp}")

        if exit_code != 0:
            print_error(f"Remote restore failed: {stderr}")
            return False

        print_success(f"Backup restored to remote database '{database}'")
        return True

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
