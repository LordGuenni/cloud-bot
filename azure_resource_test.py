#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | WARN | FAIL
    details: str


def run_az(args: list[str], expect_json: bool = True) -> Any:
    command = ["az", *args]
    if expect_json:
        command.extend(["-o", "json"])

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())

    if not expect_json:
        return completed.stdout.strip()

    try:
        return json.loads(completed.stdout or "null")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ungueltige JSON-Antwort von az: {exc}") from exc


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def parse_vault_name(vault_uri: str) -> str:
    host = urlparse(vault_uri).netloc
    if not host:
        raise ValueError(f"Ungültige Vault-URI: {vault_uri}")
    return host.split(".")[0]


def check_subscription(config: dict[str, Any]) -> CheckResult:
    account = run_az(["account", "show"])
    expected_sub = config.get("subscription_id")
    expected_tenant = config.get("tenant_id")

    if expected_sub and account.get("id") != expected_sub:
        return CheckResult(
            "Azure Subscription",
            "FAIL",
            f"Aktiv: {account.get('id')}, Erwartet: {expected_sub}",
        )

    if expected_tenant and account.get("tenantId") != expected_tenant:
        return CheckResult(
            "Azure Tenant",
            "FAIL",
            f"Aktiv: {account.get('tenantId')}, Erwartet: {expected_tenant}",
        )

    return CheckResult(
        "Azure Login",
        "PASS",
        f"Eingeloggt als Subscription {account.get('name')} ({account.get('id')})",
    )


def check_resource_group(config: dict[str, Any]) -> CheckResult:
    rg_name = config["resource_group"]
    rg = run_az(["group", "show", "--name", rg_name])
    expected_location = config.get("location")

    if expected_location and rg.get("location", "").lower() != expected_location.lower():
        return CheckResult(
            "Resource Group Standort",
            "FAIL",
            f"Aktiv: {rg.get('location')}, Erwartet: {expected_location}",
        )

    return CheckResult(
        "Resource Group",
        "PASS",
        f"{rg_name} vorhanden (Location: {rg.get('location')})",
    )


def check_resource_types(config: dict[str, Any]) -> CheckResult:
    rg_name = config["resource_group"]
    required_types = config.get("required_resource_types", [])
    resources = run_az(["resource", "list", "--resource-group", rg_name])
    available_types = {resource.get("type") for resource in resources}
    missing = [resource_type for resource_type in required_types if resource_type not in available_types]

    if missing:
        return CheckResult(
            "Ressourcen-Typen",
            "FAIL",
            f"Fehlende Typen: {', '.join(missing)}",
        )

    return CheckResult(
        "Ressourcen-Typen",
        "PASS",
        f"Alle erwarteten Typen vorhanden ({len(required_types)} geprüft)",
    )


def check_expected_names(config: dict[str, Any]) -> CheckResult:
    expected = config.get("expected_resource_names", {})
    if not expected:
        return CheckResult(
            "Ressourcen-Namen",
            "WARN",
            "Keine expected_resource_names im Config-File gesetzt",
        )

    rg_name = config["resource_group"]
    resources = run_az(["resource", "list", "--resource-group", rg_name])
    by_type: dict[str, set[str]] = {}
    for resource in resources:
        resource_type = resource.get("type")
        resource_name = resource.get("name")
        if resource_type and resource_name:
            by_type.setdefault(resource_type, set()).add(resource_name)

    missing: list[str] = []
    for resource_type, name in expected.items():
        if name not in by_type.get(resource_type, set()):
            missing.append(f"{resource_type}:{name}")

    if missing:
        return CheckResult(
            "Ressourcen-Namen",
            "FAIL",
            f"Fehlend: {', '.join(missing)}",
        )

    return CheckResult("Ressourcen-Namen", "PASS", "Alle erwarteten Ressourcennamen vorhanden")


def check_key_vault_secrets(config: dict[str, Any]) -> CheckResult:
    secret_names = config.get("key_vault_secret_names", {})
    if not secret_names:
        return CheckResult(
            "Key Vault Secrets",
            "WARN",
            "Keine key_vault_secret_names gesetzt",
        )

    vault_uri = config.get("key_vault_uri")
    if not vault_uri:
        return CheckResult("Key Vault Secrets", "FAIL", "key_vault_uri fehlt in config.json")

    vault_name = parse_vault_name(vault_uri)
    missing: list[str] = []
    skipped: list[str] = []

    for logical_name, secret_name in secret_names.items():
        if not secret_name:
            skipped.append(logical_name)
            continue
        try:
            run_az(
                [
                    "keyvault",
                    "secret",
                    "show",
                    "--vault-name",
                    vault_name,
                    "--name",
                    secret_name,
                ]
            )
        except RuntimeError:
            missing.append(f"{logical_name}:{secret_name}")

    if missing:
        return CheckResult(
            "Key Vault Secrets",
            "FAIL",
            f"Nicht lesbar/fehlend: {', '.join(missing)}",
        )

    if skipped:
        return CheckResult(
            "Key Vault Secrets",
            "WARN",
            f"{len(secret_names) - len(skipped)} geprüft, übersprungen: {', '.join(skipped)}",
        )

    return CheckResult(
        "Key Vault Secrets",
        "PASS",
        f"Alle {len(secret_names)} Secrets sind lesbar",
    )


def print_report(results: list[CheckResult]) -> None:
    print("\n=== Azure Resource Test Report ===")
    for result in results:
        print(f"[{result.status:<4}] {result.name}: {result.details}")

    failed = sum(1 for result in results if result.status == "FAIL")
    warned = sum(1 for result in results if result.status == "WARN")
    print(f"\nSummary: {len(results)} checks, {failed} FAIL, {warned} WARN")


def write_json_report(path: str, results: list[CheckResult]) -> None:
    payload = [
        {"name": result.name, "status": result.status, "details": result.details}
        for result in results
    ]
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Testet Azure-Ressourcen für den Sprachbot")
    parser.add_argument("--config", default="config.json", help="Pfad zur Konfiguration")
    parser.add_argument("--report-json", default="", help="Optionaler Pfad für JSON-Report")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        checks = [
            check_subscription(config),
            check_resource_group(config),
            check_resource_types(config),
            check_expected_names(config),
            check_key_vault_secrets(config),
        ]
    except Exception as exc:  # pragma: no cover
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2

    print_report(checks)

    if args.report_json:
        write_json_report(args.report_json, checks)
        print(f"JSON-Report geschrieben: {args.report_json}")

    has_failure = any(check.status == "FAIL" for check in checks)
    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
