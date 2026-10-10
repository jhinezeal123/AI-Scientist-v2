"""Personal-device pairing and scoped credentials. No multi-user identity system."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
from urllib.parse import urlsplit
import uuid

from fastapi import HTTPException, Request

from .store import _json, _now

SCOPES = {"read", "task", "message", "workspace", "permission", "research", "admin"}
COOKIE = "agent_device"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def loopback(request):
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        return request.client is not None and request.client.host == "testclient"


def remote_surface(request):
    # A TLS reverse proxy may itself connect from loopback. Its public Host is
    # still a remote surface, including when it does not send X-Forwarded-For.
    return not loopback(request) or request.url.hostname not in {'localhost','127.0.0.1','::1','testserver'}


def transport_guard(request: Request):
    origin = request.headers.get("origin")
    public = os.environ.get("AI_SCIENTIST_AGENT_PUBLIC_ORIGIN", "").rstrip("/")
    local = f"{request.url.scheme}://{request.url.netloc}"
    if origin and origin not in {local, public}:
        raise HTTPException(403, "Agent API origin refused")
    if loopback(request) and request.url.hostname not in {'localhost', '127.0.0.1', '::1', 'testserver'}:
        # Host is relevant even on loopback: prevent a DNS-rebinding origin from
        # using a browser's paired device cookie against the local control plane.
        if local != public:
            raise HTTPException(403, 'Untrusted local control host')
    if remote_surface(request):
        parsed = urlsplit(public)
        if not public or parsed.scheme != "https" or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise HTTPException(403, "Remote control requires a configured HTTPS private origin")
        if request.url.scheme != "https" or request.url.netloc != parsed.netloc:
            raise HTTPException(403, "Remote transport is not the configured HTTPS origin")


@dataclass(frozen=True)
class Principal:
    id: str
    scopes: frozenset[str]
    rig_ids: frozenset[str]
    seat_id: str | None = None
    agent: bool = False

    def require(self, scope, rig_id=None, *, human=False):
        if human and self.agent:
            raise HTTPException(403, "Agent credentials cannot authorize human-only actions")
        if scope not in self.scopes and "admin" not in self.scopes:
            raise HTTPException(403, "Credential scope does not allow this action")
        if rig_id is not None and "*" not in self.rig_ids and rig_id not in self.rig_ids:
            raise HTTPException(403, "Credential is outside this team's scope")


class DeviceAccess:
    def __init__(self, store):
        self.store = store

    def authenticate(self, request, *, scope="read", rig_id=None, human=False):
        transport_guard(request)
        master = os.environ.get("AI_SCIENTIST_AGENT_CONTROL_TOKEN", "")
        if not master:
            raise HTTPException(404, "Agent management is disabled")
        bearer = request.headers.get("authorization", "")
        credential = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get(COOKIE, "")
        if not credential:
            raise HTTPException(401, "Pair or sign in to control agents")
        if hmac.compare_digest(credential, master):
            # Master is a bootstrap credential. Never accepted from browser cookies.
            if not bearer:
                raise HTTPException(401, "Bootstrap credential requires explicit authorization")
            if remote_surface(request):
                raise HTTPException(403, 'Bootstrap control token is local only; pair a device')
            principal = Principal("local-operator", frozenset(SCOPES), frozenset({"*"}))
        else:
            with self.store.connect() as con:
                row = con.execute("SELECT * FROM devices WHERE token_hash=? AND revoked=0 AND expires_at>?", (digest(credential), _now())).fetchone()
            if row is None:
                raise HTTPException(401, "Device credential expired or revoked")
            scopes = frozenset(json.loads(row["scopes_json"]))
            principal = Principal(row["id"], scopes, frozenset(json.loads(row["rig_ids_json"])),
                next((s[5:] for s in scopes if s.startswith("seat:")), None), "agent" in scopes)
            if not bearer and request.method not in {"GET", "HEAD", "OPTIONS"}:
                csrf = digest(credential + ":csrf")
                if not hmac.compare_digest(request.headers.get("x-agent-csrf", ""), csrf):
                    raise HTTPException(403, "Agent CSRF token required")
        principal.require(scope, rig_id, human=human)
        return principal

    def pairing(self, *, scopes, rig_ids, ttl_seconds=300):
        if not set(scopes) <= SCOPES or not scopes or not rig_ids or not 30 <= ttl_seconds <= 600:
            raise ValueError("Invalid pairing scope or expiry")
        identifier, code = uuid.uuid4().hex, secrets.token_urlsafe(24)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        with self.store.connect(True) as con:
            con.execute("INSERT INTO pairings VALUES(?,?,?,?,?,0)", (identifier, digest(code), _json(scopes), _json(rig_ids), expires))
            self.store.event(con, "pairing_created", {"pairing_id": identifier, "scopes": scopes, "rig_ids": rig_ids})
        return {"pairing_id": identifier, "code": code, "expires_at": expires}

    def exchange(self, pairing_id, code, name):
        if not isinstance(name, str) or not 1 <= len(name) <= 120:
            raise ValueError("Invalid device name")
        with self.store.connect(True) as con:
            row = con.execute("SELECT * FROM pairings WHERE id=? AND used=0 AND expires_at>?", (pairing_id, _now())).fetchone()
            if row is None or not hmac.compare_digest(digest(code), row["code_hash"]):
                raise ValueError("Pairing code expired, invalid or already used")
            con.execute("UPDATE pairings SET used=1 WHERE id=?", (pairing_id,))
            token, device_id = secrets.token_urlsafe(32), uuid.uuid4().hex
            expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            con.execute("INSERT INTO devices VALUES(?,?,?,?,?,0,?,?)", (device_id, name, digest(token), row["scopes_json"], row["rig_ids_json"], expires, _now()))
            self.store.event(con, "device_paired", {"device_id": device_id, "name": name})
        return {"device_id": device_id, "token": token, "csrf": digest(token + ":csrf"), "expires_at": expires}

    def agent_token(self, rig_id, seat_id):
        rig = self.store.rig(rig_id)
        if seat_id not in {s.id for s in rig.seats}:
            raise ValueError("Unknown seat")
        token, identifier = secrets.token_urlsafe(32), uuid.uuid4().hex
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        scopes = ["read", "task", "message", "agent", "seat:" + seat_id]
        with self.store.connect(True) as con:
            con.execute("INSERT INTO devices VALUES(?,?,?,?,?,0,?,?)", (identifier, "Agent " + seat_id, digest(token), _json(scopes), _json([rig_id]), expires, _now()))
            self.store.event(con, "agent_credential_created", {"device_id": identifier}, rig_id=rig_id, seat_id=seat_id)
        return {"device_id": identifier, "token": token, "expires_at": expires}

    def revoke(self, device_id):
        with self.store.connect(True) as con:
            cursor = con.execute("UPDATE devices SET revoked=1 WHERE id=?", (device_id,))
            if not cursor.rowcount:
                raise KeyError("Unknown device")
            self.store.event(con, "device_revoked", {"device_id": device_id})

    def devices(self):
        with self.store.connect() as con:
            rows = con.execute("SELECT id,name,scopes_json,rig_ids_json,revoked,expires_at,created_at FROM devices ORDER BY created_at").fetchall()
        return [{"id": r["id"], "name": r["name"], "scopes": json.loads(r["scopes_json"]),
                 "rig_ids": json.loads(r["rig_ids_json"]), "revoked": bool(r["revoked"]),
                 "expires_at": r["expires_at"], "created_at": r["created_at"]} for r in rows]
