"""
CLI display utilities - Progress bars, tables, colors
Inspired by brainkeys style
"""

import subprocess
from typing import Callable, Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TextColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    SpinnerColumn,
    TaskProgressColumn,
)
from rich.panel import Panel
from rich.text import Text

console = Console()


def print_step(message: str):
    """Print a step message with blue color"""
    console.print(f"[bold blue]>>> {message}[/bold blue]")


def print_success(message: str):
    """Print a success message with green checkmark"""
    console.print(f"[bold green]✅ {message}[/bold green]")


def print_error(message: str):
    """Print an error message with red cross"""
    console.print(f"[bold red]❌ {message}[/bold red]")


def print_warning(message: str):
    """Print a warning message with yellow exclamation"""
    console.print(f"[bold yellow]⚠️  {message}[/bold yellow]")


def print_info(message: str):
    """Print an info message"""
    console.print(f"[dim]ℹ️  {message}[/dim]")


def print_commands(commands: List[str], cwd: Optional[str] = None):
    """
    Print commands that will be executed in a styled table
    (brainkeys style)
    """
    table = Table(show_header=False, style="bright_black", border_style="bright_black")

    if cwd:
        table.add_row(f"[italic]$ cd {cwd}[/italic]")

    for cmd in commands:
        table.add_row(f"[italic]$ {cmd}[/italic]")

    console.print(table)
    console.print()


def with_progress_bar(tag: str, total: int, action: Callable):
    """
    Execute an action with a progress bar
    (brainkeys style)

    Args:
        tag: Description of the task
        total: Total steps/bytes
        action: Callable that receives (progress, task_id)
    """
    with Progress(
        TextColumn("   ║║"),
        SpinnerColumn(style="bold orange1"),
        TextColumn("{task.description}"),
        BarColumn(
            bar_width=50,
            complete_style="orange1",
            finished_style="bold green",
            pulse_style="dim"
        ),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        TaskProgressColumn(),
    ) as progress:
        task_id = progress.add_task(tag, total=total)
        action(progress, task_id)


def run_command(
    cmd: str,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    capture_output: bool = False,
    show_command: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a shell command with optional display

    Args:
        cmd: Command to execute
        cwd: Working directory
        env: Environment variables
        capture_output: Capture stdout/stderr
        show_command: Print command before executing
        check: Raise exception on non-zero exit

    Returns:
        CompletedProcess result
    """
    if show_command:
        print_commands([cmd], cwd)

    import os
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        env=full_env,
        capture_output=capture_output,
        text=True,
    )

    if check and result.returncode != 0:
        if capture_output:
            print_error(f"Command failed: {result.stderr}")
        raise typer.Exit(code=result.returncode)

    return result


def ask_password(prompt: str = "Master password") -> str:
    """Ask for a password interactively"""
    import getpass
    return getpass.getpass(f"{prompt}: ")


def ask_confirm(message: str, default: bool = False) -> bool:
    """Ask for confirmation"""
    return typer.confirm(message, default=default)


def display_config_table(config_dict: dict, title: str = "Configuration"):
    """Display configuration as a nice table"""
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Parameter", style="dim")
    table.add_column("Value")

    for key, value in config_dict.items():
        # Mask passwords
        if "password" in key.lower() and value:
            display_value = "***" + value[-3:] if len(value) > 3 else "***"
        else:
            display_value = str(value)
        table.add_row(key, display_value)

    console.print(table)
