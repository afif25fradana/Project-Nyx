"""Unit tests for Two-Stage Adaptive StreamParser, 510-Phoneme Guard & Emotion Extractor."""

import pytest
from backend.app.core.stream_parser import ClauseChunk, StreamParser


class TestStreamParser:
    def test_clause_1_fast_emission_on_punctuation(self):
        """Stage 1: Initial clause emits at 40-60 characters upon punctuation."""
        parser = StreamParser()
        # Feed 35 chars without punctuation
        chunks = parser.feed_token("This is a test sentence that is now")
        assert chunks == []

        # Feed token that crosses 40 chars and includes a comma
        chunks = parser.feed_token(" reached forty chars, and it continues.")
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.text == "This is a test sentence that is now reached forty chars,"
        assert 40 <= len(chunk.text) <= 65
        assert not chunk.is_final

    def test_clause_1_waits_for_40_chars_before_punctuation_split(self):
        """Stage 1: Punctuation under 40 chars does not trigger immediate split."""
        parser = StreamParser()
        # Sentence under 40 chars
        chunks = parser.feed_token("Hello, friend! ")
        assert chunks == []

        # Cross 40 chars and end with punctuation
        chunks = parser.feed_token("How are you doing on this fine day?")
        assert len(chunks) == 1
        assert "Hello, friend! How are you doing on this fine day?" in chunks[0].text

    def test_stage_2_sentence_delimiter_chunking(self):
        """Stage 2: Subsequent clauses split on sentence delimiters (.!?\n), not commas."""
        parser = StreamParser()
        # Emit stage 1 chunk ending with period
        c1 = parser.feed_token("First clause that has reached over forty characters in length.")
        assert len(c1) == 1

        # Feed stage 2 text with a comma - should NOT split on comma
        c2 = parser.feed_token(" In the second stage, commas do not split,")
        assert c2 == []

        # Feed sentence-ending period - should split
        c3 = parser.feed_token(" but periods definitely do.")
        assert len(c3) == 1
        assert c3[0].text == "In the second stage, commas do not split, but periods definitely do."

    def test_secondary_hard_cap_splits_run_on_text(self):
        """Invariant #5 / ADR-0006: Run-on text without punctuation splits on whitespace before 300 chars."""
        parser = StreamParser()
        # Generate 320 chars of unpunctuated text with words of length 5
        words = ["word" + str(i % 10) for i in range(65)]
        long_run_on = " ".join(words)
        assert len(long_run_on) > 300

        chunks = parser.feed_token(long_run_on)
        assert len(chunks) >= 1
        first_chunk = chunks[0]
        assert len(first_chunk.text) <= 300
        assert len(first_chunk.text) >= 250
        # Verify split occurred at a clean word boundary (no broken word)
        assert not first_chunk.text.endswith(" ")
        assert not parser._buffer.startswith(" ")

    def test_hard_cap_splits_even_without_whitespace(self):
        """Invariant #5: Even continuous non-whitespace text splits at or before 300 chars."""
        parser = StreamParser()
        solid_string = "a" * 320
        chunks = parser.feed_token(solid_string)
        assert len(chunks) == 1
        assert len(chunks[0].text) <= 300

    def test_prefix_emotion_extraction(self):
        """Prefix <emotion> tag is extracted, stripped from TTS text, and sets chunk emotion."""
        parser = StreamParser()
        # 45 characters of text after emotion tag to trigger Stage 1 split
        chunks = parser.feed_token(
            "<emotion>happy</emotion> Hello world! I am so happy to assist you today."
        )
        assert len(chunks) >= 1
        assert chunks[0].emotion == "happy"
        assert "<emotion>" not in chunks[0].text
        assert "</emotion>" not in chunks[0].text
        assert "Hello world! I am so happy to assist you today." in chunks[0].text

    def test_prefix_emotion_short_turn_with_finalize(self):
        """Short turn with prefix emotion (<emotion>happy</emotion> Hello!) flushes correctly on finalize()."""
        parser = StreamParser()
        chunks = parser.feed_token("<emotion>happy</emotion> Hello!")
        assert chunks == []
        flushed = parser.finalize()
        assert len(flushed) == 1
        assert flushed[0].emotion == "happy"
        assert flushed[0].text == "Hello!"
        assert flushed[0].is_final is True

    def test_prefix_emotion_split_across_tokens(self):
        """Emotion tag arriving in fragmented streaming tokens is cleanly extracted."""
        parser = StreamParser()
        assert parser.feed_token("<emo") == []
        assert parser.feed_token("tion>sur") == []
        assert parser.feed_token("prised</emotion> ") == []
        chunks = parser.feed_token("Look at that incredible view right there, isn't it great?")
        all_chunks = chunks + parser.finalize()
        assert len(all_chunks) >= 1
        assert all_chunks[0].emotion == "surprised"
        assert "<emotion>" not in all_chunks[0].text

    def test_reasoning_block_suppression(self):
        """<think>...</think> reasoning blocks are completely suppressed from audio chunks."""
        parser = StreamParser()
        raw = "<think>Let me ponder this question deeply.\nCalculating answer...</think> The answer is 42."
        chunks = parser.feed_token(raw)
        chunks += parser.finalize()
        assert len(chunks) >= 1
        full_text = " ".join(c.text for c in chunks)
        assert "ponder" not in full_text
        assert "Calculating" not in full_text
        assert "<think>" not in full_text
        assert "The answer is 42." in full_text

    def test_reasoning_block_streaming_across_tokens(self):
        """Thinking block streamed token by token produces zero audio chunks until closed."""
        parser = StreamParser()
        assert parser.feed_token("<think>") == []
        assert parser.feed_token("reasoning step 1. ") == []
        assert parser.feed_token("reasoning step 2.\n") == []
        assert parser.feed_token("</think>") == []
        chunks = parser.feed_token("Ready to respond!")
        chunks += parser.finalize()
        assert len(chunks) == 1
        assert chunks[0].text == "Ready to respond!"
        assert "reasoning" not in chunks[0].text

    def test_markdown_and_formatting_stripping(self):
        """Markdown code fences, inline backticks, bold symbols, bullets, and emojis are stripped."""
        parser = StreamParser()
        raw = (
            "Here is the plan:\n"
            "- **Step 1**: Run the `pytest` suite.\n"
            "```python\ndef test(): pass\n```\n"
            "All tests pass! 🎉"
        )
        chunks = parser.feed_token(raw)
        chunks += parser.finalize()
        combined = " ".join(c.text for c in chunks)

        assert "```" not in combined
        assert "def test():" not in combined
        assert "`" not in combined
        assert "**" not in combined
        assert "🎉" not in combined
        assert "Step 1: Run the suite." in combined or "Step 1: Run the pytest suite." in combined
        assert "All tests pass!" in combined

    def test_finalize_flushes_remaining_buffer(self):
        """finalize() flushes any remaining buffered text with is_final=True."""
        parser = StreamParser()
        # Feed text that does not meet the 40 char Stage 1 threshold
        chunks = parser.feed_token("Short turn.")
        assert chunks == []

        flushed = parser.finalize()
        assert len(flushed) == 1
        assert flushed[0].text == "Short turn."
        assert flushed[0].is_final is True

        # Second finalize on empty buffer returns empty list
        assert parser.finalize() == []

    @pytest.mark.asyncio
    async def test_async_parse_stream(self):
        """parse_stream wraps an async token generator into an async ClauseChunk stream."""
        parser = StreamParser()

        async def token_gen():
            tokens = [
                "<emotion>thinking</emotion> ",
                "<think>calculating</think>",
                "Let us begin our deep exploration ",
                "of this complex topic, ",
                "which will take several minutes. ",
                "Are you ready to proceed",
            ]
            for t in tokens:
                yield t

        received_chunks: list[ClauseChunk] = []
        async for chunk in parser.parse_stream(token_gen()):
            received_chunks.append(chunk)

        assert len(received_chunks) >= 2
        assert received_chunks[0].emotion == "thinking"
        assert "calculating" not in " ".join(c.text for c in received_chunks)
        assert received_chunks[-1].is_final is True
        assert received_chunks[-1].text == "Are you ready to proceed"

    def test_unclosed_think_block_with_preceding_text_does_not_leak(self):
        """Unclosed <think> appearing after short text (think_pos > 0) does not leak thoughts."""
        parser = StreamParser()
        # Feed text where think_pos > 0 and think block is unclosed
        chunks = parser.feed_token("Wait a moment. <think>secret internal reasoning that must not leak")
        # Ensure nothing from the think block leaked into emitted chunks
        emitted_text = " ".join(c.text for c in chunks)
        assert "secret internal reasoning" not in emitted_text
        assert "<think>" not in emitted_text

    def test_decimal_number_and_abbreviation_not_split(self):
        """Decimal numbers like 3.14 and abbreviations like Dr. Smith do not trigger sentence split."""
        parser = StreamParser()
        # Feed sentence with 3.14 and Dr. Smith
        # Stage 1: Initial clause requires 40 chars
        chunks = parser.feed_token("The current ratio is approximately 3.14159 according to Dr. Smith, who verified it.")
        assert len(chunks) == 1
        # The split should happen at the comma or period after 'verified it.', not at '3.' or 'Dr.'
        assert "3.14159" in chunks[0].text
        assert "Dr. Smith" in chunks[0].text
        assert not chunks[0].text.endswith("3.")
        assert not chunks[0].text.endswith("Dr.")

    def test_emotion_with_leading_whitespace(self):
        """Emotion tag with leading whitespace is properly extracted without tag leaking."""
        parser = StreamParser()
        chunks = parser.feed_token("   <emotion>happy</emotion> Hello world! It is a great pleasure to meet you today.")
        assert len(chunks) >= 1
        assert chunks[0].emotion == "happy"
        assert "<emotion>" not in chunks[0].text
        assert "Hello world!" in chunks[0].text

    def test_unpermitted_emotion_falls_back_to_neutral(self):
        """Emotion outside permitted_emotions falls back to default_emotion ('neutral')."""
        parser = StreamParser(permitted_emotions={"neutral", "happy", "sad", "surprised", "thinking"})
        chunks = parser.feed_token("<emotion>unregistered_rage</emotion> Hello world! It is a great pleasure to meet you today.")
        assert len(chunks) >= 1
        assert chunks[0].emotion == "neutral"
        assert "<emotion>" not in chunks[0].text
        assert "unregistered_rage" not in chunks[0].text

