"""
Jarvis CLI - Main entry point
Odoo Cloudron Maintenance Tools
"""

import typer
from typing import Optional
from typing_extensions import Annotated

from rich.console import Console
from rich.panel import Panel

from . import __version__
from .config import JarvisConfig
from .commands import BackupCommand, RestoreCommand, ShellCommand, RemoteCommand, ModuleCommand
from .tools import print_info, display_config_table

# Initialize typer app
app = typer.Typer(
    name="jarvis",
    help="Jarvis - Odoo Cloudron Maintenance CLI",
    add_completion=False,
    rich_markup_mode="rich",
)

# Initialize config
config = JarvisConfig()

# Register commands
for CommandClass in [BackupCommand, RestoreCommand, ShellCommand, RemoteCommand, ModuleCommand]:
    cmd_instance = CommandClass(config)
    # Merge command app into main app
    for command in cmd_instance.app.registered_commands:
        app.registered_commands.append(command)


def version_callback(value: bool):
    """Show version and exit"""
    if value:
        console = Console()
        console.print(Panel(
            f"[bold blue]Jarvis[/bold blue] v{__version__}\n"
            "[dim]Odoo Cloudron Maintenance CLI[/dim]",
            title="Version",
            border_style="blue",
        ))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", "-v",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
    show_config: Annotated[
        bool,
        typer.Option(
            "--show-config",
            help="Show current configuration",
            show_default=False,
        ),
    ] = False,
):
    """
    Jarvis - Odoo Cloudron Maintenance CLI

    A tool for managing Odoo backups, modules, and maintenance in Cloudron environments.

    \b
    Commands:
      backup          Create an Odoo backup (database + filestore)
      restore         Restore an Odoo backup
      shell           Launch Odoo interactive shell
      update          Update Odoo modules
      install         Install Odoo modules
      module-list     List Odoo modules
      remote-backup   Backup a remote Odoo instance
      remote-restore  Restore backup to a remote Odoo instance

    \b
    Examples:
      jarvis backup                          # Full backup
      jarvis backup --db-only                # Database only
      jarvis restore backup.zip              # Restore from file
      jarvis shell                           # Open Odoo shell
      jarvis update all                      # Update all modules
      jarvis install account_payment_method_base  # Install module
      jarvis module-list --to-upgrade        # List modules to upgrade
      jarvis remote-backup https://odoo.example.com -d mydb
    """
    console = Console()

    if show_config:
        config_dict = {
            "PostgreSQL Host": config.pg_host,
            "PostgreSQL Port": config.pg_port,
            "PostgreSQL User": config.pg_user,
            "PostgreSQL Password": config.pg_password,
            "Database": config.pg_database,
            "Data Directory": str(config.data_dir),
            "Backup Directory": str(config.backup_dir),
            "Odoo Directory": str(config.odoo_dir),
            "Master Password": config.master_password or "(not set)",
        }
        display_config_table(config_dict, title="Jarvis Configuration")
        raise typer.Exit()

    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        console.print(Panel(
            "[bold blue]Jarvis[/bold blue] - Odoo Cloudron Maintenance CLI\n\n"
            "[dim]Use [bold]jarvis --help[/bold] to see available commands[/dim]",
            border_style="blue",
        ))


if __name__ == "__main__":
    app()
