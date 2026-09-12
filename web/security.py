"""
Security middleware for the web UI.

This server has no login (it's a single-user, localhost-bound tool),
so these two cheap checks stand in for authentication:

    - Host header allowlist: defeats DNS rebinding, where an
      attacker's page gets a victim browser to resolve an
      attacker-controlled hostname to 127.0.0.1 *after* the original
      same-origin check passed, then talks to this server as if it
      were same-origin JavaScript. Browsers don't let a page fake its
      own Host header, so this is a real barrier.
    - Content-Type: application/json required on every mutating
      request, including ones with no body (e.g. cancel): a plain
      HTML <form> cannot set an arbitrary Content-Type (browsers
      restrict forms to a fixed list that doesn't include
      "application/json"), and a cross-origin fetch() that tries to
      set it triggers a CORS preflight -- which this server never
      answers with permissive CORS headers, so the browser blocks the
      real request before it's sent. Between the two, classic form
      CSRF and cross-origin JS both fail closed.

Neither of these defends against something already running as the
same OS user on the same machine (a local process could always read
the config file or call this API directly) -- that is out of scope for
what an unauthenticated localhost server can meaningfully protect.
"""

from __future__ import annotations

from typing import Iterable

from flask import Flask, jsonify, request

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def install_security_checks(app: Flask, allowed_hosts: Iterable[str]) -> None:
    """Register before_request hooks enforcing the host allowlist and JSON-only mutations."""
    allowed = set(allowed_hosts)

    @app.before_request
    def _check_host():
        if request.host not in allowed:
            return jsonify(error="Forbidden host header."), 403

    @app.before_request
    def _check_json_on_mutations():
        if request.method not in _MUTATING_METHODS:
            return None
        content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return jsonify(error="Content-Type must be application/json."), 415
        return None
