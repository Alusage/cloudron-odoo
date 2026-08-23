"""
Base command class for Jarvis CLI
Inspired by brainkeys architecture
"""

import subprocess
from abc import ABC, abstractmethod
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from ..config import JarvisConfig


class JarvisCommand(ABC):
    """
    Base class for all Jarvis commands

    Each command must implement:
    - register(): Register typer commands
    """

    def __init__(self, config: JarvisConfig):
        """
        Initialize command with config

        Args:
            config: JarvisConfig instance
        """
        self.config = config
        self.app = typer.Typer()
        self.console = Console()
        self.register()

    @abstractmethod
    def register(self):
        """Register typer commands - must be implemented by subclasses"""
        raise NotImplementedError

    def print_commands(self, commands: List[str], cwd: Optional[str] = None):
        """
        Print commands that will be executed (brainkeys style)

        Args:
            commands: List of commands
            cwd: Working directory
        """
        table = Table(show_header=False, style="bright_black", border_style="bright_black")

        if cwd:
            table.add_row(f"[italic]$ cd {cwd}[/italic]")

        for cmd in commands:
            table.add_row(f"[italic]$ {cmd}[/italic]")

        self.console.print(table)
        self.console.print()

    def run_subprocess(
        self,
        commands: List[str],
        cwd: Optional[str] = None,
        shell: bool = True,
        text: bool = True,
        capture_output: bool = False,
        check: bool = False,
        env: Optional[dict] = None,
    ):
        """
        Run subprocess commands (brainkeys style)

        Args:
            commands: List of commands to run
            cwd: Working directory
            shell: Use shell
            text: Text mode
            capture_output: Capture output
            check: Check return code
            env: Environment variables
        """
        import os

        self.print_commands(commands, cwd)

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        for cmd in commands:
            subprocess.run(
                cmd,
                cwd=cwd,
                shell=shell,
                text=text,
                capture_output=capture_output,
                check=check,
                env=full_env,
            )
