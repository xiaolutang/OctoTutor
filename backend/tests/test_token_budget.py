import pytest

from app.agent.token_budget import TokenBudget, estimate_tokens


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_pure_english_abc(self):
        assert estimate_tokens("abc") == 4  # len=3 * 1.5 = 4.5 -> int -> 4

    def test_pure_chinese(self):
        assert estimate_tokens("中文测试") == 6  # len=4 * 1.5 = 6

    def test_mixed_chinese_english(self):
        # "hello你好" len=7, 7 * 1.5 = 10.5 -> int -> 10
        assert estimate_tokens("hello你好") == 10

    def test_long_text(self):
        text = "a" * 1000
        assert estimate_tokens(text) == 1500  # 1000 * 1.5

    def test_single_char(self):
        assert estimate_tokens("x") == 1  # 1 * 1.5 = 1.5 -> int -> 1


class TestTokenBudget:
    def test_context_window_positive(self):
        assert TokenBudget.CONTEXT_WINDOW > 0

    def test_summarize_threshold_range(self):
        assert 0 < TokenBudget.SUMMARIZE_THRESHOLD < 1

    def test_reserved_for_rag_positive(self):
        assert TokenBudget.RESERVED_FOR_RAG > 0

    def test_reserved_for_output_positive(self):
        assert TokenBudget.RESERVED_FOR_OUTPUT > 0

    def test_recent_messages_keep_positive(self):
        assert TokenBudget.RECENT_MESSAGES_KEEP > 0

    def test_threshold_triggers_at_130k(self):
        expected = int(TokenBudget.CONTEXT_WINDOW * TokenBudget.SUMMARIZE_THRESHOLD)
        assert expected == 130_000

    def test_reserved_total_less_than_context_window(self):
        total_reserved = TokenBudget.RESERVED_FOR_RAG + TokenBudget.RESERVED_FOR_OUTPUT
        assert total_reserved < TokenBudget.CONTEXT_WINDOW
