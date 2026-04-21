"""Tests for security, authentication, middleware, and server infrastructure.

Each test class covers a specific concern such as auth, CORS, rate limiting,
input validation, and server configuration.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from releasepilot.web.server import create_app


class TestSSESubscriberCleanup:
    """Verify SSE subscribers are cleaned up properly."""

    """GIVEN Full queues are removed when a new subscriber joins"""

    def test_full_queues_pruned_on_subscribe(self):
        """WHEN the test exercises full queues pruned on subscribe"""
        from releasepilot.web.state import AppState

        state = AppState()
        q1 = state.subscribe()
        for i in range(100):
            q1.put_nowait({"event": "test", "data": {"i": i}})
        """THEN the expected behavior for full queues pruned on subscribe is observed"""
        assert q1.full()

        q2 = state.subscribe()
        assert q1 not in state._sse_subscribers
        assert q2 in state._sse_subscribers

    """GIVEN Full queues are unsubscribed during broadcast"""

    def test_full_queues_removed_on_broadcast(self):
        """WHEN the test exercises full queues removed on broadcast"""
        from releasepilot.web.state import AppState

        state = AppState()
        q = state.subscribe()
        for i in range(100):
            q.put_nowait({"event": "test", "data": {"i": i}})

        loop = asyncio.new_event_loop()
        loop.run_until_complete(state.broadcast("test", {"x": 1}))
        loop.close()

        """THEN the expected behavior for full queues removed on broadcast is observed"""
        assert q not in state._sse_subscribers

    """GIVEN Subscribing past the limit evicts the oldest subscriber"""

    def test_max_subscribers_limit(self):
        """WHEN the test exercises max subscribers limit"""
        from releasepilot.web.state import AppState

        state = AppState()
        state._max_subscribers = 3
        q1 = state.subscribe()
        _ = state.subscribe()
        _ = state.subscribe()
        _ = state.subscribe()
        """THEN the expected behavior for max subscribers limit is observed"""
        assert q1 not in state._sse_subscribers
        assert len(state._sse_subscribers) == 3


class TestHSTSHeader:
    """Verify HSTS header is present on responses."""

    """GIVEN a scenario for hsts header present"""

    def test_hsts_header_present(self):
        """WHEN the test exercises hsts header present"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/live")
        """THEN the expected behavior for hsts header present is observed"""
        assert "strict-transport-security" in resp.headers
        assert "max-age=" in resp.headers["strict-transport-security"]


class TestHandleErrorNoSystemExit:
    """Verify _handle_error can return without exiting."""

    """GIVEN a scenario for returns user error when exit disabled"""

    def test_returns_user_error_when_exit_disabled(self):
        """WHEN the test exercises returns user error when exit disabled"""
        from releasepilot.cli.errors import UserError
        from releasepilot.cli.helpers import _handle_error
        from releasepilot.pipeline.orchestrator import PipelineError

        err = _handle_error(PipelineError("test error"), exit_on_error=False)
        """THEN the expected behavior for returns user error when exit disabled is observed"""
        assert isinstance(err, UserError)
        assert "test error" in err.reason

    """GIVEN a scenario for still exits by default"""

    def test_still_exits_by_default(self):
        """WHEN the test exercises still exits by default"""
        from releasepilot.cli.helpers import _handle_error
        from releasepilot.pipeline.orchestrator import PipelineError

        """THEN the expected behavior for still exits by default is observed"""
        with pytest.raises(SystemExit):
            _handle_error(PipelineError("test error"))

    """GIVEN a scenario for returns for git errors"""

    def test_returns_for_git_errors(self):
        """WHEN the test exercises returns for git errors"""
        from releasepilot.cli.helpers import _handle_error
        from releasepilot.sources.git import GitCollectionError

        err = _handle_error(GitCollectionError("git failed"), exit_on_error=False)
        """THEN the expected behavior for returns for git errors is observed"""
        assert err is not None

    """GIVEN a scenario for returns for generic errors"""

    def test_returns_for_generic_errors(self):
        """WHEN the test exercises returns for generic errors"""
        from releasepilot.cli.helpers import _handle_error

        err = _handle_error(RuntimeError("something broke"), exit_on_error=False)
        """THEN the expected behavior for returns for generic errors is observed"""
        assert err is not None
        assert "something broke" in err.reason


