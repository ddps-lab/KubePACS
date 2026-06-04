import unittest

from scripts.check_azure_ingestion_monitor import (
    AthenaQueryError,
    AthenaQueryTimeout,
    build_monitor_query,
    read_count_result,
    run_monitor_check,
    wait_for_query,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeAthenaClient:
    def __init__(self, states, count="3"):
        self.states = list(states)
        self.count = count
        self.started_requests = []
        self.get_query_execution_calls = 0

    def start_query_execution(self, **request):
        self.started_requests.append(request)
        return {"QueryExecutionId": "query-123"}

    def get_query_execution(self, QueryExecutionId):
        self.get_query_execution_calls += 1
        index = min(self.get_query_execution_calls - 1, len(self.states) - 1)
        state = self.states[index]
        status = {"State": state}
        if state == "FAILED":
            status["StateChangeReason"] = "synthetic failure"
        return {"QueryExecution": {"QueryExecutionId": QueryExecutionId, "Status": status}}

    def get_query_results(self, QueryExecutionId, MaxResults):
        return {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "_col0"}]},
                    {"Data": [{"VarCharValue": self.count}]},
                ]
            }
        }


class AthenaIngestionMonitorTest(unittest.TestCase):
    def test_build_monitor_query_quotes_database_and_table(self):
        self.assertEqual(
            build_monitor_query("default", "azure_ingestion_monitor"),
            'SELECT count(*) FROM "default"."azure_ingestion_monitor" WHERE spotprice != -1',
        )

    def test_wait_keeps_polling_after_ten_seconds_when_query_is_running(self):
        clock = FakeClock()
        client = FakeAthenaClient(["RUNNING", "RUNNING", "RUNNING", "SUCCEEDED"])

        execution = wait_for_query(
            client,
            "query-123",
            timeout_seconds=30,
            poll_interval_seconds=5,
            clock=clock,
            sleeper=clock.sleep,
        )

        self.assertEqual(execution["Status"]["State"], "SUCCEEDED")
        self.assertEqual(clock.now, 15)
        self.assertEqual(client.get_query_execution_calls, 4)

    def test_wait_times_out_after_configured_limit(self):
        clock = FakeClock()
        client = FakeAthenaClient(["RUNNING"])

        with self.assertRaises(AthenaQueryTimeout):
            wait_for_query(
                client,
                "query-123",
                timeout_seconds=12,
                poll_interval_seconds=5,
                clock=clock,
                sleeper=clock.sleep,
            )

        self.assertEqual(clock.now, 12)

    def test_wait_reports_failed_query_reason(self):
        client = FakeAthenaClient(["FAILED"])

        with self.assertRaisesRegex(AthenaQueryError, "synthetic failure"):
            wait_for_query(client, "query-123")

    def test_run_monitor_check_returns_count_after_success(self):
        client = FakeAthenaClient(["QUEUED", "RUNNING", "SUCCEEDED"], count="7")

        result = run_monitor_check(
            client,
            database="default",
            table="azure_ingestion_monitor",
            output_location="s3://example-athena-results/",
            timeout_seconds=30,
            poll_interval_seconds=0,
            min_count=1,
        )

        self.assertEqual(result.query_execution_id, "query-123")
        self.assertEqual(result.count, 7)
        self.assertEqual(client.started_requests[0]["QueryString"], build_monitor_query("default", "azure_ingestion_monitor"))

    def test_read_count_result_requires_data_row(self):
        class EmptyResultClient:
            def get_query_results(self, QueryExecutionId, MaxResults):
                return {"ResultSet": {"Rows": []}}

        with self.assertRaises(AthenaQueryError):
            read_count_result(EmptyResultClient(), "query-123")


if __name__ == "__main__":
    unittest.main()
