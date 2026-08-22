"""
Backup command - Create Odoo backups
"""

from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from .base import JarvisCommand
from ..tools import OdooHelper, print_step, print_success, print_error, print_info


class BackupCommand(JarvisCommand):
    """
    Backup command for creating Odoo backups

    Usage:
        jarvis backup                    # Full backup (DB + filestore)
        jarvis backup --db-only          # Database only
        jarvis backup --output /path     # Custom output path
    """

    def register(self):
        self.app.command(
            "backup",
            help="Create an Odoo backup (database + filestore)",
            rich_help_panel="Local Operations",
        )(self.backup)

    def backup(
        self,
        # Options
        db_only: Annotated[
            bool,
            typer.Option(
                "--db-only",
                help="Backup database only (no filestore)",
                show_default=False,
            ),
        ] = False,
        output: Annotated[
            Optional[Path],
            typer.Option(
                "--output", "-o",
                help="Output file path (default: /app/data/backups/<db>_<timestamp>.zip)",
            ),
        ] = None,
        database: Annotated[
            Optional[str],
            typer.Option(
                "--database", "-d",
                help="Database name (default: from Cloudron env)",
            ),
        ] = None,
    ):
        """
        Create an Odoo backup

        Creates a ZIP archive containing:
        - dump.sql: PostgreSQL database dump
        - filestore/: Odoo filestore (unless --db-only)
        """
        odoo = OdooHelper(self.config)

        # Use provided database or default
        db = database or self.config.default_database

        print_step("Starting Odoo backup")
        print_info(f"Database: {db}")
        print_info(f"Mode: {'Database only' if db_only else 'Full (DB + filestore)'}")
        print_info(f"Output: {output or self.config.backup_dir}")

        result = odoo.backup(
            output_path=output,
            database=db,
            db_only=db_only,
        )

        if result:
            print_success(f"Backup completed: {result}")
        else:
            print_error("Backup failed")
            raise typer.Exit(code=1)
