"""One-time personal-device pairing, independent of team/preset/Slack logic."""
from datetime import datetime, timedelta, timezone
import hmac
import secrets
import uuid

from .auth import SCOPES, digest
from .store import _json, _now


class RemoteDevices:
    def __init__(self, store):
        self.store = store

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
