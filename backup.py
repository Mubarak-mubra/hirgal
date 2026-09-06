#!/usr/bin/env python3
"""
Hirgal Kiro - Automatic Database Backup Script
================================================
Waxaan kaydineynaa:
  - db.sqlite3 → backups/db_YYYY-MM-DD_HH-MM.sqlite3
  - 30 maalmood ka badan lagu tirtiraa si automated ah

Run manually:
    python backup.py

Ku dar cron job si usbuucle ah (recommended):
    crontab -e
    # Habeen walba 2:00 AM
    0 2 * * * /path/to/venv/bin/python /path/to/kiro/backend/backup.py
"""

import os
import shutil
import sys
import datetime
import gzip
import logging

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "db.sqlite3")
BACKUP_DIR    = os.path.join(BASE_DIR, "backups")
KEEP_DAYS     = 30          # Xog da' ka badan 30 maalmood ayaa tirtirma
COMPRESS      = True        # Ku kaydi gzip si looga faa'idaysto boos
LOG_FILE      = os.path.join(BACKUP_DIR, "backup.log")

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(BACKUP_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def make_backup():
    if not os.path.exists(DB_PATH):
        log.error(f"Database file not found: {DB_PATH}")
        sys.exit(1)

    now       = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M")
    ext       = ".sqlite3.gz" if COMPRESS else ".sqlite3"
    dest      = os.path.join(BACKUP_DIR, f"db_{timestamp}{ext}")

    if COMPRESS:
        with open(DB_PATH, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copy2(DB_PATH, dest)

    size_kb = os.path.getsize(dest) // 1024
    log.info(f"✅  Backup created: {os.path.basename(dest)}  ({size_kb} KB)")
    return dest


def purge_old_backups():
    """Tirtir backups-yada da' ka badan KEEP_DAYS."""
    cutoff    = datetime.datetime.now() - datetime.timedelta(days=KEEP_DAYS)
    removed   = 0
    for fname in os.listdir(BACKUP_DIR):
        if not (fname.startswith("db_") and (fname.endswith(".sqlite3") or fname.endswith(".sqlite3.gz"))):
            continue
        fpath = os.path.join(BACKUP_DIR, fname)
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
        if mtime < cutoff:
            os.remove(fpath)
            log.info(f"🗑️   Purged old backup: {fname}")
            removed += 1
    if removed == 0:
        log.info(f"ℹ️   No old backups to purge (keeping last {KEEP_DAYS} days).")


def list_backups():
    """Tus dhammaan backups-yada jira."""
    files = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("db_")],
        reverse=True,
    )
    if not files:
        print("No backups found.")
        return
    print(f"\n{'Backup File':<45} {'Size':>10}")
    print("-" * 57)
    for f in files:
        fpath = os.path.join(BACKUP_DIR, f)
        size  = os.path.getsize(fpath) // 1024
        print(f"{f:<45} {size:>8} KB")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hirgal Kiro Database Backup Tool")
    parser.add_argument("--list", action="store_true", help="Show all existing backups")
    args = parser.parse_args()

    if args.list:
        list_backups()
    else:
        log.info("═══════════════════════════════════════════")
        log.info("  Hirgal Kiro — Database Backup Started")
        log.info("═══════════════════════════════════════════")
        make_backup()
        purge_old_backups()
        log.info("  Backup complete.")
        log.info("═══════════════════════════════════════════")
