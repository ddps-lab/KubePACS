#!/usr/bin/env python3
"""Check that Azure ingestion monitor rows with real spot prices are queryable.

The check starts an Athena query and polls GetQueryExecution until Athena reaches
one of its terminal states. It intentionally does not treat QUEUED/RUNNING as a
failure, because larger partitions can take longer than the first few polling
intervals to finish.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}
IN_PROGRESS_STATES = {"QUEUED", "RUNNING"}
DEFAULT_QUERY_TIMEOUT_SECONDS = 300.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class QueryResult:
    query_execution_id: str
    count: int


class AthenaQueryError(RuntimeError):
    """Raised when Athena reports a terminal unsuccessful state."""


class AthenaQueryTimeout(TimeoutError):
    """Raised when an Athena query does not finish before the configured timeout."""


def build_monitor_query(database: str, table: str) -> str:
    return f'SELECT count(*) FROM "{database}"."{table}" WHERE spotprice != -1'


def start_query(
    client: Any,
    query: str,
    database: str,
    output_location: str,
    workgroup: str | None = None,
) -> str:
    request: dict[str, Any] = {
        "QueryString": query,
        "QueryExecutionContext": {"Database": database},
        "ResultConfiguration": {"OutputLocation": output_location},
    }
    if workgroup:
        request["WorkGroup"] = workgroup

    response = client.start_query_execution(**request)
    return response["QueryExecutionId"]


def wait_for_query(
    client: Any,
    query_execution_id: str,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Poll Athena until the query reaches a terminal state or times out."""
    deadline = clock() + timeout_seconds
    last_state = "UNKNOWN"
    last_reason = ""

    while True:
        response = client.get_query_execution(QueryExecutionId=query_execution_id)
        execution = response["QueryExecution"]
        status = execution.get("Status", {})
        state = status.get("State", "UNKNOWN")
        reason = status.get("StateChangeReason", "")
        last_state = state
        last_reason = reason

        if state == "SUCCEEDED":
            return execution
        if state in TERMINAL_STATES:
            message = f"Athena query {query_execution_id} ended in {state}"
            if reason:
                message = f"{message}: {reason}"
            raise AthenaQueryError(message)
        if state not in IN_PROGRESS_STATES:
            raise AthenaQueryError(f"Athena query {query_execution_id} returned unexpected state {state}")

        remaining_seconds = deadline - clock()
        if remaining_seconds <= 0:
            message = (
                f"Athena query {query_execution_id} did not finish within "
                f"{timeout_seconds:g}s; last state was {last_state}"
            )
            if last_reason:
                message = f"{message}: {last_reason}"
            raise AthenaQueryTimeout(message)

        sleeper(min(poll_interval_seconds, remaining_seconds))


def read_count_result(client: Any, query_execution_id: str) -> int:
    response = client.get_query_results(QueryExecutionId=query_execution_id, MaxResults=2)
    rows = response.get("ResultSet", {}).get("Rows", [])
    if len(rows) < 2:
        raise AthenaQueryError(f"Athena query {query_execution_id} returned no count row")

    data = rows[1].get("Data", [])
    if not data or "VarCharValue" not in data[0]:
        raise AthenaQueryError(f"Athena query {query_execution_id} returned an unreadable count row")

    return int(data[0]["VarCharValue"])


def run_monitor_check(
    client: Any,
    database: str,
    table: str,
    output_location: str,
    workgroup: str | None = None,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    min_count: int = 1,
) -> QueryResult:
    query = build_monitor_query(database, table)
    query_execution_id = start_query(client, query, database, output_location, workgroup)
    wait_for_query(client, query_execution_id, timeout_seconds, poll_interval_seconds)
    count = read_count_result(client, query_execution_id)

    if count < min_count:
        raise AthenaQueryError(
            f'Expected at least {min_count} row(s) in "{database}"."{table}" with spotprice != -1; got {count}'
        )

    return QueryResult(query_execution_id=query_execution_id, count=count)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Azure ingestion monitor data through Athena.")
    parser.add_argument("--database", default=os.getenv("ATHENA_DATABASE", "default"))
    parser.add_argument("--table", default=os.getenv("ATHENA_TABLE", "azure_ingestion_monitor"))
    parser.add_argument("--output-location", default=os.getenv("ATHENA_OUTPUT_LOCATION"), required=False)
    parser.add_argument("--workgroup", default=os.getenv("ATHENA_WORKGROUP"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("ATHENA_QUERY_TIMEOUT_SECONDS", DEFAULT_QUERY_TIMEOUT_SECONDS)),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=float(os.getenv("ATHENA_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)),
    )
    parser.add_argument("--min-count", type=int, default=int(os.getenv("ATHENA_MIN_COUNT", "1")))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.output_location:
        print("ATHENA_OUTPUT_LOCATION or --output-location is required", file=sys.stderr)
        return 2

    import boto3

    client = boto3.client("athena", region_name=args.region)
    result = run_monitor_check(
        client=client,
        database=args.database,
        table=args.table,
        output_location=args.output_location,
        workgroup=args.workgroup,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        min_count=args.min_count,
    )
    print(
        f"Athena query {result.query_execution_id} succeeded: "
        f"found {result.count} row(s) with spotprice != -1."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
