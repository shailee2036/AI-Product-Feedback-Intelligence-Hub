"""Import the Feedback Hub dashboards into a Grafana Cloud stack.

Usage:
    $env:GRAFANA_CLOUD_TOKEN = "<service account token>"
    python deploy/scripts/grafana_cloud_import.py --url https://<stack>.grafana.net

The token needs the Editor role. It is read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any

FOLDER_UID = "feedback-hub"
FOLDER_TITLE = "Feedback Hub"
DASHBOARDS = pathlib.Path(__file__).resolve().parents[1] / "charts" / "monitoring" / "dashboards"
SUFFIXES = {"prometheus": "-prom", "loki": "-logs"}


class Grafana:
    def __init__(self, url: str, token: str) -> None:
        if not url.startswith("https://"):
            sys.exit("The stack URL must start with https://.")
        self.url = url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method)  # noqa: S310
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error)
            except ValueError:
                detail = {}
            return error.code, detail


def pick_datasources(
    grafana: Grafana, overrides: dict[str, str | None]
) -> dict[str, dict[str, str]]:
    status, sources = grafana.request("GET", "/api/datasources")
    if status != 200:
        sys.exit(
            f"Could not list data sources (HTTP {status}). "
            "Check the URL and that the token has the Editor role."
        )
    picked: dict[str, dict[str, str]] = {}
    for kind, suffix in SUFFIXES.items():
        candidates = [s for s in sources if s.get("type") == kind]
        uid = overrides.get(kind)
        if uid:
            match = next((s for s in candidates if s.get("uid") == uid), None)
        else:
            match = next((s for s in candidates if str(s.get("name", "")).endswith(suffix)), None)
        if match is None:
            names = ", ".join(f"{s.get('name')} ({s.get('uid')})" for s in candidates) or "none"
            sys.exit(f"No {kind} data source found. Available: {names}. Pass --{kind}-uid.")
        picked[kind] = {"text": str(match["name"]), "value": str(match["uid"])}
        print(f"{kind}: {match['name']} ({match['uid']})")
    return picked


def ensure_folder(grafana: Grafana) -> None:
    status, _ = grafana.request("GET", f"/api/folders/{FOLDER_UID}")
    if status == 200:
        return
    status, detail = grafana.request(
        "POST", "/api/folders", {"uid": FOLDER_UID, "title": FOLDER_TITLE}
    )
    if status != 200:
        message = detail.get("message", "")
        sys.exit(f"Could not create the {FOLDER_TITLE} folder (HTTP {status}): {message}")


def point_at(dashboard: dict[str, Any], picked: dict[str, dict[str, str]]) -> None:
    for variable in dashboard.get("templating", {}).get("list", []):
        if variable.get("type") == "datasource" and variable.get("query") in picked:
            variable["current"] = picked[variable["query"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url",
        default=os.environ.get("GRAFANA_CLOUD_URL"),
        help="Stack URL, https://<stack>.grafana.net",
    )
    parser.add_argument("--prometheus-uid", help="Metrics data source uid, if not the *-prom one")
    parser.add_argument("--loki-uid", help="Logs data source uid, if not the *-logs one")
    args = parser.parse_args()

    token = os.environ.get("GRAFANA_CLOUD_TOKEN")
    if not args.url or not token:
        sys.exit("Set --url (or GRAFANA_CLOUD_URL) and GRAFANA_CLOUD_TOKEN.")

    grafana = Grafana(args.url, token)
    picked = pick_datasources(grafana, {"prometheus": args.prometheus_uid, "loki": args.loki_uid})
    ensure_folder(grafana)

    failed = 0
    for path in sorted(DASHBOARDS.glob("*.json")):
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        dashboard.pop("id", None)
        point_at(dashboard, picked)
        status, detail = grafana.request(
            "POST",
            "/api/dashboards/db",
            {
                "dashboard": dashboard,
                "folderUid": FOLDER_UID,
                "overwrite": True,
                "message": "Imported from the repository",
            },
        )
        if status == 200:
            print(f"imported {dashboard['title']}: {args.url.rstrip('/')}{detail.get('url', '')}")
        else:
            failed += 1
            print(f"failed {dashboard['title']} (HTTP {status}): {detail.get('message', '')}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
