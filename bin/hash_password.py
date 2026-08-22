#!/usr/bin/env python3
"""Hash password using PBKDF2-SHA512 (Odoo format)"""
import hashlib
import base64
import os
import sys
import getpass

def pbkdf2_hash(password, iterations=600000):
    """Hash password using PBKDF2-SHA512."""
    salt = os.urandom(12)
    hash_obj = hashlib.pbkdf2_hmac('sha512', password.encode(), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode().rstrip('=')
    hash_b64 = base64.b64encode(hash_obj).decode().rstrip('=')
    return f"$pbkdf2-sha512${iterations}${salt_b64}${hash_b64}"

if __name__ == '__main__':
    password = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("Password: ")
    if not password:
        print("Error: password required", file=sys.stderr)
        sys.exit(1)
    print(pbkdf2_hash(password))
