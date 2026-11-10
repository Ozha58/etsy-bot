"""Encrypted state kept inside the git repository.

The repository is public (so GitHub Actions minutes are free), therefore every
state file is encrypted with a key derived from the STATE_KEY secret.

Layout:
  state/products/<id>.enc   one file per product (daily run creates, poller updates)
  state/meta.enc            Telegram offset etc. (poller only)
  state/etsy.enc            Etsy OAuth tokens (poller / connect only)
"""
import atexit
import base64
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import config

PRODUCTS_DIR = config.STATE_DIR / "products"


def _fernet() -> Fernet:
    if not config.STATE_KEY:
        raise RuntimeError("STATE_KEY gizli anahtarı tanımlı değil (GitHub Secrets).")
    key = base64.urlsafe_b64encode(hashlib.sha256(("etsybot:" + config.STATE_KEY).encode()).digest())
    return Fernet(key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    return _fernet().decrypt(data)


def _read(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(decrypt_bytes(path.read_bytes()).decode("utf-8"))
    except InvalidToken:
        raise RuntimeError(f"{path.name} çözülemedi: STATE_KEY değişmiş olabilir.")


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(encrypt_bytes(json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")))
    for attempt in range(10):  # Windows: the file may be open in the other process for a moment
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.3)


# ---------------- products ----------------

def save_product(p: dict) -> None:
    p["updated_at"] = int(time.time())
    _write(PRODUCTS_DIR / f"{p['id']}.enc", p)


def load_product(pid: str):
    return _read(PRODUCTS_DIR / f"{pid}.enc")


def all_products() -> list:
    out = []
    if PRODUCTS_DIR.exists():
        for f in sorted(PRODUCTS_DIR.glob("*.enc")):
            try:
                out.append(_read(f))
            except Exception as e:
                print(f"[storage] {f.name} atlandı: {e}")
    out.sort(key=lambda p: p.get("created_at", 0))
    return out


def add_event(p: dict, text: str) -> None:
    p.setdefault("history", []).append({"t": int(time.time()), "e": text})


# ---------------- meta / tokens ----------------

def load_meta() -> dict:
    return _read(config.STATE_DIR / "meta.enc", {}) or {}


def save_meta(m: dict) -> None:
    _write(config.STATE_DIR / "meta.enc", m)


def load_etsy() -> dict:
    return _read(config.STATE_DIR / "etsy.enc", {}) or {}


def save_etsy(t: dict) -> None:
    _write(config.STATE_DIR / "etsy.enc", t)


def load_pinterest() -> dict:
    return _read(config.STATE_DIR / "pinterest.enc", {}) or {}


def save_pinterest(t: dict) -> None:
    _write(config.STATE_DIR / "pinterest.enc", t)


# ---------------- git ----------------

def _git(*args, check=True):
    return subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True, check=check)


_DEFERRED = {"msgs": [], "paths": set()}


def _flush_deferred():
    msgs = _DEFERRED["msgs"]
    if not msgs:
        return
    msg = msgs[-1] if len(set(msgs)) == 1 else f"{msgs[-1]} (+{len(msgs) - 1} işlem)"
    _DEFERRED["msgs"] = []
    try:
        commit_and_push(msg, tuple(sorted(_DEFERRED["paths"])), _final=True)
    except Exception as e:
        print(f"[git] tek commit gönderilemedi: {e}", flush=True)


def commit_and_push(message: str, extra_paths=(), _final=False) -> bool:
    """Commit state/ (and extra_paths) and push, retrying with rebase if another run pushed first.
    With DEFER_COMMIT=1 (all workflows) everything is saved in ONE commit when the job ends, so the repository
    gets a few commits per day instead of dozens (GitHub flags very frequent automated commits)."""
    if os.environ.get("DEFER_COMMIT") == "1" and not _final:
        if not _DEFERRED["msgs"]:
            atexit.register(_flush_deferred)
            try:  # a cancelled / timed-out job gets SIGTERM: still save what was done
                import signal
                import sys
                signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
            except Exception:
                pass
        _DEFERRED["msgs"].append(message)
        _DEFERRED["paths"].update(extra_paths)
        return False
    if not config.GITHUB_REPOSITORY:
        return False  # local run
    _git("config", "user.name", "etsy-bot")
    _git("config", "user.email", "etsy-bot@users.noreply.github.com")
    if not config.STATE_DIR.exists():
        return False
    _git("add", "-A", "state", *extra_paths)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    _git("commit", "-m", message)
    for attempt in range(6):
        r = _git("push", check=False)
        if r.returncode == 0:
            return True
        print(f"[git] push denemesi {attempt + 1} başarısız, rebase: {r.stderr.strip()[:200]}")
        pr = _git("pull", "--rebase", "-X", "theirs", check=False)
        if pr.returncode != 0:
            _git("rebase", "--abort", check=False)
            time.sleep(3)
        time.sleep(2 + attempt * 2)
    raise RuntimeError("Durum dosyaları GitHub'a gönderilemedi (git push).")
