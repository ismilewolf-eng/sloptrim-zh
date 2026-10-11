"""Tests for the Chinese detector. Run: python -m unittest discover tests"""
import json
import os
import socket
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "detect_zh.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import detect_zh as Z  # noqa: E402


def keys(text, lyrics=False):
    return {k for k in Z.scan(text, lyrics=lyrics) if not k.startswith("_")}


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return f.read()


# (key, sentence that must fire, sentence that must stay quiet)
CASES = [
    ("1_ai_vocabulary", "我们将深入探讨这个至关重要的问题。", "我们讨论这个问题。"),
    ("3_promotional", "这家店坐落于老城区，令人叹为观止。", "这家店在老城区。"),
    ("5_simple_yet", "这个设计简单却不失优雅。", "这个设计很简单。"),
    ("10_significance_inflation", "这次发布标志着行业进入新时代。", "这次发布在周三。"),
    ("12_vague_attribution", "专家认为这项政策会有效。", "王教授在报告中说这项政策有效。"),
    ("15_false_range", "从小作坊的诞生到如今的辉煌，公司走过了很长的路。", "从北京到上海要五个小时。"),
    ("16_tail_inflation", "页面支持全文搜索，彰显了团队对创新的追求。", "页面支持全文搜索，方便查找术语。"),
    ("17_negative_parallelism", "这不仅是一个按钮，更是通往效率的入口。", "按钮在右上角。"),
    ("18_not_x_just_y", "没有套路，只有真诚。", "没有备份，只能重做。"),
    ("20_empty_pivot_phrase", "值得注意的是，缓存会过期。", "缓存会过期。"),
    ("21_outcome_speculation", "这件事传开后，引发了人们的深思。", "这件事传开后，他辞职了。"),
    ("24_self_thoroughness", "一文读懂区块链。", "区块链的基本原理。"),
    ("27_compulsive_intro", "你是否也曾觉得时间不够用？", "我常觉得时间不够用。"),
    ("31_signposting", "接下来让我们一起看看具体步骤。", "具体步骤如下。"),
    ("36_challenges_section", "当前行业机遇与挑战并存。", "当前行业缺少熟练工人。"),
    ("38_compulsive_conclusion", "正文。\n总而言之，这个方案可行。", "正文。\n这个方案可行。"),
    ("39_generic_positive_end", "让我们拭目以待，未来可期。", "下周继续测试。"),
    ("47_chatbot_artifacts", "希望这对你有帮助！如果你还有其他问题，欢迎提问。", "这份说明到此结束。"),
    ("48_sycophantic", "这是一个好问题！答案在下面。", "答案在下面。"),
    ("50_cutoff_disclaimer", "截至我的训练数据，这家公司仍在运营。", "这家公司仍在运营。"),
    ("51_copula_avoidance", "西湖被誉为人间天堂。", "西湖是杭州的湖。"),
    ("63_placeholder_zh", "尊敬的【姓名】，您好。", "尊敬的王先生，您好。"),
    ("69_canonical_slop", "我们为城市注入新的活力。", "我们修了三座桥。"),
    ("72_de_stacking", "这是一个十亿参数的开源的小模型的微调的方案。", "这是我的书。"),
    ("73_jinxing_verb", "我们对系统进行全面测试，并对配置进行调整。", "我们测试系统，调整配置。"),
    ("74_bei_stacking", "该问题被社区报告，被认为与内存有关。", "社区报告了这个问题。"),
    ("75_four_char_parallel", "方案稳定可靠、快速响应、易于维护。", "方案很稳定。"),
    ("78_officialese", "我清醒地认识到不足，今后将进一步加强学习。", "我知道自己还有不足，打算多学习。"),
    ("79_overclaim", "本方法是首个解决该问题的工作，性能显著提升。", "本方法在测试集上提高了 3.2 个百分点。"),
    ("76_suizhe_opener", "随着科技的不断发展，人们的生活改变了。", "随着文件增加，检索变慢了。"),
]


class PatternCases(unittest.TestCase):
    def test_each_pattern_fires_and_stays_quiet(self):
        for key, hit, miss in CASES:
            with self.subTest(key=key):
                self.assertIn(key, keys(hit), hit)
                self.assertNotIn(key, keys(miss), miss)


