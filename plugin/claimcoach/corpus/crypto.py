"""User-scope encryption at rest with a key held in the macOS Keychain.

Implements: US-4.2 (``KeyProvider`` protocol, ``KeychainKeyProvider``, ``InMemoryKeyProvider``,
``Cipher``). Rules: BR-6 (user scope encrypted at rest, key in the macOS Keychain), BR-14 (errors
carry no key material or Keychain output).

Each value is AES-256-GCM with a fresh 96-bit nonce, stored as ``nonce || ciphertext``. The
associated data names the value's table and row, so a blob copied onto another row fails to
decrypt instead of being read as that row.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path
from typing import Final, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from claimcoach.corpus.errors import CorpusKeyError

__all__ = [
    "KEY_BYTES",
    "KEY_SERVICE",
    "Cipher",
    "InMemoryKeyProvider",
    "KeyProvider",
    "KeychainKeyProvider",
    "key_account",
]

KEY_BYTES: Final = 32
KEY_SERVICE: Final = "ClaimCoach user store"
"""Keychain service of every user-store key; the account names the profile."""

_NONCE_BYTES: Final = 12
_SECURITY: Final = Path("/usr/bin/security")
_NOT_FOUND: Final = 44
"""``security`` exit status for "The specified item could not be found in the keychain"."""


def key_account(profile: str) -> str:
    """Return the Keychain account of ``profile``'s user-store key."""
    return f"user-store:{profile}"


class KeyProvider(Protocol):
    """Supplies the 256-bit key of a user store.

    ``create`` is true only for a brand-new store: an existing store whose key is missing must
    fail closed, never get a fresh key that cannot decrypt it (and that would then block importing
    the real one).
    """

    def key_for(self, account: str, *, create: bool) -> bytes:  # noqa: D102 - see the class
        ...


class InMemoryKeyProvider:
    """Test double: keys live in a dict and die with the process."""

    def __init__(self) -> None:
        """Start with no keys."""
        self.keys: dict[str, bytes] = {}

    def key_for(self, account: str, *, create: bool) -> bytes:
        """Return ``account``'s key; a random one is created only when ``create`` is true.

        Raises:
            CorpusKeyError: No key and ``create`` is false.
        """
        if account not in self.keys:
            if not create:
                raise CorpusKeyError
            self.keys[account] = secrets.token_bytes(KEY_BYTES)
        return self.keys[account]


class KeychainKeyProvider:
    """Keys as generic passwords in the macOS Keychain, through ``/usr/bin/security``.

    Reads use fixed argv and ``stdin=DEVNULL``. Writes run ``security -i`` with the command on
    stdin, so a key never appears in a process listing; because ``security -i`` exits 0 even when
    its command fails, every write is read back, and the stored key is the one used.

    Args:
        keychain: A specific keychain file (tests use a throwaway one); the user's default
            keychain search list otherwise.
        security: The ``security`` binary.
        timeout: Seconds per ``security`` call.
    """

    def __init__(
        self, keychain: Path | None = None, *, security: Path = _SECURITY, timeout: float = 10.0
    ) -> None:
        """Store the Keychain settings; nothing runs until a key is asked for."""
        self._keychain = keychain
        self._security = security
        self._timeout = timeout

    def key_for(self, account: str, *, create: bool) -> bytes:
        """Return ``account``'s key; a random one is created and stored only when ``create``.

        Raises:
            CorpusKeyError: No key (and ``create`` is false), or the Keychain could not be read or
                written, or it holds something that is not a ClaimCoach key.
        """
        key = self._find(account)
        if key is None:
            if not create:
                raise CorpusKeyError
            key = self.store_key(account, secrets.token_bytes(KEY_BYTES), replace=False)
        return key

    def export_key(self, account: str) -> bytes:
        """Return ``account``'s stored key, for a key backup (runbook).

        Raises:
            CorpusKeyError: There is no key, or it cannot be read.
        """
        return self.key_for(account, create=False)

    def store_key(self, account: str, key: bytes, *, replace: bool) -> bytes:
        """Store ``key`` for ``account`` (a key restore) and return the key the Keychain holds.

        Args:
            account: Keychain account.
            key: A 32-byte key.
            replace: Overwrite an existing item (``-U``); otherwise an existing item wins.

        Raises:
            CorpusKeyError: ``key`` is not 32 bytes, or the Keychain did not keep it.
        """
        if len(key) != KEY_BYTES:
            raise CorpusKeyError
        # Service, account, and keychain path are quoted for ``security -i``'s own tokenizer;
        # the account is ``user-store:<profile name>`` and the hex key has no special characters.
        target = "".join(f' "{arg}"' for arg in self._keychain_args())
        update = " -U" if replace else ""
        command = (
            f'add-generic-password{update} -s "{KEY_SERVICE}" -a "{account}" '
            f"-w {key.hex()}{target}\n"
        )
        self._run([str(self._security), "-i"], command.encode("ascii"))
        stored = self._find(account)
        if stored is None or (replace and stored != key):
            raise CorpusKeyError
        return stored

    def _keychain_args(self) -> list[str]:
        return [] if self._keychain is None else [str(self._keychain)]

    def _run(self, argv: list[str], stdin: bytes | None) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv,
                input=stdin,
                stdin=subprocess.DEVNULL if stdin is None else None,
                capture_output=True,
                timeout=self._timeout,
                check=False,
                env={"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "")},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CorpusKeyError from exc

    def _find(self, account: str) -> bytes | None:
        argv = [str(self._security), "find-generic-password", "-s", KEY_SERVICE, "-a", account]
        done = self._run([*argv, "-w", *self._keychain_args()], None)
        if done.returncode == _NOT_FOUND:
            return None
        if done.returncode != 0:
            raise CorpusKeyError
        try:
            key = bytes.fromhex(done.stdout.decode("ascii").strip())
        except (UnicodeDecodeError, ValueError) as exc:
            raise CorpusKeyError from exc
        if len(key) != KEY_BYTES:
            raise CorpusKeyError
        return key


class Cipher:
    """AES-256-GCM over individual values.

    Args:
        key: 32-byte key.
    """

    def __init__(self, key: bytes) -> None:
        """Build the AEAD; ``key`` must be 32 bytes."""
        if len(key) != KEY_BYTES:
            raise CorpusKeyError
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: bytes, context: str) -> bytes:
        """Return ``nonce || ciphertext`` bound to ``context`` (table and row ID)."""
        nonce = secrets.token_bytes(_NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, plaintext, context.encode())

    def decrypt(self, blob: bytes, context: str) -> bytes:
        """Return the plaintext of ``blob``.

        Raises:
            CorpusKeyError: Wrong key, wrong context, or a tampered value.
        """
        try:
            return self._aead.decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], context.encode())
        except (InvalidTag, ValueError) as exc:  # ValueError: a truncated blob
            raise CorpusKeyError from exc
