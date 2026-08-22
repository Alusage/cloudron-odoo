"""
Remote commands - Backup/restore via HTTPS or SSH
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer
import requests
from typing_extensions import Annotated

from .base import JarvisCommand
from ..tools import (
    print_step,
    print_success,
    print_error,
    print_info,
    print_warning,
    ask_password,
    ask_confirm,
    with_progress_bar,
)
from ..tools.ssh import SSHHelper


class RemoteCommand(JarvisCommand):
    """
    Remote backup/restore commands

    Supports two modes:
    - HTTPS: Uses Odoo's /web/database/backup and /web/database/restore endpoints
    - SSH: Direct connection to remote server

    Usage:
        jarvis remote-backup https://odoo.example.com
        jarvis remote-backup user@host --ssh
        jarvis remote-restore https://odoo.example.com backup.zip
    """

    def register(self):
        self.app.command(
            "remote-backup",
            help="Backup a remote Odoo instance",
            rich_help_panel="Remote Operations",
        )(self.remote_backup)

        self.app.command(
            "remote-restore",
            help="Restore backup to a remote Odoo instance",
            rich_help_panel="Remote Operations",
        )(self.remote_restore)

    def remote_backup(
        self,
        # Argument
        target: Annotated[
            str,
            typer.Argument(
                help="Remote target: URL (https://...) or SSH (user@host)",
            ),
        ],
        # Options
        database: Annotated[
            str,
            typer.Option(
                "--database", "-d",
                help="Database name to backup",
            ),
        ] = "odoo",
        output: Annotated[
            Optional[Path],
            typer.Option(
                "--output", "-o",
                help="Output file path",
            ),
        ] = None,
        db_only: Annotated[
            bool,
            typer.Option(
                "--db-only",
                help="Backup database only (no filestore)",
                show_default=False,
            ),
        ] = False,
        ssh: Annotated[
            bool,
            typer.Option(
                "--ssh",
                help="Use SSH instead of HTTPS",
                show_default=False,
            ),
        ] = False,
        master_password: Annotated[
            Optional[str],
            typer.Option(
                "--master-password", "-p",
                help="Odoo master password (will prompt if not provided)",
            ),
        ] = None,
        ssh_key: Annotated[
            Optional[Path],
            typer.Option(
                "--ssh-key", "-k",
                help="SSH private key file",
            ),
        ] = None,
    ):
        """
        Backup a remote Odoo instance

        Two modes:
        - HTTPS (default): Uses /web/database/backup endpoint
        - SSH (--ssh): Direct connection to server
        """
        # Set default output path
        if output is None:
            suffix = "db" if db_only else "full"
            output = self.config.backup_dir / f"remote_{database}_{suffix}.zip"

        if ssh or "@" in target and not target.startswith("http"):
            self._backup_ssh(target, database, output, db_only, ssh_key, master_password)
        else:
            self._backup_https(target, database, output, db_only, master_password)

    def remote_restore(
        self,
        # Arguments
        target: Annotated[
            str,
            typer.Argument(
                help="Remote target: URL (https://...) or SSH (user@host)",
            ),
        ],
        backup_file: Annotated[
            Path,
            typer.Argument(
                help="Backup file to restore",
                exists=True,
                readable=True,
            ),
        ],
        # Options
        database: Annotated[
            str,
            typer.Option(
                "--database", "-d",
                help="Target database name",
            ),
        ] = "odoo",
        db_only: Annotated[
            bool,
            typer.Option(
                "--db-only",
                help="Restore database only",
                show_default=False,
            ),
        ] = False,
        ssh: Annotated[
            bool,
            typer.Option(
                "--ssh",
                help="Use SSH instead of HTTPS",
                show_default=False,
            ),
        ] = False,
        master_password: Annotated[
            Optional[str],
            typer.Option(
                "--master-password", "-p",
                help="Odoo master password",
            ),
        ] = None,
        ssh_key: Annotated[
            Optional[Path],
            typer.Option(
                "--ssh-key", "-k",
                help="SSH private key file",
            ),
        ] = None,
        force: Annotated[
            bool,
            typer.Option(
                "--force", "-f",
                help="Skip confirmation",
                show_default=False,
            ),
        ] = False,
    ):
        """
        Restore backup to a remote Odoo instance

        Two modes:
        - HTTPS (default): Uses /web/database/restore endpoint
        - SSH (--ssh): Direct connection to server
        """
        if not force:
            print_warning(f"This will overwrite database '{database}' on {target}!")
            if not ask_confirm("Do you want to continue?"):
                print_info("Restore cancelled")
                raise typer.Exit(code=0)

        if ssh or "@" in target and not target.startswith("http"):
            self._restore_ssh(target, backup_file, database, db_only, ssh_key, master_password)
        else:
            self._restore_https(target, backup_file, database, db_only, master_password)

    def _get_master_password(self, provided: Optional[str]) -> str:
        """Get master password from argument, config, or prompt"""
        if provided:
            return provided
        if self.config.master_password:
            print_info("Using master password from .jarvis config")
            return self.config.master_password
        return ask_password("Odoo master password")

    def _backup_https(
        self,
        url: str,
        database: str,
        output: Path,
        db_only: bool,
        master_password: Optional[str],
    ):
        """Backup via Odoo HTTPS endpoint"""
        print_step(f"Remote backup via HTTPS")
        print_info(f"URL: {url}")
        print_info(f"Database: {database}")

        master_pwd = self._get_master_password(master_password)

        # Build backup URL
        base_url = url.rstrip('/')
        backup_url = f"{base_url}/web/database/backup"

        backup_format = "dump" if db_only else "zip"

        print_step(f"Downloading backup from {backup_url}...")

        try:
            response = requests.post(
                backup_url,
                data={
                    "master_pwd": master_pwd,
                    "name": database,
                    "backup_format": backup_format,
                },
                stream=True,
                timeout=600,
            )

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')

                if 'text/html' in content_type:
                    # Probably an error page - extract useful info
                    # Need to read the streamed content
                    html_content = response.content.decode('utf-8', errors='ignore')
                    print_error("Server returned HTML instead of backup file")
                    print_info(f"Content-Type: {content_type}")

                    # Try to extract error message from HTML
                    import re

                    # Look for common Odoo error patterns
                    error_patterns = [
                        r'<div class="alert[^"]*alert-danger[^"]*"[^>]*>(.*?)</div>',
                        r'<p class="alert[^"]*">(.*?)</p>',
                        r'class="o_error_detail"[^>]*>(.*?)<',
                        r'<pre[^>]*>(.*?)</pre>',
                        r'AccessDenied|Access Denied|Wrong password|Invalid database',
                    ]

                    error_found = False
                    for pattern in error_patterns:
                        match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
                        if match:
                            error_msg = re.sub(r'<[^>]+>', '', match.group(1) if match.lastindex else match.group(0))
                            error_msg = error_msg.strip()[:200]
                            if error_msg:
                                print_error(f"Server error: {error_msg}")
                                error_found = True
                                break

                    if not error_found:
                        # Show first part of HTML for debugging
                        print_warning("Could not extract error message. HTML response (first 500 chars):")
                        print_info(html_content[:500])

                    print_info("\nPossible causes:")
                    print_info("  - Wrong master password")
                    print_info("  - Database name doesn't exist")
                    print_info("  - Database manager is disabled (list_db = False)")
                    print_info("  - Server requires authentication to access /web/database/backup")

                    raise typer.Exit(code=1)

                # Download with progress
                total_size = int(response.headers.get('content-length', 0))

                def download_action(progress, task_id):
                    with open(output, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                progress.update(task_id, advance=len(chunk))

                if total_size > 0:
                    with_progress_bar("Downloading backup", total_size, download_action)
                else:
                    # No content-length, download without progress
                    with open(output, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                size = output.stat().st_size / (1024 * 1024)
                print_success(f"Backup saved: {output} ({size:.2f} MB)")

            else:
                print_error(f"Backup failed: HTTP {response.status_code}")
                content_type = response.headers.get('content-type', '')
                print_info(f"Content-Type: {content_type}")

                if response.status_code == 404:
                    print_info("Endpoint /web/database/backup not found")
                    print_info("This may indicate database manager is disabled or URL is incorrect")
                elif response.status_code == 403:
                    print_info("Access forbidden - check master password or server configuration")
                elif response.status_code == 500:
                    print_info("Internal server error - check Odoo logs on remote server")

                # Show response body for debugging
                print_warning(f"Response body (first 500 chars):")
                print_info(response.text[:500])
                raise typer.Exit(code=1)

        except requests.exceptions.SSLError as e:
            print_error(f"SSL Error: {e}")
            print_info("The server may have a self-signed or invalid certificate")
            raise typer.Exit(code=1)
        except requests.exceptions.ConnectionError as e:
            print_error(f"Connection failed: {e}")
            print_info("Check if the URL is correct and the server is reachable")
            raise typer.Exit(code=1)
        except requests.exceptions.Timeout as e:
            print_error(f"Request timeout: {e}")
            print_info("The server took too long to respond (timeout: 600s)")
            raise typer.Exit(code=1)
        except requests.RequestException as e:
            print_error(f"Request failed: {e}")
            raise typer.Exit(code=1)

    def _restore_https(
        self,
        url: str,
        backup_file: Path,
        database: str,
        db_only: bool,
        master_password: Optional[str],
    ):
        """Restore via Odoo HTTPS endpoint"""
        print_step(f"Remote restore via HTTPS")
        print_info(f"URL: {url}")
        print_info(f"Database: {database}")
        print_info(f"Backup: {backup_file}")

        master_pwd = self._get_master_password(master_password)

        base_url = url.rstrip('/')
        restore_url = f"{base_url}/web/database/restore"

        print_step(f"Uploading backup to {restore_url}...")

        try:
            with open(backup_file, 'rb') as f:
                response = requests.post(
                    restore_url,
                    data={
                        "master_pwd": master_pwd,
                        "name": database,
                        "copy": "true",  # Don't neutralize
                    },
                    files={
                        "backup_file": (backup_file.name, f, "application/zip"),
                    },
                    timeout=1800,  # 30 min timeout for large restores
                )

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')

                if 'text/html' in content_type and 'error' in response.text.lower():
                    print_error("Restore failed - server returned error")
                    raise typer.Exit(code=1)

                print_success(f"Backup restored to '{database}' on {url}")
            else:
                print_error(f"Restore failed: HTTP {response.status_code}")
                print_error(response.text[:500])
                raise typer.Exit(code=1)

        except requests.RequestException as e:
            print_error(f"Request failed: {e}")
            raise typer.Exit(code=1)

    def _parse_ssh_target(self, target: str) -> tuple:
        """Parse SSH target (user@host:port)"""
        user = "root"
        host = target
        port = 22

        if "@" in target:
            user, host = target.split("@", 1)

        if ":" in host:
            host, port_str = host.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                pass

        return user, host, port

    def _backup_ssh(
        self,
        target: str,
        database: str,
        output: Path,
        db_only: bool,
        ssh_key: Optional[Path],
        master_password: Optional[str],
    ):
        """Backup via SSH"""
        print_step(f"Remote backup via SSH")
        print_info(f"Target: {target}")
        print_info(f"Database: {database}")

        user, host, port = self._parse_ssh_target(target)
        master_pwd = self._get_master_password(master_password)

        try:
            with SSHHelper(
                host=host,
                user=user,
                port=port,
                key_file=str(ssh_key) if ssh_key else None,
            ) as ssh:
                if ssh.remote_backup(database, output, master_pwd, db_only):
                    size = output.stat().st_size / (1024 * 1024)
                    print_success(f"Backup saved: {output} ({size:.2f} MB)")
                else:
                    raise typer.Exit(code=1)

        except Exception as e:
            print_error(f"SSH backup failed: {e}")
            raise typer.Exit(code=1)

    def _restore_ssh(
        self,
        target: str,
        backup_file: Path,
        database: str,
        db_only: bool,
        ssh_key: Optional[Path],
        master_password: Optional[str],
    ):
        """Restore via SSH"""
        print_step(f"Remote restore via SSH")
        print_info(f"Target: {target}")
        print_info(f"Database: {database}")

        user, host, port = self._parse_ssh_target(target)
        master_pwd = self._get_master_password(master_password)

        try:
            with SSHHelper(
                host=host,
                user=user,
                port=port,
                key_file=str(ssh_key) if ssh_key else None,
            ) as ssh:
                if ssh.remote_restore(backup_file, database, master_pwd, db_only):
                    print_success(f"Backup restored to '{database}' on {target}")
                else:
                    raise typer.Exit(code=1)

        except Exception as e:
            print_error(f"SSH restore failed: {e}")
            raise typer.Exit(code=1)
