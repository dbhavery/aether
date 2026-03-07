"""Tests for Batch 12 — backchannel manager, filler generator, emotion tracker."""

from src.persona.backchannels import BackchannelManager, get_backchannel_manager
from src.persona.emotion_tracker import EmotionState, EmotionTracker, get_emotion_tracker
from src.persona.fillers import FillerGenerator, get_filler_generator


class TestBackchannelManager:
    def test_emotional_statement_triggers_backchannel(self):
        mgr = BackchannelManager()
        result = mgr.analyze("I'm so frustrated with this project, nothing is working")
        assert result is not None
        # May match frustration or emotional pool depending on pattern order
        all_valid = [
            "that sounds rough",
            "yeah, that sucks",
            "ugh, yeah",
            "yeah",
            "I hear you",
            "mm",
            "yeah, that's rough",
        ]
        assert result in all_valid

    def test_question_returns_silence(self):
        mgr = BackchannelManager()
        result = mgr.analyze("What do you think about that?")
        assert result is None

    def test_explanation_triggers_acknowledgment(self):
        mgr = BackchannelManager()
        result = mgr.analyze("So basically the reason I did that is because the API changed")
        assert result is not None
        assert result in ["mm-hmm", "right", "got it", "yeah"]

    def test_short_statement_no_backchannel(self):
        mgr = BackchannelManager()
        result = mgr.analyze("okay")
        assert result is None

    def test_empty_returns_none(self):
        mgr = BackchannelManager()
        assert mgr.analyze("") is None

    def test_no_repeat(self):
        mgr = BackchannelManager()
        results = set()
        for _ in range(10):
            # Use different frustration messages to trigger backchannels
            r = mgr.analyze("this stupid thing keeps breaking and I'm so frustrated")
            if r:
                results.add(r)
        # Should have gotten at least 2 different phrases
        assert len(results) >= 2

    def test_disabled_returns_none(self):
        mgr = BackchannelManager()
        mgr._enabled = False
        result = mgr.analyze("I'm so frustrated!")
        assert result is None

    def test_singleton(self):
        m1 = get_backchannel_manager()
        m2 = get_backchannel_manager()
        assert m1 is m2


class TestFillerGenerator:
    def test_simple_no_filler(self):
        gen = FillerGenerator()
        assert gen.get_filler("hi") is None
        assert gen.get_filler("what time is it?") is None
        assert gen.get_filler("thanks") is None

    def test_research_immediate_filler(self):
        gen = FillerGenerator()
        result = gen.get_filler("look up the latest news on AI")
        assert result is not None
        assert result in ["on it", "let me check", "one sec", "checking that now", "hold on, looking into it"]

    def test_complex_thinking_filler(self):
        gen = FillerGenerator()
        result = gen.get_filler("explain the difference between transformers and RNNs in detail")
        assert result is not None
        # Should be from the thinking pool
        valid_fillers = [
            "let me think about that",
            "hmm, good question",
            "give me a second",
            "that's interesting, let me think",
            "hmm, let me consider that",
        ]
        assert result in valid_fillers

    def test_classify_simple(self):
        gen = FillerGenerator()
        assert gen.classify_complexity("hello") == "simple"
        assert gen.classify_complexity("yes") == "simple"

    def test_classify_research(self):
        gen = FillerGenerator()
        assert gen.classify_complexity("search for python tutorials") == "research"
        assert gen.classify_complexity("open chrome") == "research"

    def test_classify_complex(self):
        gen = FillerGenerator()
        assert gen.classify_complexity("explain how neural networks work") == "complex"
        assert gen.classify_complexity("compare React vs Vue") == "complex"

    def test_long_message_classified_complex(self):
        gen = FillerGenerator()
        long_msg = "I was thinking about " + " ".join(["word"] * 25) + " and what that means"
        assert gen.classify_complexity(long_msg) == "complex"

    def test_cooldown_prevents_repeat(self):
        gen = FillerGenerator()
        gen.get_filler("search for something")
        # Mark all phrases as recently used except one
        import time

        for phrase in ["on it", "let me check", "one sec", "checking that now", "hold on, looking into it"]:
            gen._recent_fillers[phrase] = time.time()
        # Should still pick something (clears cooldowns when all exhausted)
        result = gen.get_filler("look up something else")
        assert result is not None

    def test_disabled_returns_none(self):
        gen = FillerGenerator()
        gen._enabled = False
        assert gen.get_filler("explain quantum physics") is None

    def test_singleton(self):
        g1 = get_filler_generator()
        g2 = get_filler_generator()
        assert g1 is g2


