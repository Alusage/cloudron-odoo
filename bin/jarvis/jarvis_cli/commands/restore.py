"""
Restore command - Restore Odoo backups
"""

from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from .base import JarvisCommand
from ..tools import OdooHelper, print_step, print_success, print_error, print_info, print_warning, ask_confirm


class RestoreCommand(JarvisCommand):
    """
    Restore command for restoring Odoo backups

    Usage:
        jarvis restore backup.zip                    # Full restore
        jarvis restore backup.zip --db-only          # Database only (keep filestore)
        jarvis restore backup.zip --merge-filestore  # Merge filestore (rsync)
    """

    def register(self):
        self.app.command(
            "restore",
            help="Restore an Odoo backup",
            rich_help_panel="Local Operations",
        )(self.restore)

    def restore(
        self,
        # Argument
        backup_file: Annotated[
            Path,
            typer.Argument(
                help="Path to backup ZIP file",
                exists=True,
                readable=True,
            ),
        ],
        # Options
        db_only: Annotated[
            bool,
            typer.Option(
                "--db-only",
                help="Restore database only (keep existing filestore)",
                show_default=False,
            ),
        ] = False,
        merge_filestore: Annotated[
            bool,
            typer.Option(
                "--merge-filestore",
                help="Merge filestore with existing (rsync, keeps existing files)",
                show_default=False,
            ),
        ] = False,
        database: Annotated[
            Optional[str],
            typer.Option(
                "--database", "-d",
                help="Target database name (default: from Cloudron env)",
            ),
        ] = None,
        force: Annotated[
            bool,
            typer.Option(
                "--force", "-f",
                help="Skip confirmation prompt",
                show_default=False,
            ),
        ] = False,
    ):
        """
        Restore an Odoo backup

        Restore modes:
        - Default: Replace database AND filestore
        - --db-only: Replace database only, keep existing filestore
        - --merge-filestore: Replace database, merge filestore (rsync)
        """
        odoo = OdooHelper(self.config)

        # Use provided database or default
        db = database or self.config.default_database

        # Determine mode
        if db_only:
            mode = "Database only (keep existing filestore)"
        elif merge_filestore:
            mode = "Database + merge filestore (rsync)"
        else:
            mode = "Full restore (replace database and filestore)"

        print_step("Odoo Restore")
        print_info(f"Backup file: {backup_file}")
        print_info(f"Target database: {db}")
        print_info(f"Mode: {mode}")

        # Confirmation
        if not force:
            print_warning(f"This will overwrite database '{db}'!")
            if not ask_confirm("Do you want to continue?"):
                print_info("Restore cancelled")
                raise typer.Exit(code=0)

        result = odoo.restore(
            backup_file=backup_file,
            database=db,
            db_only=db_only,
            merge_filestore=merge_filestore,
        )

        if result:
            print_success("Restore completed successfully")
        else:
            print_error("Restore failed")
            raise typer.Exit(code=1)