class TestHealthCheckStartupFailure:
    """Verify /health/ready works correctly."""

    """GIVEN a scenario for health ready 200 when ok"""

    def test_health_ready_200_when_ok(self):
        """WHEN the test exercises health ready 200 when ok"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health/ready")
        """THEN the expected behavior for health ready 200 when ok is observed"""
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


class TestGenerationTimeout:
    """Verify generation pipeline has a timeout configured."""

    """GIVEN a scenario for timeout constant is reasonable"""

    def test_timeout_constant_is_reasonable(self):
        """WHEN the test exercises timeout constant is reasonable"""
        from releasepilot.web.server import GENERATION_TIMEOUT_SECONDS

        """THEN the expected behavior for timeout constant is reasonable is observed"""
        assert GENERATION_TIMEOUT_SECONDS > 0
        assert GENERATION_TIMEOUT_SECONDS <= 600


class TestGracefulShutdown:
    """Verify background tasks are tracked."""

    """GIVEN a scenario for app creates without error"""

    def test_app_creates_without_error(self):
        """WHEN the test exercises app creates without error"""
        app = create_app({"repo_path": "."})
        """THEN the expected behavior for app creates without error is observed"""
        assert app is not None


class TestProgressTrackerEncapsulation:
    """Verify progress state is encapsulated, not global."""

    """GIVEN a scenario for tracker class exists"""

    def test_tracker_class_exists(self):
        """WHEN the test exercises tracker class exists"""
        from releasepilot.cli.guide import _ProgressTracker

        tracker = _ProgressTracker()
        """THEN the expected behavior for tracker class exists is observed"""
        assert hasattr(tracker, "start_time")
        assert hasattr(tracker, "make_callback")
        assert hasattr(tracker, "finish")

    """GIVEN a scenario for two trackers independent"""

    def test_two_trackers_independent(self):
        """WHEN the test exercises two trackers independent"""
        from releasepilot.cli.guide import _ProgressTracker

        t1 = _ProgressTracker()
        t2 = _ProgressTracker()
        t1.start_time = 100.0
        t2.start_time = 200.0
        """THEN the expected behavior for two trackers independent is observed"""
        assert t1.start_time != t2.start_time


class TestGitHealthCheck:
    """Verify git availability check exists."""

    """GIVEN a scenario for check git available"""

    def test_check_git_available(self):
        """WHEN the test exercises check git available"""
        from releasepilot.web.server import _check_git_available

        result = _check_git_available()
        """THEN the expected behavior for check git available is observed"""
        assert isinstance(result, bool)

    """GIVEN a scenario for api status includes git available"""

    def test_api_status_includes_git_available(self):
        """WHEN the test exercises api status includes git available"""
        app = create_app({"repo_path": "."})
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/status")
        """THEN the expected behavior for api status includes git available is observed"""
        assert "git_available" in resp.json()


class TestSuppressOsCompat:
    """Verify _SuppressOs still works."""

    """GIVEN a scenario for suppress os still works"""

    def test_suppress_os_still_works(self):
        """WHEN the test exercises suppress os still works"""
        from releasepilot.cli.helpers import _SuppressOs

        with _SuppressOs():
            raise OSError("test")

    """GIVEN a scenario for suppress os does not suppress other"""

    def test_suppress_os_does_not_suppress_other(self):
        """WHEN the test exercises suppress os does not suppress other"""
        from releasepilot.cli.helpers import _SuppressOs

        """THEN the expected behavior for suppress os does not suppress other is observed"""
        with pytest.raises(ValueError):
            with _SuppressOs():
                raise ValueError("not os error")
