#!/usr/bin/env python3
"""Offline regression tests for paper-search HTTP and worker isolation.

Run: python3 scripts/selftest_runtime.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import _http_runtime
import requests
import search_papers
import search_papers_by_arxiv
import search_papers_by_openreview
import source_worker

ENV_KEYS = {
    "PAPER_SEARCH_TIMEOUT_SECONDS",
    "PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS",
    "PAPER_SEARCH_MAX_ATTEMPTS",
    "PAPER_SEARCH_SOURCE_BUDGET_SECONDS",
    *(
        f"PAPER_SEARCH_{source.upper()}_TIMEOUT_SECONDS"
        for source in search_papers.ALL_SOURCES
    ),
    *(
        f"PAPER_SEARCH_{source.upper()}_BUDGET_SECONDS"
        for source in search_papers.ALL_SOURCES
    ),
}


class FakeResponse:
    def __init__(self, status_code: int, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []
        self.mounts = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0) if self.responses else FakeResponse(200)

    def mount(self, prefix, adapter):
        self.mounts[prefix] = adapter


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            key: os.environ[key] for key in ENV_KEYS if key in os.environ
        }
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(self._saved_env)

    def test_timeout_defaults_override_and_validation(self):
        default = _http_runtime.get_http_config("open_alex")
        self.assertEqual(default.timeout, (15.0, 300.0))
        self.assertEqual(default.max_attempts, 4)

        os.environ["PAPER_SEARCH_TIMEOUT_SECONDS"] = "90"
        os.environ["PAPER_SEARCH_OPEN_ALEX_TIMEOUT_SECONDS"] = "12.5"
        os.environ["PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS"] = "2"
        overridden = _http_runtime.get_http_config("open_alex")
        self.assertEqual(overridden.timeout, (2.0, 12.5))

        os.environ["PAPER_SEARCH_MAX_ATTEMPTS"] = "0"
        with self.assertRaisesRegex(ValueError, "positive integer"):
            _http_runtime.validate_environment(["open_alex"])

    def test_timeout_environment_rejects_every_non_positive_or_malformed_value(self):
        numeric_keys = (
            "PAPER_SEARCH_TIMEOUT_SECONDS",
            "PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS",
            "PAPER_SEARCH_ARXIV_TIMEOUT_SECONDS",
        )
        for key in numeric_keys:
            for value in ("", "0", "-1", "nan", "inf", "not-a-number"):
                with self.subTest(key=key, value=value):
                    os.environ[key] = value
                    with self.assertRaises(ValueError):
                        _http_runtime.validate_environment(["arxiv"])
                    os.environ.pop(key)

        for value in ("", "0", "-1", "1.5", "not-an-integer"):
            with self.subTest(key="PAPER_SEARCH_MAX_ATTEMPTS", value=value):
                os.environ["PAPER_SEARCH_MAX_ATTEMPTS"] = value
                with self.assertRaises(ValueError):
                    _http_runtime.validate_environment(["arxiv"])
                os.environ.pop("PAPER_SEARCH_MAX_ATTEMPTS")

    def test_connection_failure_is_bounded_by_connect_timeout(self):
        os.environ["PAPER_SEARCH_MAX_ATTEMPTS"] = "1"
        session = mock.Mock()
        session.request.side_effect = requests.exceptions.ConnectTimeout("no route")
        with self.assertRaises(requests.exceptions.ConnectTimeout):
            _http_runtime.request(
                session, "GET", "https://example.invalid", source="open_alex"
            )
        self.assertEqual(session.request.call_count, 1)
        self.assertEqual(session.request.call_args.kwargs["timeout"], (15.0, 300.0))

    def test_retry_is_bounded_and_passes_timeout_tuple(self):
        session = FakeSession([FakeResponse(429) for _ in range(4)])
        with mock.patch.object(_http_runtime.time, "sleep") as sleep:
            response = _http_runtime.request(
                session, "GET", "https://example.invalid", source="crossref"
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(session.calls), 4)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list], [3.0, 6.0, 12.0]
        )
        self.assertTrue(
            all(call[2]["timeout"] == (15.0, 300.0) for call in session.calls)
        )

    def test_external_session_gets_timeout_and_finite_adapter(self):
        session = FakeSession()
        _http_runtime.configure_external_session(session, "openreview")
        session.request("GET", "https://example.invalid")
        self.assertEqual(session.calls[0][2]["timeout"], (15.0, 300.0))
        self.assertEqual(session.mounts["https://"].max_retries.total, 3)
        self.assertNotIn("POST", session.mounts["https://"].max_retries.allowed_methods)
        self.assertTrue(
            session.mounts["https://"].max_retries.respect_retry_after_header
        )

    def test_transient_network_errors_are_retried_for_get_only(self):
        session = mock.Mock()
        session.request.side_effect = [
            requests.exceptions.ConnectionError("reset"),
            FakeResponse(200),
        ]
        with mock.patch.object(_http_runtime.time, "sleep") as sleep:
            response = _http_runtime.request(
                session, "GET", "https://example.invalid", source="open_alex"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.request.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_read_timeout_is_idle_not_total_duration(self):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format, *_args):
                pass

            def do_GET(self):
                body = b"abcd"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    for index, byte in enumerate(body):
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        if self.path == "/stall" and index == 0:
                            time.sleep(0.25)
                        elif self.path == "/progress" and index < len(body) - 1:
                            time.sleep(0.07)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        os.environ["PAPER_SEARCH_TIMEOUT_SECONDS"] = "0.12"
        os.environ["PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS"] = "0.12"
        os.environ["PAPER_SEARCH_MAX_ATTEMPTS"] = "1"
        session = _http_runtime.create_session()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(requests.exceptions.RequestException):
                _http_runtime.request(session, "GET", base + "/stall", source="arxiv")
            response = _http_runtime.request(
                session, "GET", base + "/progress", source="arxiv"
            )
            self.assertEqual(response.content, b"abcd")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class WorkerTests(unittest.TestCase):
    def test_worker_uses_native_multi_query_connector_when_available(self):
        calls = []

        def batch_connector(queries, _start, _end, _limit, **_kwargs):
            calls.append(queries)
            return [
                {
                    "title": "shared",
                    "source": "openreview",
                    "retrieval_ranks": [
                        {"query": "first", "rank": 1, "source": "openreview"},
                        {"query": "second", "rank": 2, "source": "openreview"},
                    ],
                }
            ]

        with (
            mock.patch.object(
                source_worker, "_load_source_func", return_value=mock.Mock()
            ),
            mock.patch.object(
                source_worker, "_load_batch_source_func", return_value=batch_connector
            ),
        ):
            payload = source_worker.run_source(
                "openreview", ["first", "second"], 2025, 2026, 5
            )
        self.assertEqual(calls, [["first", "second"]])
        self.assertEqual(len(payload["papers"][0]["retrieval_ranks"]), 2)

    def test_worker_preserves_query_order_and_continues_after_error(self):
        calls = []

        def connector(query, start_year, end_year, max_results, **_kwargs):
            calls.append((query, start_year, end_year, max_results))
            if query == "bad":
                raise RuntimeError("boom")
            return [
                {"title": query, "source": "arxiv"},
                {"title": "duplicate", "source": "arxiv"},
            ]

        with mock.patch.object(
            source_worker, "_load_source_func", return_value=connector
        ):
            payload = source_worker.run_source(
                "arxiv", ["first", "bad", "last"], 2020, 2026, 7
            )
        self.assertEqual(
            [paper["title"] for paper in payload["papers"]],
            ["duplicate", "first", "last"],
        )
        self.assertEqual([call[0] for call in calls], ["first", "bad", "last"])
        self.assertTrue(all(call[3] == 7 for call in calls))
        self.assertEqual(payload["errors"][0]["query"], "bad")

    def test_worker_applies_final_per_source_limit_after_multi_query_dedup(self):
        def connector(query, _start_year, _end_year, _max_results, **_kwargs):
            return [
                {"title": "shared", "source": "arxiv"},
                {"title": query, "source": "arxiv"},
            ]

        with mock.patch.object(
            source_worker, "_load_source_func", return_value=connector
        ):
            payload = source_worker.run_source(
                "arxiv", ["first", "second"], 2020, 2026, 2
            )
        self.assertEqual(
            [paper["title"] for paper in payload["papers"]], ["shared", "first"]
        )

    def test_programmatic_results_retain_per_source_errors(self):
        with mock.patch.object(source_worker, "_load_source_func") as load:
            load.return_value.side_effect = RuntimeError("upstream unavailable")
            payload = source_worker.run_source("arxiv", ["query"], 2020, 2026, 1)

        def command(_source, _queries, _start_year, _end_year, _max_results, out_path):
            code = (
                "import json,sys; "
                "json.dump(" + repr(payload) + ",open(sys.argv[1],'w'))"
            )
            return [sys.executable, "-c", code, str(out_path)]

        with mock.patch.object(search_papers, "_worker_command", command):
            result = search_papers._run_source_workers(
                ["arxiv"], ["query"], 2020, 2026, 1, parallel=False
            )
        self.assertEqual(result["arxiv"], [])
        self.assertEqual(result.errors["arxiv"][0]["query"], "query")
        self.assertEqual(result.errors["arxiv"][0]["type"], "RuntimeError")
        self.assertIn("upstream unavailable", result.errors["arxiv"][0]["message"])

    def test_connector_internal_diagnostics_reach_worker_payload(self):
        def connector(
            query, _start_year, _end_year, _max_results, diagnostics, source_options
        ):
            diagnostics.append(
                {"query": query, "type": "LookupError", "message": "v2 failed"}
            )
            return [{"title": "fallback result", "source": "openreview"}]

        with mock.patch.object(
            source_worker, "_load_source_func", return_value=connector
        ):
            payload = source_worker.run_source("openreview", ["query"], 2020, 2026, 1)
        self.assertEqual(payload["papers"][0]["title"], "fallback result")
        self.assertEqual(
            payload["errors"],
            [{"query": "query", "type": "LookupError", "message": "v2 failed"}],
        )

    def test_source_options_reach_connector(self):
        captured = {}

        def connector(
            _query, _start_year, _end_year, _max_results, diagnostics, source_options
        ):
            captured.update(source_options)
            return []

        with mock.patch.object(
            source_worker, "_load_source_func", return_value=connector
        ):
            source_worker.run_source(
                "openreview",
                ["query"],
                2025,
                2026,
                1,
                source_options={"venues": ["ICLR.cc/2026/Conference"]},
            )
        self.assertEqual(captured["venues"], ["ICLR.cc/2026/Conference"])

    def test_worker_ranks_all_queries_before_final_limit(self):
        def connector(query, _start_year, _end_year, _max_results, **_kwargs):
            if query == "broad":
                return [
                    {"title": "Broad weak one", "source": "arxiv"},
                    {"title": "Broad weak two", "source": "arxiv"},
                ]
            return [{"title": "Exact target breakthrough", "source": "arxiv"}]

        with mock.patch.object(
            source_worker, "_load_source_func", return_value=connector
        ):
            payload = source_worker.run_source(
                "arxiv", ["broad", "exact target"], 2020, 2026, 2
            )
        titles = [paper["title"] for paper in payload["papers"]]
        self.assertIn("Exact target breakthrough", titles)

    def test_atomic_result_envelope(self):
        payload = {"source": "arxiv", "papers": [{"title": "x"}], "errors": []}
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "result.json"
            source_worker.write_atomic(out, payload)
            self.assertEqual(json.loads(out.read_text()), payload)
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_search_results_json_envelope_keeps_errors(self):
        result = search_papers.SearchResults(
            {"arxiv": []},
            {"arxiv": [{"query": "q", "type": "X", "message": "failed"}]},
        )
        envelope = json.loads(json.dumps(result.to_dict()))
        self.assertEqual(envelope["papers"], {"arxiv": []})
        self.assertEqual(envelope["errors"]["arxiv"][0]["message"], "failed")

    def test_report_envelope_contains_ranked_records_and_stats(self):
        result = search_papers.SearchResults(
            {
                "arxiv": [
                    {
                        "title": "Relevant Paper",
                        "abstract": "widget gating",
                        "source": "arxiv",
                        "citation_count": None,
                    }
                ]
            },
            {"arxiv": []},
        )
        report = search_papers.build_report_envelope(
            result, ["widget gating"], start_year=2024, end_year=2026
        )
        self.assertEqual(report["stats"]["unique_papers"], 1)
        self.assertEqual(report["merged_ranked_papers"][0]["relevance_score"], 2)

    @staticmethod
    def _fake_worker_command(
        source, queries, start_year, end_year, max_results, out_path
    ):
        code = (
            "import json,sys,time; "
            "out,source=sys.argv[1:3]; "
            "started=time.time(); time.sleep(0.2); finished=time.time(); "
            "json.dump({'source':source,'papers':[{'source':source,'started':started,'finished':finished}],"
            "'errors':[]},open(out,'w'))"
        )
        return [sys.executable, "-c", code, str(out_path), source]

    def test_sources_overlap_in_parallel_and_serialize_when_disabled(self):
        sources = ["arxiv", "dblp"]
        with mock.patch.object(
            search_papers, "_worker_command", self._fake_worker_command
        ):
            parallel = search_papers._run_source_workers(
                sources, ["q"], 2020, 2026, 1, parallel=True
            )
            serial = search_papers._run_source_workers(
                sources, ["q"], 2020, 2026, 1, parallel=False
            )
        first_p, second_p = parallel["arxiv"][0], parallel["dblp"][0]
        self.assertLess(
            max(first_p["started"], second_p["started"]),
            min(first_p["finished"], second_p["finished"]),
        )
        first_s, second_s = serial["arxiv"][0], serial["dblp"][0]
        self.assertGreaterEqual(second_s["started"], first_s["finished"])
        self.assertEqual(list(parallel), sources)

    def test_worker_crash_and_invalid_json_do_not_cancel_other_sources(self):
        def command(source, queries, start_year, end_year, max_results, out_path):
            if source == "arxiv":
                return [sys.executable, "-c", "raise SystemExit(7)"]
            if source == "dblp":
                return [
                    sys.executable,
                    "-c",
                    "import sys; open(sys.argv[1],'w').write('not json')",
                    str(out_path),
                ]
            if source == "open_alex":
                return [sys.executable, "-c", "raise SystemExit(0)"]
            code = (
                "import json,sys; out,source=sys.argv[1:3]; "
                "json.dump({'source':source,'papers':[{'title':'ok'}],'errors':[]},open(out,'w'))"
            )
            return [sys.executable, "-c", code, str(out_path), source]

        sources = ["arxiv", "dblp", "open_alex", "crossref"]
        with mock.patch.object(search_papers, "_worker_command", command):
            result = search_papers._run_source_workers(
                sources, ["q"], 2020, 2026, 1, parallel=True
            )
        self.assertEqual(result["arxiv"], [])
        self.assertEqual(result["dblp"], [])
        self.assertEqual(result["open_alex"], [])
        self.assertEqual(result["crossref"], [{"title": "ok"}])

    def test_interrupt_terminates_all_started_workers(self):
        started = []
        original_start = search_papers._start_worker

        def command(_source, _queries, _start_year, _end_year, _max_results, _out):
            return [sys.executable, "-c", "import time; time.sleep(30)"]

        def recording_start(*args, **kwargs):
            state = original_start(*args, **kwargs)
            started.append(state[0])
            return state

        with (
            mock.patch.object(search_papers, "_worker_command", command),
            mock.patch.object(
                search_papers, "_start_worker", side_effect=recording_start
            ),
            mock.patch.object(
                search_papers, "_collect_worker", side_effect=KeyboardInterrupt
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            search_papers._run_source_workers(
                ["arxiv", "dblp"], ["q"], 2020, 2026, 1, parallel=True
            )

        self.assertEqual(len(started), 2)
        self.assertTrue(all(process.poll() is not None for process in started))

    def test_public_api_keeps_order_and_applies_date_filter_after_workers(self):
        raw = {
            "dblp": [{"title": "old", "publication_date": "2023-01-01"}],
            "arxiv": [{"title": "new", "publication_date": "2025-02-01"}],
        }
        with mock.patch.object(search_papers, "_run_source_workers", return_value=raw):
            result = search_papers.search_papers(
                "q",
                2023,
                2025,
                sources=["dblp", "arxiv"],
                start_date="2024-01-01",
            )
        self.assertEqual(list(result), ["dblp", "arxiv"])
        self.assertEqual(result["dblp"], [])
        self.assertEqual(result["arxiv"][0]["title"], "new")

    def test_source_wall_clock_budget_terminates_worker(self):
        def command(_source, _queries, _start_year, _end_year, _max_results, _out):
            return [sys.executable, "-c", "import time; time.sleep(5)"]

        with (
            mock.patch.dict(
                os.environ, {"PAPER_SEARCH_ARXIV_BUDGET_SECONDS": "0.1"}, clear=False
            ),
            mock.patch.object(search_papers, "_worker_command", command),
        ):
            started = time.monotonic()
            result = search_papers._run_source_workers(
                ["arxiv"], ["q"], 2020, 2026, 1, parallel=False
            )
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(result["arxiv"], [])
        self.assertEqual(result.errors["arxiv"][0]["type"], "SourceBudgetExceeded")

    def test_public_api_validates_ranges_and_source_options(self):
        with self.assertRaisesRegex(ValueError, "start_year"):
            search_papers.search_papers("q", 2026, 2025, sources=["arxiv"])
        with self.assertRaisesRegex(ValueError, "max_results"):
            search_papers.search_papers("q", 2025, 2026, -1, sources=["arxiv"])
        with self.assertRaisesRegex(ValueError, "unknown open_alex"):
            search_papers.search_papers(
                "q",
                2025,
                2026,
                sources=["open_alex"],
                source_options={"open_alex": {"unknown": True}},
            )
        with self.assertRaisesRegex(ValueError, "scan_limit_per_venue"):
            search_papers.search_papers(
                "q",
                2025,
                2026,
                sources=["openreview"],
                source_options={"openreview": {"scan_limit_per_venue": 0}},
            )

    def test_invalid_runtime_configuration_fails_before_starting_workers(self):
        with (
            mock.patch.dict(
                os.environ, {"PAPER_SEARCH_TIMEOUT_SECONDS": "invalid"}, clear=False
            ),
            mock.patch.object(search_papers, "_run_source_workers") as run_workers,
        ):
            with self.assertRaises(ValueError):
                search_papers.search_papers(
                    "q", 2023, 2025, sources=["arxiv"], parallel=True
                )
        run_workers.assert_not_called()


class OpenReviewTests(unittest.TestCase):
    def test_multi_query_search_scans_each_venue_once(self):
        calls = []

        def fake_scan(_client, venue, *_args):
            calls.append(venue)
            return [
                {
                    "title": "Reasoning code distillation",
                    "authors": [],
                    "year": 2025,
                    "abstract": "policy optimization",
                    "url": f"https://example/{venue}",
                    "venue": venue,
                    "citation_count": None,
                    "publication_date": "2025-01-01",
                    "source": "openreview",
                    "doi": None,
                    "arxiv_id": None,
                }
            ]

        with (
            mock.patch.object(
                search_papers_by_openreview,
                "_openreview_clients",
                return_value=object(),
            ),
            mock.patch.object(
                search_papers_by_openreview, "_scan_venue", side_effect=fake_scan
            ),
            mock.patch.object(search_papers_by_openreview.time, "sleep"),
        ):
            papers = search_papers_by_openreview.search_papers_by_openreview_queries(
                ["reasoning code", "policy optimization"],
                2025,
                2025,
                5,
                venues=["venue-a", "venue-b"],
                source_options={"mode": "remote"},
            )
        self.assertEqual(calls, ["venue-a", "venue-b"])
        self.assertTrue(all(len(paper["retrieval_ranks"]) == 2 for paper in papers))

    def test_v2_client_is_configured_before_login(self):
        created = []

        class Client:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.session = FakeSession()
                self.logins = []
                created.append(self)

            def login_user(self, **kwargs):
                self.logins.append(kwargs)
                self.session.request("POST", self.kwargs["baseurl"] + "/login")

        fake_openreview = type(
            "FakeOpenReview",
            (),
            {"api": type("API", (), {"OpenReviewClient": Client}), "Client": Client},
        )
        env = {"OPENREVIEW_USER": "user", "OPENREVIEW_PASS": "pass"}
        with (
            mock.patch.dict(sys.modules, {"openreview": fake_openreview}),
            mock.patch.dict(os.environ, env, clear=False),
        ):
            search_papers_by_openreview._CLIENT_CACHE.clear()
            client = search_papers_by_openreview._openreview_clients()
            cached = search_papers_by_openreview._openreview_clients()
            search_papers_by_openreview._CLIENT_CACHE.clear()

        self.assertEqual(len(created), 1)
        self.assertIs(client, cached)
        self.assertEqual(client.kwargs, {"baseurl": "https://api2.openreview.net"})
        self.assertEqual(client.logins, [{"username": "user", "password": "pass"}])
        self.assertEqual(client.session.calls[0][2]["timeout"], (15.0, 300.0))

    def test_submission_invitation_comes_from_venue_group(self):
        class Group:
            content = {"submission_name": {"value": "Paper_Submission"}}

        class Client:
            def get_group(self, venue):
                self.venue = venue
                return Group()

        client = Client()
        invitation = search_papers_by_openreview._resolve_submission_invitation(
            client, "ICLR.cc/2026/Conference"
        )
        self.assertEqual(invitation, "ICLR.cc/2026/Conference/-/Paper_Submission")
        self.assertEqual(client.venue, "ICLR.cc/2026/Conference")

    def test_submission_invitation_falls_back_to_known_suffixes(self):
        class Client:
            def get_group(self, _venue):
                return type("Group", (), {"content": {}})()

            def get_invitation(self, invitation):
                # Only the plain Submission suffix exists (e.g. TMLR).
                if invitation.endswith("/-/Submission"):
                    return object()
                raise RuntimeError(f"NotFound: {invitation}")

        invitation = search_papers_by_openreview._resolve_submission_invitation(
            Client(), "TMLR"
        )
        self.assertEqual(invitation, "TMLR/-/Submission")

    def test_notes_are_paged_with_offset(self):
        class Note:
            def __init__(self, note_id):
                self.id = note_id

        class Client:
            def __init__(self):
                self.calls = []

            def get_notes(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return [Note("n1"), Note("n2")]
                if len(self.calls) == 2:
                    return [Note("n3")]
                return []

        client = Client()
        notes = list(
            search_papers_by_openreview._iter_notes(client, "Venue/-/Submission", 2)
        )
        self.assertEqual([note.id for note in notes], ["n1", "n2", "n3"])
        self.assertEqual(
            client.calls[0],
            {"invitation": "Venue/-/Submission", "limit": 2, "offset": 0},
        )
        self.assertEqual(
            client.calls[1],
            {"invitation": "Venue/-/Submission", "limit": 2, "offset": 2},
        )

    def test_notes_paging_dedupes_unstable_ordering(self):
        class Note:
            def __init__(self, note_id):
                self.id = note_id

        class Client:
            def __init__(self):
                self.calls = []

            def get_notes(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return [Note("n1"), Note("n2")]  # n2 reappears on page 2
                if len(self.calls) == 2:
                    return [Note("n2"), Note("n3")]
                return []

        client = Client()
        notes = list(
            search_papers_by_openreview._iter_notes(client, "Venue/-/Submission", 2)
        )
        self.assertEqual([note.id for note in notes], ["n1", "n2", "n3"])
        self.assertEqual(len(client.calls), 3)

    def test_static_registry_uses_verified_openreview_venue_shapes(self):
        static = search_papers_by_openreview._static_venues
        venues_2025 = static(2025, 2025, "v2")
        self.assertIn("colmweb.org/COLM/2025/Conference", venues_2025)
        self.assertIn("aistats.org/AISTATS/2025/Conference", venues_2025)
        self.assertIn("auai.org/UAI/2025/Conference", venues_2025)
        self.assertIn("robot-learning.org/CoRL/2025/Conference", venues_2025)
        self.assertIn("MLSys.org/2025/Conference", venues_2025)
        self.assertIn("TMLR", venues_2025)
        # Shell groups measured empty on 2026-09-07 must never be scanned again.
        self.assertNotIn("AAAI.org/2025/Conference", venues_2025)
        self.assertNotIn("thecvf.com/CVPR/2025/Conference", venues_2025)
        self.assertNotIn("thecvf.com/ICCV/2025/Conference", venues_2025)
        self.assertNotIn("aclweb.org/ACL/2025/Conference", venues_2025)
        self.assertEqual(
            sum(1 for venue in static(2022, 2027, "v2") if venue == "TMLR"), 1
        )
        # ICLR migrated to API v2 only in 2024; 2023 and earlier are v1-only.
        self.assertNotIn("ICLR.cc/2023/Conference", static(2023, 2023, "v2"))
        self.assertIn("ICLR.cc/2023/Conference", static(2023, 2023, "v1"))
        self.assertIn("NeurIPS.cc/2022/Conference", static(2022, 2022, "v1"))
        self.assertNotIn("NeurIPS.cc/2022/Conference", static(2022, 2022, "v2"))
        self.assertEqual(static(2024, 2024, "v1"), [])

    def test_search_venue_scans_candidates_before_taking_top_results(self):
        class Note:
            def __init__(self, note_id, title, timestamp):
                self.id = note_id
                self.cdate = timestamp
                self.content = {
                    "title": {"value": title},
                    "abstract": {"value": "abstract"},
                    "authors": {"value": ["Author"]},
                }

        class Client:
            def get_group(self, _venue):
                return type(
                    "Group", (), {"content": {"submission_name": "Submission"}}
                )()

            def get_notes(self, **_kwargs):
                return [
                    Note("n1", "Unrelated", 1735689600000),
                    Note("n2", "Test-time scaling", 1735689600000),
                    Note(
                        "n3", "Test-time scaling with test-time search", 1735689600000
                    ),
                ]

        papers = search_papers_by_openreview._search_venue(
            Client(),
            "ICLR.cc/2025/Conference",
            "test-time search",
            2025,
            2025,
            1,
            "all",
        )
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "Test-time scaling with test-time search")

    def test_search_venue_reports_truncated_candidate_scan(self):
        notes = [
            type(
                "Note",
                (),
                {
                    "id": f"n{index}",
                    "cdate": 1735689600000,
                    "content": {
                        "title": {"value": "Test paper"},
                        "abstract": {"value": "abstract"},
                        "authors": {"value": ["Author"]},
                    },
                },
            )()
            for index in range(3)
        ]
        client = mock.Mock()
        client.get_group.return_value = type(
            "Group", (), {"content": {"submission_name": "Submission"}}
        )()
        client.get_notes.return_value = notes
        diagnostics = []
        search_papers_by_openreview._search_venue(
            client,
            "ICLR.cc/2025/Conference",
            "test",
            2025,
            2025,
            1,
            "all",
            scan_limit=2,
            diagnostics=diagnostics,
        )
        self.assertEqual(diagnostics[0]["type"], "CandidateScanTruncated")

    def test_search_visits_every_venue_before_global_truncation(self):
        calls = []

        def fake_search(_client, venue, *_args):
            calls.append(venue)
            score = 1 if venue == "venue-a" else 3
            return [
                {
                    "title": venue,
                    "authors": [],
                    "year": 2025,
                    "abstract": "",
                    "url": f"https://example/{venue}",
                    "venue": venue,
                    "citation_count": None,
                    "publication_date": "2025-01-01",
                    "source": "openreview",
                    "doi": None,
                    "arxiv_id": None,
                    "_openreview_score": score,
                }
            ]

        with (
            mock.patch.object(
                search_papers_by_openreview,
                "_openreview_clients",
                return_value=object(),
            ),
            mock.patch.object(
                search_papers_by_openreview, "_search_venue", side_effect=fake_search
            ),
            mock.patch.object(search_papers_by_openreview.time, "sleep"),
        ):
            papers = search_papers_by_openreview.search_papers_by_openreview(
                "query",
                2025,
                2025,
                1,
                venues=["venue-a", "venue-b"],
                source_options={"mode": "remote"},
            )
        self.assertEqual(calls, ["venue-a", "venue-b"])
        self.assertEqual(papers[0]["title"], "venue-b")

    def test_venue_year_overrides_submission_creation_year(self):
        note = type(
            "Note",
            (),
            {
                "id": "paper-id",
                "cdate": 1735689600000,
                "content": {
                    "title": {"value": "Paper"},
                    "abstract": {"value": "Abstract"},
                    "authors": {"value": ["Author"]},
                },
            },
        )()
        paper = search_papers_by_openreview._or_note_to_paper(
            note, "ICLR.cc/2026/Conference"
        )
        self.assertEqual(paper["year"], 2026)
        self.assertEqual(paper["publication_date"], "2025-01-01")
        self.assertEqual(paper["publication_status"], "submitted")

    def test_openreview_all_status_preserves_withdrawn_state(self):
        note = type(
            "Note",
            (),
            {
                "id": "paper-id",
                "cdate": 1735689600000,
                "content": {
                    "title": {"value": "Paper"},
                    "abstract": {"value": "Abstract"},
                    "authors": {"value": ["Author"]},
                    "venueid": {
                        "value": "ICLR.cc/2025/Conference/Withdrawn_Submission"
                    },
                },
            },
        )()
        paper = search_papers_by_openreview._or_note_to_paper(
            note, "ICLR.cc/2025/Conference", status_filter="all"
        )
        self.assertEqual(paper["publication_status"], "withdrawn")


class ArxivSchemaTests(unittest.TestCase):
    def test_mock_response_matches_legacy_fixture_output(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <id>https://arxiv.org/abs/2401.12345v2</id>
            <published>2024-01-20T00:00:00Z</published>
            <title> A Test Paper </title>
            <summary> Abstract body. </summary>
            <author><name>Alice</name></author>
            <author><name>Bob</name></author>
            <arxiv:doi>10.1000/test</arxiv:doi>
          </entry>
        </feed>"""
        response = mock.Mock()
        response.content = xml.encode("utf-8")
        with mock.patch.object(
            search_papers_by_arxiv, "request", return_value=response
        ) as request:
            papers = search_papers_by_arxiv.search_papers_by_arxiv(
                "test query", 2024, 2026, 10
            )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(request.call_args.kwargs["source"], "arxiv")
        self.assertIs(
            request.call_args.kwargs["before_attempt"], search_papers_by_arxiv._throttle
        )
        self.assertEqual(
            papers,
            [
                {
                    "title": "A Test Paper",
                    "authors": ["Alice", "Bob"],
                    "year": 2024,
                    "abstract": "Abstract body.",
                    "url": "https://arxiv.org/abs/2401.12345v2",
                    "venue": "arXiv",
                    "citation_count": None,
                    "citation_source": None,
                    "publication_date": "2024-01-20",
                    "publication_status": "preprint",
                    "status_source": "arxiv",
                    "source": "arxiv",
                    "doi": "10.1000/test",
                    "arxiv_id": "2401.12345",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
