from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any
from uuid import uuid4

from azure.cosmos import CosmosClient, PartitionKey
from botbuilder.core import Storage


class LocalAccountStore:
    def __init__(self, path: str = "data/users.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def save(self, account: dict[str, Any]) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload.append(account)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, account_id: str, email: str) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload = [acc for acc in payload if acc.get("id") != account_id]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_accounts(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))


class CosmosAccountStore:
    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str,
    ) -> None:
        client = CosmosClient(endpoint, credential=key)
        database = client.create_database_if_not_exists(id=database_name)
        self.container = database.create_container_if_not_exists(
            id=container_name,
            partition_key=PartitionKey(path="/email"),
        )

    def save(self, account: dict[str, Any]) -> None:
        item = dict(account)
        item["id"] = str(uuid4())
        self.container.upsert_item(item)

    def update(self, account: dict[str, Any]) -> None:
        item = dict(account)
        if "id" not in item:
            raise ValueError("Account ID is required for update")
        self.container.upsert_item(item)

    def delete(self, account_id: str, email: str) -> None:
        self.container.delete_item(item=account_id, partition_key=email)

    def list_accounts(self) -> list[dict[str, Any]]:
        return list(
            self.container.query_items(
                query="SELECT * FROM c",
                enable_cross_partition_query=True,
            )
        )


class FileStorage(Storage):
    def __init__(self, folder: str = "data/storage") -> None:
        super().__init__()
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def _safe_key(self, key: str) -> str:
        return "".join(c for c in key if c.isalnum() or c in ("-", "_"))

    async def read(self, keys: list[str]) -> dict[str, object]:
        result = {}
        for key in keys:
            file_path = self.folder / f"{self._safe_key(key)}.pkl"
            if file_path.exists():
                try:
                    result[key] = pickle.loads(file_path.read_bytes())
                except Exception:
                    pass
        return result

    async def write(self, changes: dict[str, object]) -> None:
        for key, change in changes.items():
            file_path = self.folder / f"{self._safe_key(key)}.pkl"
            try:
                file_path.write_bytes(pickle.dumps(change))
            except Exception:
                pass

    async def delete(self, keys: list[str]) -> None:
        for key in keys:
            file_path = self.folder / f"{self._safe_key(key)}.pkl"
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
