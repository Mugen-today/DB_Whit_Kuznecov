"""The single shared MongoDB connection layer for all future backend modules."""

import os

USERS = {
    "reader": ("analyst", "READER_PASSWORD"),
    "ingest": ("etl_ingest", "INGEST_PASSWORD"),
    "processor": ("etl_processor", "PROCESSOR_PASSWORD"),
    "user": ("app_user", "USER_PASSWORD"),
    "guest": ("guest", "GUEST_PASSWORD"),
}


class MongoDB:
    def __init__(self, environment=None, client_factory=None):
        env = os.environ if environment is None else environment
        passwords = {
            role: env.get(variable, "") for role, (_, variable) in USERS.items()
        }
        if not all(passwords.values()):
            raise ValueError("Missing MongoDB service credentials")
        if client_factory is None:
            from pymongo import MongoClient

            client_factory = MongoClient
        self.database_name = env.get("MONGO_DATABASE", "Schema")
        self.clients = {}
        try:
            for role, (username, _) in USERS.items():
                self.clients[role] = client_factory(
                    env.get("MONGO_HOST", "storage"),
                    int(env.get("MONGO_PORT", "27017")),
                    username=username,
                    password=passwords[role],
                    authSource=self.database_name,
                    appname="gis-backend-" + role,
                    maxPoolSize=4,
                    minPoolSize=0,
                    maxConnecting=2,
                    serverSelectionTimeoutMS=3000,
                    connectTimeoutMS=3000,
                    socketTimeoutMS=3000,
                    timeoutMS=3000,
                    waitQueueTimeoutMS=1000,
                    retryWrites=False,
                    tz_aware=True,
                )
        except Exception:
            self.close()
            raise

    def database(self, role):
        """Caller must authorize an operation before choosing a role; no default root client."""
        if role=="admin": role="user"
        if role not in self.clients:
            raise ValueError("Unknown database role")
        from pymongo.write_concern import WriteConcern

        return self.clients[role].get_database(
            self.database_name, write_concern=WriteConcern(w=1, j=True)
        )

    def ready(self):
        """Read one projected ID per service user: proves authentication AND read access."""
        for client in self.clients.values():
            database = client[self.database_name]
            database.command("ping")
            database.cases.find_one({}, {"_id": 1}, max_time_ms=1000)

    def close(self):
        for client in self.clients.values():
            client.close()
