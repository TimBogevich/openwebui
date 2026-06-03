# -*- coding: utf-8 -*-
"""
Auto-parse-on-upload watcher for ГЦУ Excel reports.

Watches a folder; whenever a new/changed .xlsx appears, it runs the parser
(parse_gtsu_excel.py) to ingest it into the local PostgreSQL `gtsu_search`
table. So "attach the Excel → it auto-loads into the DB the assistant queries".

No external deps (pure stdlib polling) — works alongside the Open WebUI venv.

Usage:

    set PGHOST=127.0.0.1
    set PGPORT=5432
    set PGUSER=postgres
    set PGPASSWORD=...
    set PGDATABASE=postgres
    python watch_uploads.py [WATCH_DIR]

WATCH_DIR defaults to ./gcu_inbox next to this script.

Two modes:
  * Inbox mode (default): drop ГЦУ-*.xlsx into WATCH_DIR. Processed files are
    MOVED to WATCH_DIR/_done (or _failed on error).
  * Non-destructive mode (NO_MOVE=1): files are LEFT in place and processed
    state is persisted to a JSON sidecar (.gcu_watch_state.json). Use this when
    pointing WATCH_DIR at Open WebUI's own uploads folder, where moving files
    would break Open WebUI's file references (RAG, display, downloads).

To wire it to Open WebUI uploads:
    set ONLY_GCU=1
    set NO_MOVE=1
    python watch_uploads.py c:\\llm\\openwebui\\data\\uploads
Open WebUI stores uploads as "<uuid>_<original-name>", so ONLY_GCU still matches
on the original name and the parser strips the UUID prefix for date inference.
"""
import os
import sys
import time
import json
import shutil
import subprocess

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PARSER = os.path.join(HERE, "parse_gtsu_excel.py")
WATCH_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "gcu_inbox")
DONE_DIR = os.path.join(WATCH_DIR, "_done")
FAIL_DIR = os.path.join(WATCH_DIR, "_failed")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "5"))
ONLY_GCU = os.environ.get("ONLY_GCU", "0") == "1"
NO_MOVE = os.environ.get("NO_MOVE", "0") == "1"
STATE_FILE = os.path.join(WATCH_DIR, ".gcu_watch_state.json")


def looks_like_gcu(name):
    low = name.lower()
    return ("гцу" in low) or ("gcu" in low) or ("гцу" in low)


def load_state():
    """Persisted set of already-processed (name, mtime) keys (NO_MOVE mode)."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(tuple(k) for k in json.load(f))
    except Exception:
        return set()


def save_state(seen):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump([list(k) for k in seen], f, ensure_ascii=False)
    except Exception as e:
        print(f"[state-warn] could not persist state: {e}")


def stable(path, checks=2, gap=1.0):
    """Wait until file size stops changing (upload finished)."""
    last = -1
    for _ in range(20):
        try:
            sz = os.path.getsize(path)
        except OSError:
            return False
        if sz == last:
            checks -= 1
            if checks <= 0:
                return True
        else:
            checks = 2
        last = sz
        time.sleep(gap)
    return True


def process(path):
    """Run the parser. Returns True on success. Moves the file only when not NO_MOVE."""
    name = os.path.basename(path)
    print(f"[ingest] {name} ...")
    env = dict(os.environ)
    try:
        r = subprocess.run([sys.executable, PARSER, path],
                           capture_output=True, text=True, env=env, timeout=300)
        sys.stdout.write(r.stdout)
        success = r.returncode == 0
        if not success:
            sys.stderr.write(r.stderr)
        if NO_MOVE:
            print(f"[{'ok' if success else 'fail'}] {name} (left in place)")
            return success
        dest = DONE_DIR if success else FAIL_DIR
        shutil.move(path, os.path.join(dest, name))
        print(f"[{'ok' if success else 'fail'}] {name} -> {os.path.basename(dest)}"
              + ("" if success else f" (exit {r.returncode})"))
        return success
    except Exception as e:
        print(f"[error] {name}: {e}")
        if not NO_MOVE:
            try:
                shutil.move(path, os.path.join(FAIL_DIR, name))
            except Exception:
                pass
        return False


def main():
    os.makedirs(WATCH_DIR, exist_ok=True)
    if not NO_MOVE:
        for d in (DONE_DIR, FAIL_DIR):
            os.makedirs(d, exist_ok=True)
    print(f"Watching {WATCH_DIR} (poll {POLL_SECONDS}s, only_gcu={ONLY_GCU}, no_move={NO_MOVE})")
    print(f"Parser: {PARSER}")

    # In NO_MOVE mode, processed state must survive restarts (files stay put),
    # otherwise the watcher would reparse the whole folder on every launch.
    seen = load_state() if NO_MOVE else set()
    while True:
        try:
            for name in os.listdir(WATCH_DIR):
                full = os.path.join(WATCH_DIR, name)
                if not os.path.isfile(full):
                    continue
                if not name.lower().endswith(".xlsx"):
                    continue
                if name.startswith("~$"):  # Excel lock file
                    continue
                if ONLY_GCU and not looks_like_gcu(name):
                    continue
                key = (name, os.path.getmtime(full))
                if key in seen:
                    continue
                if stable(full):
                    process(full)
                    seen.add(key)
                    if NO_MOVE:
                        save_state(seen)
        except KeyboardInterrupt:
            print("\nstopped.")
            break
        except Exception as e:
            print(f"[watch-error] {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
