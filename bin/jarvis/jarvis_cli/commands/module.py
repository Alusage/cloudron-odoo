"""
Module command - Install, update, and list Odoo modules
"""

from typing import Optional

import typer
from typing_extensions import Annotated

from .base import JarvisCommand
from ..tools import OdooHelper, print_step, print_info, print_success, print_error


class ModuleCommand(JarvisCommand):
    """
    Module command for managing Odoo modules

    Usage:
        jarvis update all                              # Update all modules
        jarvis update base_facturx,account_invoice_facturx  # Update specific modules
        jarvis install account_payment_method_base     # Install module
        jarvis module-list                             # List installed modules
        jarvis module-list --to-upgrade                # List modules to upgrade
    """

    def register(self):
        self.app.command(
            "update",
            help="Update Odoo modules",
            rich_help_panel="Module Management",
        )(self.update)

        self.app.command(
            "install",
            help="Install Odoo modules",
            rich_help_panel="Module Management",
        )(self.install)

        self.app.command(
            "module-list",
            help="List Odoo modules",
            rich_help_panel="Module Management",
        )(self.list_modules)

    def update(
        self,
        modules: Annotated[
            str,
            typer.Argument(
                help="Modules to update: 'all' or comma-separated list (e.g., 'base_facturx,account_invoice_facturx')",
            ),
        ],
        # Options
        database: Annotated[
            Optional[str],
            typer.Option(
                "--database", "-d",
                help="Database name (default: from Cloudron env)",
            ),
        ] = None,
        no_stop: Annotated[
            bool,
            typer.Option(
                "--no-stop",
                help="Don't use --stop-after-init (keep Odoo running)",
            ),
        ] = False,
        no_http: Annotated[
            bool,
            typer.Option(
                "--no-http",
                help="Disable HTTP server (avoid port conflicts)",
            ),
        ] = False,
    ):
        """
        Update Odoo modules

        Updates one or more Odoo modules. By default, stops Odoo after update
        and shows logs in real-time.

        Examples:
            jarvis update all
            jarvis update base_facturx,account_invoice_facturx
            jarvis update website --database prod --no-stop
        """
        odoo = OdooHelper(self.config)
        db = database or self.config.default_database

        print_step(f"Updating modules: {modules}")
        print_info(f"Database: {db}")
        print_info(f"Stop after init: {not no_stop}")

        # Update modules
        success = odoo.update_modules(
            modules=modules,
            database=db,
            stop_after=not no_stop,
            no_http=no_http,
        )

        if success:
            print_success("✅ Modules updated successfully!")
        else:
            print_error("❌ Module update failed")
            raise typer.Exit(code=1)

    def install(
        self,
        modules: Annotated[
            str,
            typer.Argument(
                help="Modules to install (comma-separated, e.g., 'base_facturx,account_invoice_facturx')",
            ),
        ],
        # Options
        database: Annotated[
            Optional[str],
            typer.Option(
                "--database", "-d",
                help="Database name (default: from Cloudron env)",
            ),
        ] = None,
        with_demo: Annotated[
            bool,
            typer.Option(
                "--with-demo",
                help="Install with demo data (default: without demo)",
            ),
        ] = False,
        no_stop: Annotated[
            bool,
            typer.Option(
                "--no-stop",
                help="Don't use --stop-after-init (keep Odoo running)",
            ),
        ] = False,
        no_http: Annotated[
            bool,
            typer.Option(
                "--no-http",
                help="Disable HTTP server (avoid port conflicts)",
            ),
        ] = False,
    ):
        """
        Install Odoo modules

        Installs one or more Odoo modules. By default, installs without demo data,
        stops Odoo after installation, and shows logs in real-time.

        Examples:
            jarvis install account_payment_method_base
            jarvis install website,website_sale --with-demo
            jarvis install l10n_fr_chorus --database prod
        """
        odoo = OdooHelper(self.config)
        db = database or self.config.default_database

        print_step(f"Installing modules: {modules}")
        print_info(f"Database: {db}")
        print_info(f"With demo data: {with_demo}")
        print_info(f"Stop after init: {not no_stop}")

        # Install modules
        success = odoo.install_modules(
            modules=modules,
            database=db,
            without_demo=not with_demo,
            stop_after=not no_stop,
            no_http=no_http,
        )

        if success:
            print_success("✅ Modules installed successfully!")
        else:
            print_error("❌ Module installation failed")
            raise typer.Exit(code=1)

    def list_modules(
        self,
        # Options
        database: Annotated[
            Optional[str],
            typer.Option(
                "--database", "-d",
                help="Database name (default: from Cloudron env)",
            ),
        ] = None,
        to_upgrade: Annotated[
            bool,
            typer.Option(
                "--to-upgrade",
                help="List only modules that need upgrade",
            ),
        ] = False,
        uninstalled: Annotated[
            bool,
            typer.Option(
                "--uninstalled",
                help="List only uninstalled modules",
            ),
        ] = False,
        installed: Annotated[
            bool,
            typer.Option(
                "--installed",
                help="List only installed modules (default)",
            ),
        ] = False,
    ):
        """
        List Odoo modules and their states

        Shows modules from the database with their current state.

        Examples:
            jarvis module-list
            jarvis module-list --to-upgrade
            jarvis module-list --uninstalled
        """
        odoo = OdooHelper(self.config)
        db = database or self.config.default_database

        # Determine filter
        if to_upgrade:
            state_filter = "to upgrade"
        elif uninstalled:
            state_filter = "uninstalled"
        elif installed:
            state_filter = "installed"
        else:
            state_filter = "installed"  # Default

        print_step(f"Listing modules (state: {state_filter})")
        print_info(f"Database: {db}")

        # List modules
        modules = odoo.list_modules(database=db, state=state_filter)

        if not modules:
            print_info(f"No modules found with state '{state_filter}'")
            return

        # Display results
        from rich.table import Table
        from rich.console import Console

        console = Console()
        table = Table(title=f"Odoo Modules ({state_filter})")
        table.add_column("Module Name", style="cyan")
        table.add_column("State", style="green")
        table.add_column("Version", style="yellow")

        for module in modules:
            table.add_row(
                module.get("name", ""),
                module.get("state", ""),
                module.get("version", ""),
            )

        console.print(table)
        print_success(f"Found {len(modules)} modules")
