"""
Shell command - Launch Odoo interactive shell
"""

from typing import Optional

import typer
from typing_extensions import Annotated

from .base import JarvisCommand
from ..tools import OdooHelper, print_step, print_info


class ShellCommand(JarvisCommand):
    """
    Shell command for launching Odoo interactive shell

    Usage:
        jarvis shell              # Shell with default database
        jarvis shell -d mydb      # Shell with specific database
    """

    def register(self):
        self.app.command(
            "shell",
            help="Launch Odoo interactive shell",
            rich_help_panel="Local Operations",
        )(self.shell)

    def shell(
        self,
        # Options
        database: Annotated[
            Optional[str],
            typer.Option(
                "--database", "-d",
                help="Database name (default: from Cloudron env)",
            ),
        ] = None,
    ):
        """
        Launch Odoo interactive Python shell

        Opens a Python shell with Odoo environment loaded,
        allowing direct access to models and records.

        Example usage in shell:
            >>> env['res.partner'].search([])
            >>> env['sale.order'].browse(1).name
        """
        odoo = OdooHelper(self.config)

        db = database or self.config.default_database

        print_step("Starting Odoo Shell")
        print_info(f"Database: {db}")
        print_info("Type 'exit()' or Ctrl+D to quit")

        # This replaces current process
        odoo.shell(database=db)
