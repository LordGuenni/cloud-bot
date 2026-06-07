from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from azure.cosmos import CosmosClient, PartitionKey


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

    def list_accounts(self) -> list[dict[str, Any]]:
        return list(
            self.container.query_items(
                query="SELECT * FROM c",
                enable_cross_partition_query=True,
            )
        )
