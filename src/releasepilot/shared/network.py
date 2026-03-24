"""Shared networking utilities — SSL context, HTTP helpers.

This module centralises corporate-network concerns (proxy CAs, Zscaler,
custom cert bundles) so that *every* outgoing HTTPS call uses the same
trusted SSL context.

Corporate environments commonly intercept HTTPS traffic via proxy CAs
(Zscaler, Netskope, etc.).  Python's default SSL context does not include
these CA certificates, causing ``SSL: CERTIFICATE_VERIFY_FAILED`` errors
when talking to GitLab or any HTTPS endpoint.

Resolution order for CA certificates:

1. ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` env var  (explicit override)
2. ``certifi`` package  (ships Mozilla CA bundle)
3. macOS system keychain  (includes corporate CAs like Zscaler)
4. Python default  (works on most Linux distros)

Usage::

    from releasepilot.shared.network import make_ssl_context

    ctx = make_ssl_context()
    urllib.request.urlopen(req, context=ctx)

Configuration
-------------
Set one of the following environment variables before starting ReleasePilot
to use a custom CA bundle:

- ``SSL_CERT_FILE=/path/to/ca-bundle.pem``
- ``REQUESTS_CA_BUNDLE=/path/to/ca-bundle.pem``

On macOS, if neither env var is set and ``certifi`` is not installed,
the module automatically loads certificates from the system keychain
(which includes corporate proxy CAs).
"""

from __future__ import annotations

import logging
import os
import ssl
import sys

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSL / TLS
# ---------------------------------------------------------------------------

_cached_ssl_ctx: ssl.SSLContext | None = None


def make_ssl_context(*, force_new: bool = False) -> ssl.SSLContext:
    """Build an SSL context that works in corporate proxy environments.

    Resolution order:

    1. ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` env var (explicit override)
    2. ``certifi`` package (ships Mozilla CA bundle)
    3. macOS system keychain (includes corporate CAs like Zscaler)
    4. Python default (works on most Linux distros)

    The result is cached process-wide (thread-safe for reads) unless
    *force_new* is True.
    """
    global _cached_ssl_ctx
    if _cached_ssl_ctx is not None and not force_new:
        return _cached_ssl_ctx

    ctx = _build_ssl_context()
    _cached_ssl_ctx = ctx
    return ctx


def _build_ssl_context() -> ssl.SSLContext:
    """Internal builder — not cached, always creates a fresh context."""
    # 1. Honour explicit env var
    for env in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        ca = os.environ.get(env)
        if ca and os.path.isfile(ca):
            logger.debug("SSL: using CA bundle from %s=%s", env, ca)
            return ssl.create_default_context(cafile=ca)

    # 2. Try certifi
    try:
        import certifi  # type: ignore[import-untyped]

        logger.debug("SSL: using certifi CA bundle")
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    # 3. Try macOS system certificates (includes corporate CAs)
    if sys.platform == "darwin":
        try:
            import subprocess

            pem = subprocess.run(
                [
                    "security",
                    "find-certificate",
                    "-a",
                    "-p",
                    "/Library/Keychains/System.keychain",
                    "/System/Library/Keychains/SystemRootCertificates.keychain",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if pem.returncode == 0 and "BEGIN CERTIFICATE" in pem.stdout:
                ctx = ssl.create_default_context()
                ctx.load_verify_locations(cadata=pem.stdout)
                logger.debug("SSL: loaded macOS system certificates")
                return ctx
        except Exception:
            pass

    # 4. Default
    logger.debug("SSL: using Python default context")
    return ssl.create_default_context()


def make_no_verify_ssl_context() -> ssl.SSLContext:
    """Build an SSL context that skips certificate verification.

    **Security warning:** This disables TLS certificate validation entirely.
    Only use this when ``verify_ssl=False`` has been explicitly configured
    by the operator (e.g. for self-signed certs during development).
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
