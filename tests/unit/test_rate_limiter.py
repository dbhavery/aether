"""Tests for token bucket rate limiter."""

from src.core.rate_limiter import check_rate_limit, clear_bucket


def test_allows_messages_within_limit():
    cid = "test_conn_allow"
    for _ in range(20):
        assert check_rate_limit(cid) is True
    clear_bucket(cid)


def test_blocks_after_limit_exceeded():
    cid = "test_conn_block"
    # Exhaust the bucket
    for _ in range(20):
        check_rate_limit(cid)
    # 21st message should be blocked
    assert check_rate_limit(cid) is False
    clear_bucket(cid)


def test_refills_over_time():
    cid = "test_conn_refill"
    # Exhaust most tokens
    for _ in range(19):
        check_rate_limit(cid)
    # Force a small time advance by modifying the bucket
    from src.core.rate_limiter import _buckets

    _buckets[cid]["last_refill"] -= 10.0  # simulate 10 seconds passing
    # Should have refilled ~3.3 tokens
    assert check_rate_limit(cid) is True
    clear_bucket(cid)


def test_clear_bucket_removes_state():
    cid = "test_conn_clear"
    check_rate_limit(cid)
    clear_bucket(cid)
    from src.core.rate_limiter import _buckets

    assert cid not in _buckets
