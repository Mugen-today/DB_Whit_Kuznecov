"""Internal authorization primitives, NOT a login API.
Principal must come from a verified server-side identity, never request role/user_id fields.
End users must not receive app_user/processor/analyst MongoDB credentials.
"""

from dataclasses import dataclass
from ..models.schema import load_schema

MODEL = load_schema()
COLLECTIONS = {
    item["ns"].split(".", 1)[1] for item in MODEL["collections"].values()
} | {"cases"}
GUEST_DENY = {"Social_group", "Street", "Building", "Placement"}


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


class Repository:
    def __init__(self, store, principal):
        if (
            not isinstance(principal.user_id, str)
            or not principal.user_id.strip()
            or principal.role not in ("user", "guest")
        ):
            raise PermissionError("Use separate administrative path")
        self.store = store
        self.principal = principal

    def collection(self, name, write=False):
        if name not in COLLECTIONS:
            raise PermissionError("Unknown collection")
        if self.principal.role == "guest" and (write or name in GUEST_DENY):
            raise PermissionError("Guest permission denied")
        if write and name == "cases":
            raise PermissionError("Original cases are immutable")
        return self.store.database(self.principal.role)[name]

    def scope(self, identifier):
        # Equality wrapper prevents interpreting a dict identifier as query operators.
        result = {"_id": {"$eq": identifier}}
        if self.principal.role == "user":
            result["_owner_id"] = self.principal.user_id
        return result

    def get(self, name, identifier):
        return self.collection(name).find_one(self.scope(identifier))

    def fields(self, value):
        if not isinstance(value, dict) or not value:
            raise ValueError("Nonempty fields required")

        def walk(obj):
            if isinstance(obj, dict):
                for key, item in obj.items():
                    if (
                        not isinstance(key, str)
                        or key.startswith("$")
                        or "." in key
                        or "\x00" in key
                    ):
                        raise ValueError("Unsafe key")
                    walk(item)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(value)
        if {"_id", "_owner_id"} & set(value):
            raise PermissionError("Identity and owner are server-controlled")
        return dict(value)

    def create(self, name, fields):
        collection = self.collection(name, write=True)
        data = self.fields(fields)
        data["_owner_id"] = self.principal.user_id
        return collection.insert_one(data)

    def update(self, name, identifier, fields):
        collection = self.collection(name, write=True)
        # Ownership is checked in the SAME atomic update condition, not in a prior read.
        return collection.update_one(
            self.scope(identifier), {"$set": self.fields(fields)}, upsert=False
        )