class Scoring(unittest.TestCase):
    def test_ai_fixture_scores_high(self):
        m = Z.scan(fixture("ai_sample.txt"))["_metrics"]
        self.assertEqual(m["language"], "zh")
        self.assertGreaterEqual(m["ai_tell_score"], 41)

    def test_human_fixture_scores_clean(self):
        m = Z.scan(fixture("human_sample.txt"))["_metrics"]
        self.assertLessEqual(m["ai_tell_score"], 20)

    def test_score_in_range_and_band(self):
        m = Z.scan(fixture("ai_sample.txt"))["_metrics"]
        self.assertTrue(0 <= m["ai_tell_score"] <= 100)
        self.assertIn(m["ai_tell_band"], {"clean", "light tells", "mixed", "heavy tells", "pervasive tells"})

    def test_two_decisive_families_floor(self):
        text = "希望这对你有帮助！截至我的训练数据，情况如此。" * 3
        self.assertGreaterEqual(Z.scan(text)["_metrics"]["ai_tell_score"], 65)

    def test_overclaim_is_report_only(self):
        r = Z.scan("本方法是国内首创。")
        self.assertIn("79_overclaim", r)
        self.assertEqual(r["_metrics"]["ai_tell_score"], 0)

    def test_officialese_needs_two_distinct(self):
        self.assertNotIn("78_officialese", keys("我们始终坚持原则。"))

    def test_report_only_does_not_score(self):
        text = "他可能也许会来。" * 2
        r = Z.scan(text)
        self.assertIn("54_hedge_stacking", r)
        self.assertEqual(r["_metrics"]["ai_tell_score"], 0)


class Routing(unittest.TestCase):
    def test_english_goes_upstream(self):
        r = Z.scan("Let's delve into this vibrant tapestry. I hope this helps!")
        self.assertEqual(r["_metrics"]["language"], "en")
        self.assertIn("47_chatbot_artifacts", r)

    def test_chinese_with_some_english_stays_zh(self):
        self.assertEqual(Z.scan("我们用 Python 写了一个 CSV 导出工具。")["_metrics"]["language"], "zh")

    def test_code_is_ignored(self):
        text = "说明如下。\n\n```\n# 值得注意的是 希望这对你有帮助\n```\n"
        self.assertNotIn("47_chatbot_artifacts", keys(text))

    def test_invisible_chars_detected_and_cleaned(self):
        dirty = "文件​已经保存。"
        self.assertIn("62_invisible_chars", keys(dirty))
        out = subprocess.run([sys.executable, SCRIPT, "--clean"], input=dirty,
                             capture_output=True, text=True, encoding="utf-8").stdout
        self.assertEqual(out, "文件已经保存。")


class Lyrics(unittest.TestCase):
    LYRIC = fixture("lyrics_sample.txt") if os.path.exists(os.path.join(HERE, "fixtures", "lyrics_sample.txt")) else ""

    def test_repetition_rules_off_in_lyrics_mode(self):
        r = Z.scan(self.LYRIC, lyrics=True)
        for fam in ("71", "40", "44", "42", "75"):
            self.assertFalse(any(k.startswith(fam + "_") for k in r), fam)
        self.assertEqual(r["_metrics"]["mode"], "lyrics")

    def test_section_tags_ignored(self):
        self.assertNotIn("63_placeholder_text", keys("[Chorus]\n我在门口等你\n", lyrics=True))

    def test_lyric_cliche_cluster(self):
        text = "余生只想陪你走\n人海里再回头\n宿命让我们分手\n"
        self.assertIn("77_lyric_cliche_cluster", keys(text, lyrics=True))
        self.assertNotIn("77_lyric_cliche_cluster", keys("余生只想陪你走\n", lyrics=True))


class CLI(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, SCRIPT, *args], input=stdin,
                              capture_output=True, text=True, encoding="utf-8")

    def test_json_output(self):
        p = self.run_cli(os.path.join(HERE, "fixtures", "ai_sample.txt"))
        self.assertEqual(p.returncode, 0)
        self.assertIn("ai_tell_score", json.loads(p.stdout)["_metrics"])

    def test_empty_input(self):
        self.assertEqual(self.run_cli(stdin="   ").returncode, 1)

    def test_unknown_option(self):
        self.assertEqual(self.run_cli("--bogus").returncode, 2)


class NoNetwork(unittest.TestCase):
    def test_scan_opens_no_socket(self):
        original = socket.socket

        def refuse(*a, **k):
            raise AssertionError("network access attempted")
        socket.socket = refuse
        try:
            Z.scan(fixture("ai_sample.txt"))
            Z.scan("Let's delve into it.")
        finally:
            socket.socket = original


if __name__ == "__main__":
    unittest.main()