class TestEmotionTracker:
    def test_neutral_by_default(self):
        tracker = EmotionTracker()
        ctx = tracker.get_context()
        assert ctx.dominant_emotion == EmotionState.NEUTRAL

    def test_detects_frustration(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("this stupid thing keeps crashing, I'm so frustrated")
        assert snap.state == EmotionState.FRUSTRATED

    def test_detects_happy(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("this is awesome, I love it!")
        assert snap.state == EmotionState.HAPPY

    def test_detects_tired(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("I'm exhausted, long day at work")
        assert snap.state == EmotionState.TIRED

    def test_detects_anxious(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("I'm really worried about the deadline")
        assert snap.state == EmotionState.ANXIOUS

    def test_detects_excited(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("I figured it out! It finally works!")
        assert snap.state == EmotionState.EXCITED

    def test_detects_curious(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("I'm wondering how does that actually work?")
        assert snap.state == EmotionState.CURIOUS

    def test_neutral_for_plain_text(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("The meeting is at 3pm")
        assert snap.state == EmotionState.NEUTRAL

    def test_energy_decreases_on_frustration(self):
        tracker = EmotionTracker()
        initial_energy = tracker._energy
        tracker.analyze("this is broken, nothing works, I'm frustrated")
        assert tracker._energy < initial_energy

    def test_energy_increases_on_excitement(self):
        tracker = EmotionTracker()
        initial_energy = tracker._energy
        tracker.analyze("hell yeah, I'm so excited, let's go!")
        assert tracker._energy > initial_energy

    def test_energy_clamped_0_100(self):
        tracker = EmotionTracker()
        # Drive energy to 0
        for _ in range(20):
            tracker.analyze("I'm exhausted and burned out and tired")
        assert tracker._energy >= 0

        # Drive energy to 100
        tracker._energy = 90
        for _ in range(10):
            tracker.analyze("this is amazing, hell yeah, excited!!")
        assert tracker._energy <= 100

    def test_context_has_dominant_emotion(self):
        tracker = EmotionTracker()
        for _ in range(5):
            tracker.analyze("I'm frustrated, this is broken")
        ctx = tracker.get_context()
        assert ctx.dominant_emotion == EmotionState.FRUSTRATED

    def test_tone_hint_returns_string(self):
        tracker = EmotionTracker()
        tracker.analyze("I'm so frustrated with this")
        hint = tracker.get_tone_hint()
        assert isinstance(hint, str)
        assert len(hint) > 0

    def test_tone_hint_empty_for_neutral(self):
        tracker = EmotionTracker()
        hint = tracker.get_tone_hint()
        assert hint == ""

    def test_trend_detection(self):
        tracker = EmotionTracker()
        # Feed positive messages
        for _ in range(5):
            tracker.analyze("this is amazing, I'm excited!")
        ctx = tracker.get_context()
        assert ctx.trend in ("rising", "stable")

    def test_disabled_tracker(self):
        tracker = EmotionTracker()
        tracker._enabled = False
        tracker.analyze("I'm frustrated")
        # Window should be empty since disabled
        assert len(tracker._window) == 0

    def test_singleton(self):
        t1 = get_emotion_tracker()
        t2 = get_emotion_tracker()
        assert t1 is t2

    def test_sad_detection(self):
        tracker = EmotionTracker()
        snap = tracker.analyze("I'm feeling really sad and lonely today")
        assert snap.state == EmotionState.SAD
