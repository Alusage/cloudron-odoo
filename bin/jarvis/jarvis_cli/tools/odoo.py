"""
Odoo Helper - Database operations, backup, restore
Compatible with official Odoo backup format
"""

import os
import json
import subprocess
import tempfile
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from .cli import (
    print_step,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_commands,
    with_progress_bar,
    run_command,
)


class OdooHelper:
    """Helper class for Odoo database operations"""

    def __init__(self, config):
        """
        Initialize with JarvisConfig

        Args:
            config: JarvisConfig instance
        """
        self.config = config

    def _get_pg_version(self, database: Optional[str] = None) -> str:
        """Get PostgreSQL server version"""
        db = database or self.config.default_database
        cmd = "psql -t -c 'SHOW server_version;'"

        result = subprocess.run(
            cmd,
            shell=True,
            env={**os.environ, **self.config.get_pg_env()},
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            # Extract major.minor
            parts = version.split('.')
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}"
            return parts[0]
        return "unknown"

    def _get_installed_modules(self, database: Optional[str] = None) -> Dict[str, str]:
        """Get installed Odoo modules with versions"""
        db = database or self.config.default_database
        cmd = f"psql -t -A -F '|' -c \"SELECT name, latest_version FROM ir_module_module WHERE state = 'installed'\" {db}"

        result = subprocess.run(
            cmd,
            shell=True,
            env={**os.environ, **self.config.get_pg_env()},
            capture_output=True,
            text=True,
        )

        modules = {}
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    name, version = line.split('|', 1)
                    modules[name.strip()] = version.strip()
        return modules

    def _get_odoo_version(self) -> Tuple[str, list, str]:
        """Get Odoo version info from environment or release file"""
        # Try environment variable first
        version = os.environ.get('ODOO_VERSION', '')

        if not version:
            # Try to read from odoo release
            release_file = self.config.odoo_dir / 'odoo' / 'release.py'
            if release_file.exists():
                try:
                    with open(release_file) as f:
                        content = f.read()
                        for line in content.split('\n'):
                            if line.startswith('version ='):
                                version = line.split('=')[1].strip().strip("'\"")
                                break
                except:
                    pass

        if not version:
            version = "18.0"  # Default fallback

        # Parse version info
        major = version.split('.')[0]
        version_info = [int(major), 0, 0, "final", 0]
        major_version = f"{major}.0"

        return version, version_info, major_version

    def _generate_manifest(self, database: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate Odoo-compatible manifest.json content

        This matches the format from odoo/service/db.py dump_db_manifest()
        """
        db = database or self.config.default_database
        version, version_info, major_version = self._get_odoo_version()
        pg_version = self._get_pg_version(db)
        modules = self._get_installed_modules(db)

        manifest = {
            "odoo_dump": "1",
            "db_name": db,
            "version": version,
            "version_info": version_info,
            "major_version": major_version,
            "pg_version": pg_version,
            "modules": modules,
        }

        return manifest

    def pg_dump(self, output_file: Path, database: Optional[str] = None,
                format_type: str = "text") -> bool:
        """
        Dump PostgreSQL database

        Args:
            output_file: Path to output SQL file
            database: Database name (default: from config)
            format_type: "text" for plain SQL (Odoo ZIP), "custom" for pg_dump -Fc

        Returns:
            True if successful
        """
        db = database or self.config.default_database

        print_step(f"Dumping database '{db}'...")

        if format_type == "custom":
            # Custom format for standalone dumps
            cmd = f"pg_dump --no-owner --no-acl --format=c {db} -f {output_file}"
        else:
            # Text format for Odoo-compatible ZIP (default)
            cmd = f"pg_dump --no-owner --no-acl {db} -f {output_file}"

        print_commands([cmd])

        result = subprocess.run(
            cmd,
            shell=True,
            env={**os.environ, **self.config.get_pg_env()},
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            size = output_file.stat().st_size / (1024 * 1024)
            print_success(f"Database dumped: {output_file} ({size:.2f} MB)")
            return True
        else:
            print_error(f"pg_dump failed: {result.stderr}")
            return False

    def _is_custom_format(self, dump_file: Path) -> bool:
        """Check if dump file is in PostgreSQL custom format"""
        try:
            with open(dump_file, 'rb') as f:
                # Custom format starts with "PGDMP"
                header = f.read(5)
                return header == b'PGDMP'
        except:
            return False

    def pg_restore(self, dump_file: Path, database: Optional[str] = None) -> bool:
        """
        Restore PostgreSQL database from dump

        Automatically detects format (text SQL or custom) and uses
        appropriate restore command.

        Args:
            dump_file: Path to SQL dump file
            database: Database name (default: from config)

        Returns:
            True if successful
        """
        db = database or self.config.default_database

        print_step(f"Restoring database '{db}'...")

        # On managed PostgreSQL (Cloudron), the app user can't dropdb/createdb
        # (no rights on template1, no CREATEDB role). Instead we wipe every
        # non-system schema in-place inside the existing DB and reload the
        # dump into it. This also works on standalone PG, so we always take
        # this path.
        # NB: piped via stdin (not -c) so the shell doesn't expand $$ — the
        # PL/pgSQL block-quote delimiter — into the shell PID.
        reset_sql = (
            "DO $reset$ DECLARE r record; BEGIN "
            "FOR r IN (SELECT nspname FROM pg_namespace "
            "WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') "
            "AND nspname NOT LIKE 'pg\\_%' ESCAPE '\\') LOOP "
            "EXECUTE 'DROP SCHEMA ' || quote_ident(r.nspname) || ' CASCADE'; "
            "END LOOP; END $reset$; "
            "CREATE SCHEMA public; "
            "GRANT ALL ON SCHEMA public TO public;"
        )

        # Detect format and choose restore command
        is_custom = self._is_custom_format(dump_file)

        if is_custom:
            restore_cmd = f"pg_restore --no-owner --no-acl -d {db} {dump_file}"
        else:
            # Text SQL format - use psql (Odoo standard)
            restore_cmd = f"psql -q -f {dump_file} {db}"

        print_commands([
            f"# Wipe non-system schemas in '{db}' (in-place reset)",
            restore_cmd,
        ])

        pg_env = {**os.environ, **self.config.get_pg_env()}

        # Reset schemas in place — feed SQL via stdin to avoid shell quoting.
        result = subprocess.run(
            ["psql", "-q", "-d", db],
            input=reset_sql,
            env=pg_env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_error(f"Schema reset failed: {result.stderr}")
            return False

        # Restore
        result = subprocess.run(restore_cmd, shell=True, env=pg_env, capture_output=True, text=True)
        if result.returncode != 0:
            # pg_restore/psql may return non-zero even on success (warnings)
            if "error" in result.stderr.lower() and "warning" not in result.stderr.lower():
                print_error(f"Restore failed: {result.stderr}")
                return False
            elif result.stderr:
                print_warning(f"Restore warnings: {result.stderr[:200]}")

        print_success(f"Database '{db}' restored successfully")
        return True

    def backup(
        self,
        output_path: Optional[Path] = None,
        database: Optional[str] = None,
        db_only: bool = False,
    ) -> Optional[Path]:
        """
        Create a full Odoo backup (database + filestore)

        Creates an Odoo-compatible ZIP containing:
        - manifest.json: Odoo metadata (version, modules, etc.)
        - dump.sql: PostgreSQL dump in TEXT format
        - filestore/: Odoo filestore (unless db_only)

        Args:
            output_path: Output ZIP file path
            database: Database name
            db_only: Only backup database (no filestore)

        Returns:
            Path to backup file or None if failed
        """
        db = database or self.config.default_database
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if output_path is None:
            suffix = "db" if db_only else "full"
            output_path = self.config.backup_dir / f"{db}_{timestamp}_{suffix}.zip"

        # Ensure backup directory exists
        self.config.ensure_backup_dir()

        print_step(f"Creating {'database-only' if db_only else 'full'} Odoo backup...")
        print_info(f"Database: {db}")
        print_info(f"Output: {output_path}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Generate manifest.json (Odoo format)
            print_step("Generating manifest.json...")
            manifest = self._generate_manifest(db)
            manifest_file = tmp_path / "manifest.json"
            with open(manifest_file, 'w') as f:
                json.dump(manifest, f, indent=4)
            print_info(f"Odoo version: {manifest.get('version', 'unknown')}")
            print_info(f"Modules: {len(manifest.get('modules', {}))} installed")

            # Dump database in TEXT format (Odoo standard)
            dump_file = tmp_path / "dump.sql"
            if not self.pg_dump(dump_file, db, format_type="text"):
                return None

            # Create ZIP with Odoo-compatible structure
            print_step("Creating ZIP archive...")

            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add manifest first
                zf.write(manifest_file, "manifest.json")

                # Add database dump
                zf.write(dump_file, "dump.sql")

                # Add filestore if not db_only
                if not db_only:
                    filestore = self.config.filestore_dir / db
                    if filestore.exists():
                        print_info(f"Adding filestore: {filestore}")
                        file_count = 0
                        for root, dirs, files in os.walk(filestore):
                            for file in files:
                                file_path = Path(root) / file
                                arc_name = f"filestore/{file_path.relative_to(filestore)}"
                                zf.write(file_path, arc_name)
                                file_count += 1
                        print_info(f"Added {file_count} files from filestore")
                    else:
                        print_warning(f"Filestore not found: {filestore}")

        size = output_path.stat().st_size / (1024 * 1024)
        print_success(f"Backup created: {output_path} ({size:.2f} MB)")
        print_info("Format: Odoo-compatible ZIP (manifest.json + dump.sql + filestore)")

        return output_path

    def restore(
        self,
        backup_file: Path,
        database: Optional[str] = None,
        db_only: bool = False,
        merge_filestore: bool = False,
    ) -> bool:
        """
        Restore an Odoo backup

        Supports both Odoo-format ZIPs (manifest.json + dump.sql) and
        legacy formats (just dump.sql).

        Args:
            backup_file: Path to backup ZIP file
            database: Database name
            db_only: Only restore database
            merge_filestore: Merge filestore with existing (rsync style)

        Returns:
            True if successful
        """
        db = database or self.config.default_database

        print_step(f"Restoring backup from {backup_file}...")
        print_info(f"Database: {db}")
        print_info(f"Mode: {'DB only' if db_only else 'Merge filestore' if merge_filestore else 'Full replace'}")

        if not backup_file.exists():
            print_error(f"Backup file not found: {backup_file}")
            return False

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Check if it's a ZIP or raw dump
            if zipfile.is_zipfile(backup_file):
                # Extract ZIP
                print_step("Extracting backup archive...")
                with zipfile.ZipFile(backup_file, 'r') as zf:
                    # Only extract known members (security)
                    members = zf.namelist()
                    safe_members = ['dump.sql', 'manifest.json'] + \
                                   [m for m in members if m.startswith('filestore/')]
                    for member in safe_members:
                        if member in members:
                            zf.extract(member, tmp_path)

                # Show manifest info if present
                manifest_file = tmp_path / "manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file) as f:
                            manifest = json.load(f)
                        print_info(f"Backup from Odoo {manifest.get('version', 'unknown')}")
                        print_info(f"Original database: {manifest.get('db_name', 'unknown')}")
                        print_info(f"Modules: {len(manifest.get('modules', {}))} installed")
                    except:
                        pass

                dump_file = tmp_path / "dump.sql"
            else:
                # Raw dump file (custom format)
                print_info("Detected raw dump file (not ZIP)")
                dump_file = backup_file

            # Restore database
            if not dump_file.exists():
                print_error("dump.sql not found in backup")
                return False

            if not self.pg_restore(dump_file, db):
                return False

            # Restore filestore (only from ZIP)
            if not db_only and zipfile.is_zipfile(backup_file):
                src_filestore = tmp_path / "filestore"
                dst_filestore = self.config.filestore_dir / db

                if src_filestore.exists():
                    print_step("Restoring filestore...")

                    if merge_filestore:
                        # Merge with rsync
                        print_info("Merging filestore (rsync)...")
                        dst_filestore.mkdir(parents=True, exist_ok=True)
                        cmd = f"rsync -av {src_filestore}/ {dst_filestore}/"
                        run_command(cmd)
                    else:
                        # Full replace
                        print_info("Replacing filestore...")
                        if dst_filestore.exists():
                            shutil.rmtree(dst_filestore)
                        shutil.copytree(src_filestore, dst_filestore)

                    print_success("Filestore restored")
                else:
                    print_warning("No filestore in backup")

        print_success(f"Backup restored to database '{db}'")
        return True

    def shell(self, database: Optional[str] = None) -> None:
        """
        Launch Odoo shell

        Args:
            database: Database name

        Note:
            We always pass ``--no-http`` because the Cloudron app already
            runs an Odoo HTTP server on 8069. Without it, ``odoo-bin shell``
            tries to bind 8069 and fails immediately with
            ``OSError: [Errno 98] Address already in use``.
        """
        db = database or self.config.default_database

        print_step(f"Starting Odoo shell for database '{db}'...")

        cmd_parts = ["python3", str(self.config.odoo_bin), "shell", "-d", db]
        if self.config.odoo_conf.exists():
            cmd_parts += ["-c", str(self.config.odoo_conf)]
        cmd_parts.append("--no-http")

        print_commands([" ".join(cmd_parts)])
        os.execvp("python3", cmd_parts)

    def update_modules(
        self,
        modules: str,
        database: Optional[str] = None,
        stop_after: bool = True,
        no_http: bool = False,
    ) -> bool:
        """
        Update Odoo modules

        Args:
            modules: "all" or comma-separated list "mod1,mod2"
            database: Database name
            stop_after: Use --stop-after-init
            no_http: Use --no-http to avoid port conflicts

        Returns:
            True if successful
        """
        db = database or self.config.default_database

        print_step(f"Updating modules: {modules}")

        cmd = [
            "python3",
            str(self.config.odoo_bin),
            "-c", str(self.config.odoo_conf),
            "-d", db,
            "-u", modules,
        ]

        if stop_after:
            cmd.append("--stop-after-init")

        if no_http:
            cmd.append("--no-http")

        print_commands([" ".join(cmd)])

        # Stream logs en direct (pas de capture_output)
        result = subprocess.run(cmd, text=True)

        return result.returncode == 0

    def install_modules(
        self,
        modules: str,
        database: Optional[str] = None,
        without_demo: bool = True,
        stop_after: bool = True,
        no_http: bool = False,
    ) -> bool:
        """
        Install Odoo modules

        Args:
            modules: Comma-separated list "mod1,mod2"
            database: Database name
            without_demo: Use --without-demo=all
            stop_after: Use --stop-after-init
            no_http: Use --no-http to avoid port conflicts

        Returns:
            True if successful
        """
        db = database or self.config.default_database

        print_step(f"Installing modules: {modules}")

        cmd = [
            "python3",
            str(self.config.odoo_bin),
            "-c", str(self.config.odoo_conf),
            "-d", db,
            "-i", modules,
        ]

        if without_demo:
            cmd.append("--without-demo=all")

        if stop_after:
            cmd.append("--stop-after-init")

        if no_http:
            cmd.append("--no-http")

        print_commands([" ".join(cmd)])

        # Stream logs en direct (pas de capture_output)
        result = subprocess.run(cmd, text=True)

        return result.returncode == 0

    def list_modules(
        self,
        database: Optional[str] = None,
        state: str = "installed",
    ) -> list:
        """
        List Odoo modules from database

        Args:
            database: Database name
            state: Module state filter: "installed", "to upgrade", "uninstalled"

        Returns:
            List of dicts with module info
        """
        db = database or self.config.default_database

        print_step(f"Querying modules (state: {state})...")

        cmd = (
            f"psql -t -A -F '|' -c "
            f"\"SELECT name, state, latest_version FROM ir_module_module "
            f"WHERE state = '{state}' ORDER BY name\" {db}"
        )

        result = subprocess.run(
            cmd,
            shell=True,
            env={**os.environ, **self.config.get_pg_env()},
            capture_output=True,
            text=True,
        )

        modules = []
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        modules.append({
                            "name": parts[0].strip(),
                            "state": parts[1].strip(),
                            "version": parts[2].strip(),
                        })

        return modules
