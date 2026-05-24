"""问题意图分类器单元测试"""

from app.domain.classifier import classify_question


class TestUnrelatedIntent:
    """应判定为 unrelated 的输入（不检索教材）"""

    def test_empty_string(self):
        assert classify_question("") == "unrelated"

    def test_whitespace_only(self):
        assert classify_question("   ") == "unrelated"

    def test_short_text(self):
        assert classify_question("好的") == "unrelated"  # len <= 3

    def test_greeting_hi(self):
        assert classify_question("hi") == "unrelated"

    def test_greeting_hello(self):
        assert classify_question("hello") == "unrelated"

    def test_greeting_chinese(self):
        assert classify_question("你好") == "unrelated"

    def test_greeting_with_punctuation(self):
        assert classify_question("你好！") == "unrelated"

    def test_thanks(self):
        assert classify_question("谢谢") == "unrelated"

    def test_ok(self):
        assert classify_question("ok") == "unrelated"

    def test_bye(self):
        assert classify_question("再见") == "unrelated"

    def test_who_are_you(self):
        assert classify_question("你是谁") == "unrelated"

    def test_introduce_yourself(self):
        assert classify_question("介绍一下你自己") == "unrelated"


class TestTextbookIntent:
    """应判定为 textbook 的输入（需要检索教材）"""

    def test_math_keyword_function(self):
        assert classify_question("什么是函数？") == "textbook"

    def test_math_keyword_equation(self):
        assert classify_question("解方程 x+1=0") == "textbook"

    def test_math_keyword_calculus(self):
        assert classify_question("导数怎么求") == "textbook"

    def test_math_keyword_probability(self):
        assert classify_question("概率的定义是什么") == "textbook"

    def test_math_keyword_proof(self):
        assert classify_question("证明这个定理") == "textbook"

    def test_math_keyword_formula(self):
        assert classify_question("求最大值") == "textbook"

    def test_latex_inline(self):
        assert classify_question("已知 $f(x) = x^2$") == "textbook"

    def test_arithmetic_expression(self):
        assert classify_question("3 + 5 = ?") == "textbook"

    def test_greek_letter(self):
        assert classify_question("α 的取值范围") == "textbook"

    def test_math_symbol_pi(self):
        assert classify_question("π 是多少") == "textbook"

    def test_math_symbol_integral(self):
        assert classify_question("∫ 的计算方法") == "textbook"

    def test_math_symbol_inequality(self):
        assert classify_question("解不等式 x≥0") == "textbook"

    def test_default_fallback(self):
        """不匹配任何模式的中长文本默认走检索"""
        assert classify_question("帮我看看这道题") == "textbook"


class TestEdgeCases:
    """边界情况"""

    def test_exactly_4_chars(self):
        """4 字不匹配问候模式，默认走检索"""
        assert classify_question("帮我看看") == "textbook"

    def test_mixed_case_greeting(self):
        assert classify_question("HI") == "unrelated"

    def test_greeting_with_spaces(self):
        assert classify_question("  你好  ") == "unrelated"

    def test_greeting_with_question_mark(self):
        assert classify_question("你好？") == "unrelated"

    def test_math_keyword_in_longer_text(self):
        assert classify_question("老师，请问函数的定义是什么？") == "textbook"

    def test_non_math_long_text(self):
        """非数学但较长，默认走检索"""
        assert classify_question("今天天气怎么样") == "textbook"
