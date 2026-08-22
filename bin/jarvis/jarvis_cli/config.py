"""
Jarvis Configuration - Reads Cloudron environment and .jarvis config file
"""

import os
import json
import socket
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


def _resolve_ipv4(host: str) -> str:
    """Resolve a hostname to its IPv4 address.

    Cloudron's PostgreSQL `pg_hba.conf` only contains IPv4 entries, but the
    `postgresql` hostname resolves to AAAA (IPv6) first inside the app
    container — libpq picks the IPv6 address and the connection is rejected
    with `no pg_hba.conf entry for host "fd00:..."`. Resolving to IPv4
    ourselves sidesteps the issue. Falls back to the original string if
    resolution fails (already an IP, or DNS unavailable).
    """
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET,
                                   type=socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except (socket.gaierror, OSError):
        pass
    return host


@dataclass
class JarvisConfig:
    """Configuration for Jarvis CLI, sourced from Cloudron env vars and .jarvis file"""

    # PostgreSQL (from Cloudron environment)
    pg_host: str = field(default_factory=lambda: os.environ.get("CLOUDRON_POSTGRESQL_HOST", "localhost"))
    pg_port: str = field(default_factory=lambda: os.environ.get("CLOUDRON_POSTGRESQL_PORT", "5432"))
    pg_user: str = field(default_factory=lambda: os.environ.get("CLOUDRON_POSTGRESQL_USERNAME", "odoo"))
    pg_password: str = field(default_factory=lambda: os.environ.get("CLOUDRON_POSTGRESQL_PASSWORD", ""))
    pg_database: str = field(default_factory=lambda: os.environ.get("CLOUDRON_POSTGRESQL_DATABASE", "odoo"))

    # Paths. Overridable so the same CLI works on both layouts: the jarvis
    # image (/app/odoo, /app/addons, conf in $DATA/config) and this doodba
    # image (/app/code/odoo, /app/code/auto/addons, conf at $DATA/odoo.conf).
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("CLOUDRON_DATA_DIR", "/app/data")))
    odoo_dir: Path = field(default_factory=lambda: Path(os.environ.get("JARVIS_ODOO_DIR", "/app/odoo")))
    addons_dir: Path = field(default_factory=lambda: Path(os.environ.get("JARVIS_ADDONS_DIR", "/app/addons")))
    filestore_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("JARVIS_FILESTORE_DIR")
        or Path(os.environ.get("CLOUDRON_DATA_DIR", "/app/data")) / "filestore"
    ))
    odoo_conf_path: Path = field(default_factory=lambda: Path(
        os.environ.get("JARVIS_ODOO_CONF")
        or Path(os.environ.get("CLOUDRON_DATA_DIR", "/app/data")) / "config" / "odoo.conf"
    ))

    # From .jarvis config file
    master_password: str = ""
    backup_dir: Path = field(default_factory=lambda: Path("/app/data/backups"))
    default_database: str = ""

    # Config file path
    config_file: Path = field(default_factory=lambda: Path("/app/data/.jarvis"))

    def __post_init__(self):
        """Load config from .jarvis file if it exists"""
        self._load_config_file()

        # Set default database if not configured
        if not self.default_database:
            self.default_database = self.pg_database

    def ensure_backup_dir(self):
        """Ensure backup directory exists (call before backup operations)"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _load_config_file(self):
        """Load configuration from .jarvis JSON file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)

                self.master_password = data.get("master_password", "")
                if "backup_dir" in data:
                    self.backup_dir = Path(data["backup_dir"])
                if "default_database" in data:
                    self.default_database = data["default_database"]

            except (json.JSONDecodeError, IOError) as e:
                pass  # Use defaults if config file is invalid

    def save_config(self):
        """Save current configuration to .jarvis file"""
        data = {
            "master_password": self.master_password,
            "backup_dir": str(self.backup_dir),
            "default_database": self.default_database
        }

        # Ensure parent directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)

    @property
    def filestore_path(self) -> Path:
        """Get the filestore path for the default database"""
        return self.filestore_dir / self.default_database

    @property
    def odoo_bin(self) -> Path:
        """Get the odoo-bin executable path"""
        return self.odoo_dir / "odoo-bin"

    @property
    def odoo_conf(self) -> Path:
        """Get the odoo.conf path"""
        return self.odoo_conf_path

    def get_pg_env(self) -> dict:
        """Get environment variables for PostgreSQL commands.

        PGHOST is forced to an IPv4 address so libpq doesn't pick the AAAA
        record that Cloudron's `postgresql` hostname resolves to (its
        pg_hba.conf only allows IPv4).
        """
        return {
            "PGHOST": _resolve_ipv4(self.pg_host),
            "PGPORT": self.pg_port,
            "PGUSER": self.pg_user,
            "PGPASSWORD": self.pg_password,
            "PGDATABASE": self.pg_database,
        }

    def get_connection_string(self) -> str:
        """Get PostgreSQL connection string (IPv4 host, see get_pg_env)."""
        return f"postgresql://{self.pg_user}:{self.pg_password}@{_resolve_ipv4(self.pg_host)}:{self.pg_port}/{self.pg_database}"
