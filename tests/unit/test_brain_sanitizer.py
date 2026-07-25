"""Tests for src/brain/sanitizer.py.

The sanitizer should remove obviously-bad standalone sentences (compliment
openers, over-eager openings, formal closings) WITHOUT truncating multi-
sentence responses where a banned fragment appears mid-sentence.

The regression case: previously, "Hello! How can I assist you today?" was being
truncated to "Hello!" because Pass 1 substring-matched "how can i assist"
inside the second sentence. The sanitizer must now preserve such responses.
"""

from src.brain.sanitizer import sanitize_response


class TestRoundTrip:
    """Multi-sentence responses with embedded service phrases must survive."""

    def test_hello_followed_by_service_offer_round_trips(self):
        # The exact failure case from the integration session.
        text = "Hello! How can I assist you today?"
        assert sanitize_response(text) == text

    def test_paragraph_with_let_me_know_mid_sentence(self):
        text = "The capital of France is Paris. Let me know if you want some history."
        # First sentence kept; second is a "let me know if..." construction
        # that line-level cleanup also matches — but only when it begins the
        # line. Here it begins a NEW sentence on the same line, so the line-
        # level patterns don't fire (they anchor on line start, not sentence).
        result = sanitize_response(text)
        assert "Paris" in result
        assert "Paris." in result

    def test_long_response_with_want_me_to_phrase(self):
        text = "Sure, the API uses JSON. Want me to look up the auth endpoint for you?"
        result = sanitize_response(text)
        # The sentence is longer than the banned phrase — must survive.
        assert "auth endpoint" in result


class TestStripsTrueOpeners:
    """Standalone openers should still be stripped."""

    def test_strips_standalone_absolutely(self):
        assert sanitize_response("Absolutely!") == ""

    def test_strips_standalone_of_course(self):
        assert sanitize_response("Of course.") == ""

    def test_strips_standalone_great_question(self):
        assert sanitize_response("Great question!") == ""

    def test_strips_standalone_service_offer(self):
        # "How can I assist?" alone is just filler.
        assert sanitize_response("How can I assist?") == ""

    def test_strips_opener_keeps_following_content(self):
        text = "Absolutely! The capital of France is Paris."
        result = sanitize_response(text)
        assert "Absolutely" not in result
        assert "Paris" in result


class TestEmptyAndWhitespace:
    def test_empty_string(self):
        assert sanitize_response("") == ""

    def test_whitespace_only(self):
        assert sanitize_response("   \n  ") == "   \n  "

    def test_no_banned_content(self):
        text = "The Eiffel Tower is 330 meters tall."
        assert sanitize_response(text) == text
