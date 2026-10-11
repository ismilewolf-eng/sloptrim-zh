#!/usr/bin/env python3
"""sloptrim-zh: Chinese AI-writing pattern detector.

Modified from sloptrim (https://github.com/seyedehsanhadi/sloptrim, Apache-2.0).
The upstream detector `detect.py` ships unchanged beside this file. This module
reuses its file reading, code stripping, character layer and confidence logic,
and adds a Chinese pattern layer whose catalogue follows Humanizer-zh
(https://github.com/op7418/Humanizer-zh, MIT). Text that is not mainly Chinese
is handed to the upstream English scan.

Standard library only. No network, no model. A score describes the writing in
front of it; it is not evidence of who or what wrote it. See ETHICS.md.
"""
from __future__ import annotations

import collections
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect as D  # noqa: E402  upstream sloptrim detector, unmodified

VERSION = "0.3.0"
MAX_SAMPLES = 3
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
ZH_RATIO = 0.3  # share of Han among Han + Latin letters that routes to the Chinese scan

# ---------------------------------------------------------------- lexical (1-9)
AI_VOCAB = (
    r"赋能|深耕|助力|抓手|底层逻辑|顶层设计|颗粒度|无缝|至关重要|不可或缺|举足轻重|"
    r"深入探讨|深度剖析|深度解析|旨在|彰显|凸显|焕发|重塑|引领|交织|编织|画卷|篇章|"
    r"征程|基石|灯塔|里程碑|多维度|全方位|深度融合|日新月异|蓬勃发展|不断涌现|"
    r"精心打造|匠心|细致入微|独特魅力|丰富多彩|璀璨|瑰宝|宝贵财富|注入.{0,4}活力|"
    r"有力支撑|重要组成部分|不容忽视|值得深思|息息相关|密不可分|相辅相成|"
    r"潜移默化|源源不断|生生不息|熠熠生辉|淋漓尽致|当之无愧|诠释|蕴含着|迎难而上|攻坚克难|"
    r"拼搏进取|敢为人先|丰硕的?成果|辛勤付出|默默奉献|脱颖而出|完美(?:融合|交融|结合)|"
    r"保驾护航|集[^，。！？\n]{2,10}于一体|不一样的(?:感受|体验)"
)
MODEL_DIALECT = (
    r"划重点|敲黑板|一句话总结|干货满满|建议收藏|小白也能|保姆级|手把手|"
    r"天花板级?|绝绝子|宝子们|家人们|姐妹们|冲鸭|狠狠(?:爱了|心动)|闭眼入|"
    r"宝藏(?:小店|咖啡店|店铺|地方|好物)|美哭了?|绝了|随手一拍都是大片|私藏清单|"
    r"谁懂啊|救命[！!]|按头安利|无限回购"
)
PROMO = (
    r"坐落于|令人叹为观止|美不胜收|打卡圣地|独具匠心|得天独厚|人杰地灵|"
    r"底蕴深厚|世界一流|行业领先|业内领先|首屈一指|无与伦比|匠心独运|堪称.{0,8}(?:典范|天堂|传奇|奇迹)|"
    r"梦想天堂|人间仙境|性价比之王|不容错过|一定不要错过"
)
SIMPLE_YET = (
    r"(?:简单|朴素|平凡|低调|简约)(?:却|而又?|但(?:又|却)?|中(?:透着|蕴含着?))(?:不失)?"
    r"(?:高效|有力|深刻|优雅|精致|强大|动人|温暖|伟大|奢华|高级)"
    r"|看似[^，。！？\n]{1,8}[，,]\s*(?:实则|实际上却)"
)
FICTION_NAMES = r"林晚|苏晚|沈清|顾言|陆沉|江辞|许念|温言|林深|宋知意|陈默|顾北|沈知|苏念"

# ------------------------------------------------------- rhetorical (10-26)
SIGNIFICANCE_INFLATION = (
    r"标志着.{0,12}(?:新时代|新纪元|新篇章|新阶段|里程碑|转折点)|开启了.{0,10}新篇章|"
    r"具有(?:重要|深远|里程碑式?的?|划时代的?)(?:的)?(?:意义|影响)|"
    r"扮演着?.{0,6}(?:重要|关键|核心|举足轻重的?)(?:的)?角色|"
    r"发挥着?.{0,6}(?:重要|关键|不可替代)的?作用|留下了?不可磨灭|"
    r"成为.{0,10}(?:的)?(?:象征|缩影|代名词|标杆|典范)"
)
NOTABILITY = (
    r"(?:被|获得?|受到|登上)[^。！？\n]{0,6}(?:央视|人民日报|新华社|纽约时报|BBC|CNN|福布斯|《[^》]{1,12}》)"
    r"[^。！？\n]{0,40}(?:、|和|及)[^。！？\n]{0,40}(?:报道|关注|转载|专访|推荐)"
    r"|全网.{0,4}(?:粉丝|播放|曝光)(?:量)?(?:超过?|突破|逾)"
    r"|拥有.{0,6}(?:万|百万|千万)粉丝"
)
VAGUE_ATTR = (
    r"专家(?:们)?(?:认为|指出|表示|称)|业内人士(?:认为|指出|表示|透露)|"
    r"有(?:观点|分析|评论)认为|普遍认为|众所周知|不少人认为|多方人士|有研究表明|研究表明"
)
FALSE_RANGE = (
    r"从[^，。！？\n]{1,10}(?:的)?(?:诞生|起源|萌芽|兴起|初创|起步|蹒跚学步)"
    r"到[^，。！？\n]{1,12}(?:的)?(?:今天|如今|现在|辉煌|繁荣|腾飞|壮大)"
)
ING_TAIL = r"[，,]\s*(?:充分)?(?:彰显|体现|凸显|展现|反映|象征|折射|昭示|诠释|印证|见证)(?:了|出|着)"
NEG_PARALLEL = (
    r"不(?:仅仅?|只)是[^。！？\n]{1,30}?[，,]?\s*(?:更|还|而)是"
    r"|这不是[^。！？\n]{1,20}[，,]\s*(?:而|这)是"
    r"|与其说[^。！？\n]{1,20}不如说"
    r"|不是[^，。！？\n]{1,10}[，,]\s*(?:也)?不是[^，。！？\n]{1,10}[，,]\s*而是"
)
NOT_X_JUST_Y = (
    r"(?:没有|不需要|无需|不用)[^，。！？\n]{1,8}[，,]\s*(?:只有|只需要?|只要)[^，。！？\n]{1,10}"
    r"|[，,]\s*(?:不废话|不绕弯子|零门槛|不踩坑|没有套路)"
)
FILLER = r"从某种(?:程度|意义)上(?:来说|讲)?|在一定程度上|在这个过程中|在此基础上|具有.{0,4}的能力"
EMPTY_PIVOT = (
    r"值得(?:注意|一提|关注|强调|指出)的是|需要(?:注意|指出|强调|说明)的是|"
    r"不可否认的是|有趣的是|一个关键(?:点|考量)是"
)
OUTCOME_SPECULATION = (
    r"[，,]\s*(?:引发了?|引起了?)(?:人们|大众|社会|广泛)?的?(?:思考|深思|讨论|反思)"
    r"|[，,]\s*为[^。！？\n]{2,20}(?:铺平了道路|奠定了(?:坚实的?)?基础|提供了(?:新的)?(?:思路|可能|借鉴|启示))"
    r"|[，,]\s*(?:值得|令人)深思"
)
AUTHORITY_TROPE = (
    r"说白了|说到底|归根结底|本质上(?:来说|讲)?[，,]|事实上[，,]|真正(?:重要|关键)的是|"
    r"问题的(?:关键|核心|本质)在于|核心在于|不得不说|毋庸置疑"
)
EDITORIAL_INTERJECTION = (
    r"需要(?:记住|明白|理解|认识到)的是|我们必须(?:认识到|意识到|明白)|"
    r"必须强调的是|怎么强调都不为过"
)
SELF_THOROUGHNESS = (
    r"本文将(?:全面|深入|系统|详细)|这篇(?:全面|深度|超详细|保姆级)|一文(?:读懂|看懂|搞懂|说清)|"
    r"你需要知道的(?:一切|全部)|最全(?:攻略|指南)|全方位(?:解析|解读)"
)
QA_RHETORICAL = (
    r"为什么[^？?\n]{0,20}[？?]\s*因为"
    r"|[^。！？\n]{2,30}[？?]\s*(?:答案是|当然(?:不|是)|没错)[，,。！!]"
)
CONCRETE_EVIDENCE = r"有(?:确凿|充分|实实在在)的(?:证据|数据)(?:表明|显示|证明)|数据(?:不会说谎|说明一切)|用事实说话"

# ------------------------------------------------- structure / discourse (27-39)
COMPULSIVE_INTRO = (
    r"(?:^|\n)\s*(?:你是否(?:曾经)?|你有没有(?:想过|遇到过)|想象一下|"
    r"在当今(?:这个)?|在这个(?:信息爆炸|快节奏|瞬息万变|日新月异))"
)
DIFF_ANCHORED = (
    r"与(?:之前|以前|旧|上一)(?:的)?(?:版本?|方案)相比|"
    r"(?:这次|本次|新)(?:的)?(?:更新|版本|改版)(?:新增|带来|引入|加入)了?|"
    r"(?:已经|现已)(?:被)?(?:更新|重构|优化|升级)为"
)
SIGNPOSTING = (
    r"让我们(?:一起)?(?:深入|来)?(?:看看|探讨|了解|聊聊|探索|走进)|"
    r"接下来(?:让我们|我们来|我将)|下面(?:我们)?(?:来|将)(?:详细)?(?:介绍|看看|说说|分析)|"
    r"以下是你需要知道的|话不多说|废话不多说|事不宜迟|准备好了吗"
)
CATALOG_LEADIN = r"(?:采用|使用|运用|借助)了?(?:多种|各种|一系列|诸多)[\u4e00-\u9fff]{1,6}"
FAUX_INSIGHT = (
    r"很多人不知道的是|大多数人都?(?:忽略|不知道|搞错)了|没人告诉你|鲜为人知的(?:是|秘密)|"
    r"(?:残酷|扎心)的(?:真相|事实)是|说出来你可能不信"
)
DEFINITIONAL_METAPHOR = r"是[^，。！？\n]{1,10}的(?:语言|货币|灵魂|血液|基因|DNA|脊梁|基石|引擎|心脏|底色)"
COLON_REVEAL = r"(?m)^[ \t]*(?:关键是|重点来了|划重点|真相是|结果是|答案是|最妙的是|问题在于)[：:]"
CHALLENGES = (
    r"尽管面临(?:诸多|种种|一些|重重)?(?:挑战|困难|困境)|挑战与(?:机遇|展望|未来)|"
    r"机遇与挑战并存|仍(?:然)?面临(?:诸多|不少|一系列)(?:挑战|问题)"
)
COMPULSIVE_CONCLUSION = r"(?:^|\n)[ \t]*(?:总而言之|总之|综上所述|总的来说|总结一下|一言以蔽之)[，,：:]"
GENERIC_END = (
    r"未来可期|前景(?:十分|非常)?(?:广阔|光明)|让我们(?:一起)?拭目以待|让我们(?:携手|共同)|"
    r"期待更多(?:可能|精彩)|(?:迎接|创造)(?:更加?)?美好的?未来|必将(?:迎来|开创|书写)|"
    r"再创辉煌|扬帆起航|砥砺前行|未来已来|(?:创造|迎接|开创)(?:更加)?(?:辉煌|美好)的?(?:明天|未来)|"
    r"贡献(?:自己的)?(?:一份)?(?:力量|智慧)|以更加饱满的热情|实现新的突破|让我们一起(?:成为|努力|加油)|"
    r"带来更多(?:惊喜|可能)|迈出了(?:重要|坚实|关键)的?一步"
)

# ------------------------------------------------- register and voice (47-55)
CHATBOT = (
    r"希望(?:这|以上|本文)?(?:些)?(?:内容)?(?:对你|对您|能)(?:有所|有)?帮助|"
    r"如果(?:你|您)?(?:还)?有(?:任何|其他)(?:问题|疑问|需要)|随时(?:告诉我|联系我|提问)|"
    r"需要我(?:帮你|为你|再)|以下是(?:为你|为您|一份|一篇|几个|一些)|"
    r"(?:^|\n)\s*当然[！!]|(?:^|\n)\s*好的[，,！!]\s*(?:以下|下面|我来)|"
    r"作为一个?(?:AI|人工智能|语言模型|AI助手)|我是一个?(?:AI|人工智能)"
)
CHAT_RESIDUE = r"针对你的问题|关于你提到的|根据你的要求|按照你的要求|这是(?:修改|改写|优化)后的(?:版本|内容)"
CUTOFF = (
    r"截至我的(?:训练|知识)|根据我的(?:训练数据|知识库)|由于(?:可用|公开)?(?:信息|资料)有限|"
    r"目前(?:公开)?资料(?:较少|有限|不多)|我无法(?:获取|访问)(?:实时|最新)"
)
PRIVACY_FILLER = r"一向(?:为人)?低调|鲜少(?:公开)?(?:透露|谈及)(?:其|自己的)?私|个人生活(?:鲜为人知|十分低调)"
SYCOPHANTIC = r"(?:这是一个|非常好的|很棒的|好)问题[！!]|你说得(?:太|非常|完全)?对[！!]|问得好[！!，,]"
COPULA_AVOID = (
    r"充当着?|扮演着|被誉为|素有[^，。！？\n]{1,12}之称|享有[^，。！？\n]{1,10}的美誉|坐拥|拥有着"
    r"|作为[^，。！？\n]{1,15}[，,][^。！？\n]{0,10}(?:设有|拥有|具备)"
)
HEDGES = r"可能|也许|或许|大概|似乎|好像|或多或少|在一定程度上|某种程度上|一般来说|往往"
TRANSITIONS = (
    "此外", "另外", "与此同时", "然而", "因此", "而且", "并且", "首先", "其次",
    "再次", "总之", "不仅如此", "更重要的是", "换句话说", "也就是说", "除此之外",
)

# ---------------------------------------------- machine artefacts (63-69)
PLACEHOLDER_ZH = (
    r"\[(?:姓名|名字|公司名称?|日期|地址|你的名字|插入[^\]]{0,10})\]|"
    r"【(?:姓名|公司|日期|地址|此处[^】]{0,10})】|XXX公司|xxx公司"
)
CANONICAL_SLOP = (
    r"解锁(?:你的|无限|全新)|开启(?:你的|全新|新的)[^，。！？\n]{0,6}(?:之旅|旅程|篇章)|"
    r"在这个(?:瞬息万变|快节奏|信息爆炸)的(?:时代|世界)|一站式(?:解决方案|服务)|"
    r"打造(?:全新|极致|沉浸式)|让[^，。！？\n]{1,10}触手可及|赋能千行百业|"
    r"助力[^，。！？\n]{1,10}高质量发展|引领[^，。！？\n]{1,8}新潮流|"
    r"为[^，。！？\n]{1,12}注入新的?(?:活力|动能)|告别[^，。！？\n]{0,4}焦虑|开启[^，。！？\n]{0,8}新篇章"
)

# ------------------------------------------- Chinese-specific additions (72-76)
JINXING = (
    r"(?:进行|开展|加以|予以)了?(?:全面|深入|有效|系统|认真|进一步)?的?"
    r"(?:测试|分析|研究|讨论|调整|优化|改进|处理|检查|评估|说明|介绍|探讨|部署|配置|"
    r"修改|更新|升级|整改|宣传|培训|沟通|交流|总结|梳理|排查)"
)
SUIZHE = (
    r"(?:^|\n|[。！？]\s*)(?:随着|伴随着)[^，。！？\n]{2,24}的(?:不断|快速|飞速|日益|蓬勃|迅猛|持续)?"
    r"(?:发展|进步|普及|深入|推进|到来|兴起)"
    r"|在[^，。！？\n]{2,16}(?:的时代|时代背景|大背景)下[，,]"
)
FOUR_CHAR_RUN = re.compile(
    r"[\u4e00-\u9fff]{4}(?:、[\u4e00-\u9fff]{4}){2,}(?=[，。！？；\n,]|$)", re.M)
# 7: same-head triads such as 一直在问、一直在走、一直在看. Soft: deliberate
# parallelism exists, but in plain narrative it reads as composed.
TRIAD = re.compile(r"([\u4e00-\u9fff]{2,3})[\u4e00-\u9fff]{1,3}[、，,]\1[\u4e00-\u9fff]{1,3}[、，,]\1[\u4e00-\u9fff]{1,3}")
HALF_PUNCT = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}
HALF_BETWEEN_HAN = re.compile(r"(?<=[\u4e00-\u9fff])[,;:?!](?=[\u4e00-\u9fff])")
BEI = re.compile(r"被(?![子窝褥单套])")
ZH_EM_DASH = re.compile(r"——|—")
ZH_MIXED_PUNCT = r"(?<=[\u4e00-\u9fff])[,;:?!](?=[\u4e00-\u9fff])|\"[\u4e00-\u9fff][^\"\n]{0,30}\""

# 78: officialese of work reports and speeches. People write it too, so it is
# soft-weighted and needs two distinct phrases before it reports.
OFFICIALESE = (
    r"清醒地认识到|进一步加强|不断提升自身的?|以[^，。！？\n]{1,8}为中心的理念|始终坚持|"
    r"较好地完成了?|在[^，。！？\n]{1,10}的(?:关心|支持|指导)和[^，。！？\n]{1,10}的(?:帮助|配合)下|"
    r"现将[^，。！？\n]{1,10}(?:总结|汇报|报告)如下|有待进一步(?:提高|加强|完善)|更加务实的作风|"
    r"圆满完成|心往一处想|劲往一处使|综合素质和业务能力|取得了?(?:一定|显著)的?成绩"
)
# 79: claim strength words. Not a style defect: a calibration flag. Report only,
# never deleted silently; the skill asks for evidence or softens with consent.
OVERCLAIM = (
    r"首次|首个|唯一|最优|遥遥领先|颠覆性|革命性|碾压|全面超越|填补了?[^，。！？\n]{0,6}空白|"
    r"国际领先|国内首创|显著(?:提升|优于|提高)|彻底解决|完美(?:解决|实现)"
)

# 82: Chinese numerals for clock times, durations and prices in narrative.
# Style preference, not an AI tell: report only, and --zh-digits rewrites them.
# Idioms (一五一十, 三三两两) and "一点" meaning "a little" are left alone.
ZH_NUM = "[零一二两三四五六七八九十百]"
TIME_WORD = r"(?:早上|上午|中午|下午|晚上|凌晨|傍晚|快|到|约|大概|差不多|才|都|已经|是)"
ZH_DIGIT_RE = re.compile(
    # Clock time: needs a time word before it, or 钟/半/多/左右 after it, so
    # "好一点了" (a little better) is never read as one o'clock.
    rf"(?P<tw>{TIME_WORD})(?P<a>{ZH_NUM}{{1,3}})(?=点)"
    rf"|(?<!{ZH_NUM})(?P<b>{ZH_NUM}{{1,3}})(?=点(?:钟|半|多|左右))"
    # Durations and prices.
    rf"|(?<!{ZH_NUM})(?P<c>{ZH_NUM}{{1,4}})(?=(?:个)?多?(?:分钟|小时)|块钱?|元)"
    # Clock time opening a sentence or clause: 九点到的、十点出发。
    rf"|(?:^|(?<=[。！？，,\n们我他她]))(?P<d>{ZH_NUM}{{1,3}})(?=点(?:到|的|了|出发|开始|起))", re.M)
# 83: sentence that opens on a bare verb or time, with no subject. Report only:
# the fix needs reading, and many such sentences are fine in context.
SUBJECT_DROP = re.compile(
    rf"(?:^|(?<=[。！？\n]))\s*(?:(?:早上|上午|中午|下午|晚上|今天|昨天|然后|后来|接着|[0-9]{{1,2}}点|{ZH_NUM}{{1,3}}点)[，,]?)?"
    r"(?:(?:在|从)[^，。！？\n]{1,6})?(?:先|又|就|再)?"
    r"(?:(?:去|到|吃|看|排|坐|买|进)(?:了|的)|带[^，。！？\n]{1,4}去(?:了|的))", re.M)


# 84: a state left hanging before a comma, e.g. "在我背上快睡着，嘴里还嘟囔了一句".
# It needs 了 or 时 ("快睡着了" / "快睡着时"). Report only.
UNFINISHED_STATE = re.compile(r"快(?:要)?[一-鿿]{1,2}着(?=[，,])")


def zh_numeral_value(s: str):
    """Value of a Chinese numeral up to 999; None if it is not a plain number."""
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    total, cur = 0, 0
    for ch in s:
        if ch in digits:
            cur = digits[ch]
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
        else:
            return None
    return total + cur


def zh_digits(text: str) -> str:
    """Rewrite clock times, durations and prices to Arabic digits (sense-preserving)."""
    def sub(m):
        num = m.group("a") or m.group("b") or m.group("c") or m.group("d")
        v = zh_numeral_value(num)
        return (m.group("tw") or "") + (str(v) if v is not None else num)
    return ZH_DIGIT_RE.sub(sub, text)


# 77, lyrics mode only: abstract imagery that fills Chinese AI lyrics without
# moving the story. One or two are ordinary; three or more distinct is a cluster.
LYRIC_CLICHE = r"余生|人海|宿命|轮回|星河|尘埃|彼岸|山海|灵魂|岁月|时光|流年|红尘|心碎|回忆|远方|风雨|天涯"

# Upstream keeps U+200B beside CJK because Thai, Khmer and kana use it as a
# line-break hint. Chinese prose breaks between any two Han characters without
# it, so in a Chinese document a ZWSP next to Han does no work and is usually a
# copy-paste or web-scrape artefact. Kana context is left to upstream.
ZH_ZW = re.compile(r"(?<=[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff，。、！？；：])[\u200b\u2060]+"
                   r"|[\u200b\u2060]+(?=[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff，。、！？；：])")
KANA = re.compile(r"[\u3040-\u30ff]")


def zh_zero_width(text: str) -> list[str]:
    if KANA.search(text):
        return []
    return ZH_ZW.findall(text)


def clean_zh(text: str, syntax: str = "markdown") -> str:
    """Upstream clean, then, in a Chinese document, drop ZWSP/WJ beside Han and turn
    half-width , ; : ? ! between two Han characters into full-width."""
    cleaned = D.clean_text(text, syntax=syntax)
    if is_chinese(cleaned) and not KANA.search(cleaned):
        mapper = D._map_latex if syntax == "latex" else D._map_code
        # Protect code spans: only touch prose.
        protected: list[str] = []

        def keep(span: str) -> str:
            protected.append(span)
            return "\x00%d\x00" % (len(protected) - 1)
        masked = mapper(cleaned, keep)
        masked = ZH_ZW.sub("", masked)
        masked = HALF_BETWEEN_HAN.sub(lambda m: HALF_PUNCT[m.group(0)], masked)
        # Paired straight double quotes around Chinese text become “ ”.
        masked = re.sub(r'"([^"\n]*[一-鿿][^"\n]*)"', "“\\1”", masked)
        cleaned = re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m.group(1))], masked)
    return cleaned


SECTION_TAG = re.compile(r"^\s*\[[^\]\n]{1,30}\]\s*$", re.M)


# ------------------------------------------------------------------- helpers
def han_count(text: str) -> int:
    return len(HAN.findall(text))


def is_chinese(text: str) -> bool:
    han = han_count(text)
    latin = sum(len(w) for w in LATIN_WORD.findall(text))
    return han > 0 and han / float(han + latin) >= ZH_RATIO


def units(text: str) -> int:
    """Word-equivalents: about 1.5 Han characters per English word."""
    return int(round(han_count(text) / 1.5)) + len(LATIN_WORD.findall(text))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?…])|\n+", text)
    return [p.strip() for p in parts if p and han_count(p) > 0]


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _find(text: str, pattern: str) -> list[str]:
    return [m.group(0).strip() for m in re.finditer(pattern, text, re.M)]


def _hit(result: dict, key: str, label: str, found: list[str]) -> None:
    if found:
        result[key] = {"label": label, "count": len(found),
                       "samples": list(dict.fromkeys(found))[:MAX_SAMPLES]}


def detect_de_stacking(text: str) -> list[str]:
    """72: four or more 的 inside one clause."""
    hits = []
    for clause in re.split(r"[，。！？；：、,.!?;:\n]", text):
        if clause.count("的") >= 4 and han_count(clause) <= 60:
            hits.append(clause.strip()[:60])
    return hits


def detect_bei_stacking(text: str) -> list[str]:
    """74: two or more 被 in one sentence."""
    return [s[:60] for s in split_sentences(text) if len(BEI.findall(s)) >= 2]


def detect_hedge_stacking(text: str) -> list[str]:
    return [s[:60] for s in split_sentences(text) if len(re.findall(HEDGES, s)) >= 2]


def detect_transition_clusters(text: str) -> list[str]:
    hits = []
    for i, p in enumerate(split_paragraphs(text), 1):
        used = [t for t in TRANSITIONS if t in p]
        if len(used) >= 3:
            hits.append("第%d段: %s" % (i, "、".join(used)))
    return hits


def detect_opener_repetition(text: str) -> list[str]:
    hits = []
    for i, p in enumerate(split_paragraphs(text), 1):
        sents = split_sentences(p)
        if len(sents) < 3:
            continue
        heads = collections.Counter(s[:2] for s in sents if han_count(s[:2]) == 2)
        for head, n in heads.items():
            if n >= 3:
                hits.append("第%d段: “%s”×%d" % (i, head, n))
    return hits


def detect_paragraph_openers(text: str) -> list[str]:
    """85: three or more paragraphs open with the same two characters, or three
    sentences in a row do. Typical after subjects are added back everywhere."""
    hits = []
    heads = collections.Counter(p[:2] for p in split_paragraphs(text) if han_count(p[:2]) == 2)
    for head, n in heads.items():
        if n >= 3:
            hits.append("段首“%s”×%d" % (head, n))
    sents = [s_[:2] for s_ in split_sentences(text) if han_count(s_[:2]) == 2]
    for i in range(len(sents) - 2):
        if sents[i] == sents[i + 1] == sents[i + 2]:
            hits.append("连续三句以“%s”开头" % sents[i])
            break
    return hits


def detect_dash_overuse(text: str) -> list[str]:
    return [p[:60] for p in split_paragraphs(text) if len(ZH_EM_DASH.findall(p.replace("——", "—"))) >= 2]


def detect_burstiness(text: str) -> dict:
    lengths = [han_count(s) for s in split_sentences(text)]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 4:
        return {"sentences": len(lengths), "cv": None, "monotonous": False}
    mean = statistics.mean(lengths)
    cv = statistics.pstdev(lengths) / mean if mean else 0.0
    return {"sentences": len(lengths), "cv": round(cv, 3), "monotonous": cv < 0.35}


def detect_paragraph_monotony(text: str) -> dict:
    lengths = [han_count(p) for p in split_paragraphs(text)]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 4:
        return {"paragraphs": len(lengths), "cv": None, "monotonous": False}
    mean = statistics.mean(lengths)
    cv = statistics.pstdev(lengths) / mean if mean else 0.0
    return {"paragraphs": len(lengths), "cv": round(cv, 3), "monotonous": cv < 0.4}


def detect_degenerate_repetition(text: str, n: int = 8) -> dict:
    chars = HAN.findall(text)
    if len(chars) < n * 3:
        return {"ratio": 0.0, "degenerate": False}
    grams = ["".join(chars[i:i + n]) for i in range(len(chars) - n + 1)]
    counts = collections.Counter(grams)
    ratio = sum(c for c in counts.values() if c > 1) / float(len(grams))
    worst = counts.most_common(1)[0]
    return {"ratio": round(ratio, 4), "degenerate": ratio > 0.20,
            "worst": worst[0] if worst[1] > 1 else None}


# ------------------------------------------------------------------- scoring
SCORE_DECISIVE = {"62", "63", "64", "65", "66", "47", "50", "48"}
SCORE_STRONG = {"16", "20", "21", "24", "18", "27", "30", "5", "69", "71"}
SCORE_SOFT = {"37", "57", "2", "23", "75", "9", "78", "7"}
SCORE_REPORT_ONLY = {"19", "22", "42", "54", "58", "17", "68", "74", "79", "83", "84", "85"}
SCORE_STYLE_ONLY = {"60", "82"}
SCORE_RHYTHM = {"40"}
SCORE_MIN_UNITS = 120
ESCALATOR = set(range(1, 40)) | {47, 48, 49, 50, 51, 69, 72, 73, 76, 77}
CONTENT_CAP, RHYTHM_CAP, VOCAB_CAP, VOCAB_FLOOR = 48.0, 18.0, 26.0, 6.0

# Rules that misfire on song lyrics, where repetition, short even lines and
# four-character runs are the form rather than a defect.
LYRICS_OFF = {"71", "40", "44", "42", "75", "37", "9", "7", "85"}


def _fam(key: str) -> str:
    return key.split("_", 1)[0]


def score(result: dict, text: str, burst: dict, para: dict) -> dict:
    n_units = max(units(text), 1)
    eff = max(n_units, SCORE_MIN_UNITS)
    diversity = load = 0.0
    rhythm_flags = 0
    seen = set()
    for key, val in result.items():
        if key.startswith("_"):
            continue
        fam = _fam(key)
        if fam in SCORE_REPORT_ONLY or fam in SCORE_STYLE_ONLY or fam == "1":
            continue
        if fam in SCORE_RHYTHM:
            rhythm_flags += 1
            continue
        count = min(val.get("count", 1), 5)
        load += (3.0 if fam in SCORE_DECISIVE else 1.0 if fam in SCORE_SOFT else 1.6) * count
        if fam in seen:
            continue
        seen.add(fam)
        diversity += (16.0 if fam in SCORE_DECISIVE else 10.0 if fam in SCORE_STRONG
                      else 2.5 if fam in SCORE_SOFT else 5.0)
    content = min(CONTENT_CAP, diversity + min(10.0, load / eff * 1000))
    cv = burst.get("cv")
    burst_term = 0.0 if cv is None else max(0.0, min(1.0, (0.45 - cv) / 0.45)) * 10.0
    pcv = para.get("cv")
    mono_term = 0.0 if pcv is None else max(0.0, min(1.0, (0.4 - pcv) / 0.4)) * 8.0
    rhythm = min(RHYTHM_CAP, rhythm_flags * 4.0 + burst_term + mono_term)
    vocab_rate = result.get("1_ai_vocabulary", {}).get("count", 0) / eff * 1000
    vocab = min(VOCAB_CAP, max(0.0, vocab_rate - VOCAB_FLOOR) * 0.9)
    total = round(min(100.0, content + rhythm + vocab))

    fams = {int(_fam(k)) for k in result
            if not k.startswith("_") and _fam(k).isdigit()
            and _fam(k) not in SCORE_REPORT_ONLY and _fam(k) not in SCORE_STYLE_ONLY}
    decisive = {_fam(k) for k in result if _fam(k) in SCORE_DECISIVE}
    thin = D.score_confidence(n_units, len(fams))["confidence"] in ("none", "low")
    if len(decisive) >= 2:
        total = max(total, 65)
    elif len(decisive) == 1 and not thin:
        total = max(total, 45)
    if n_units < SCORE_MIN_UNITS:
        content_fams = fams & ESCALATOR
        if len(content_fams) >= 3:
            total = max(total, 45)
        elif len(content_fams) >= 2:
            total = max(total, 25)
    elif n_units >= 400:
        if len(fams) >= 6:
            total = max(total, 45)
        elif len(fams) >= 5:
            total = max(total, 25)
    return {"score": total, "band": D._band(total), "scored_families": len(fams)}


# ---------------------------------------------------------------------- scan
def scan_zh(raw_text: str, syntax: str = "markdown", lyrics: bool = False) -> dict:
    capped = raw_text[:D._SCAN_CAP]
    mapper = D._map_latex if syntax == "latex" else D._map_code
    prose_chars = mapper(capped, lambda span: "|CODE|")
    prose = mapper(capped, lambda span: re.sub(r"[^\n]", " ", span))
    text, evasion = D.defuse_evasion(D.strip_markdown_furniture(D.strip_quoted_spans(prose)))
    if lyrics:
        text = SECTION_TAG.sub("", text)

    result: dict = {}
    simple = [
        ("1_ai_vocabulary", AI_VOCAB, "AI 高频词"),
        ("3_promotional", PROMO, "宣传语"),
        ("5_simple_yet", SIMPLE_YET, "“简单却……”套话"),
        ("10_significance_inflation", SIGNIFICANCE_INFLATION, "意义拔高"),
        ("11_notability_list", NOTABILITY, "堆砌媒体与粉丝数"),
        ("12_vague_attribution", VAGUE_ATTR, "模糊归因"),
        ("15_false_range", FALSE_RANGE, "宏大的“从……到……”"),
        ("16_tail_inflation", ING_TAIL, "句尾补充式拔高（彰显了……）"),
        ("17_negative_parallelism", NEG_PARALLEL, "不是 X 而是 Y"),
        ("18_not_x_just_y", NOT_X_JUST_Y, "“没有 X，只有 Y”"),
        ("19_filler_phrases", FILLER, "填充短语"),
        ("20_empty_pivot_phrase", EMPTY_PIVOT, "空转折（值得注意的是）"),
        ("21_outcome_speculation", OUTCOME_SPECULATION, "结果推测尾巴（引发思考）"),
        ("22_authority_trope", AUTHORITY_TROPE, "借权威口吻（说白了、归根结底）"),
        ("23_editorial_interjection", EDITORIAL_INTERJECTION, "编辑式插话"),
        ("24_self_thoroughness", SELF_THOROUGHNESS, "自夸全面（一文读懂）"),
        ("25_question_answer", QA_RHETORICAL, "自问自答"),
        ("26_concrete_evidence", CONCRETE_EVIDENCE, "“用事实说话”式辩护"),
        ("27_compulsive_intro", COMPULSIVE_INTRO, "起跑式开头（你是否……）"),
        ("30_diff_anchored", DIFF_ANCHORED, "围绕改动写（与旧版相比）"),
        ("31_signposting", SIGNPOSTING, "路标式预告（让我们深入看看）"),
        ("32_catalog_leadin", CATALOG_LEADIN, "空泛列举引语（采用多种……）"),
        ("32_definitional_metaphor", DEFINITIONAL_METAPHOR, "定义式比喻（是……的灵魂）"),
        ("36_challenges_section", CHALLENGES, "公式化“挑战与机遇”"),
        ("36_faux_insight", FAUX_INSIGHT, "伪洞见铺垫（很多人不知道的是）"),
        ("37_colon_reveal", COLON_REVEAL, "冒号揭晓（真相是：）"),
        ("38_compulsive_conclusion", COMPULSIVE_CONCLUSION, "套路收尾词（综上所述）"),
        ("39_generic_positive_end", GENERIC_END, "空洞的正面结尾（未来可期）"),
        ("47_chatbot_artifacts", CHATBOT, "聊天机器人残留"),
        ("47_chat_residue", CHAT_RESIDUE, "对话残留"),
        ("48_sycophantic", SYCOPHANTIC, "讨好语气"),
        ("50_cutoff_disclaimer", CUTOFF, "知识边界免责"),
        ("50_privacy_filler", PRIVACY_FILLER, "猜测式隐私填充"),
        ("51_copula_avoidance", COPULA_AVOID, "回避“是／有”"),
        ("56_boldface", D.BOLD, "粗体当装饰"),
        ("33_inline_header_list", D.INLINE_HEADER, "行内标题式列表"),
        ("60_mixed_punctuation", ZH_MIXED_PUNCT, "中英标点混用"),
        ("63_placeholder_text", D.PLACEHOLDER, "占位符残留"),
        ("63_placeholder_zh", PLACEHOLDER_ZH, "中文占位符残留"),
        ("64_chatbot_ref_markup", D.CHATBOT_REF_MARKUP, "聊天引用标记泄漏"),
        ("65_ai_tracking_params", D.AI_UTM, "AI 来源追踪参数"),
        ("69_canonical_slop", CANONICAL_SLOP, "典型营销腔"),
        ("76_suizhe_opener", SUIZHE, "“随着……的发展”式开头"),
    ]
    for key, pattern, label in simple:
        _hit(result, key, label, _find(text, pattern))

    if not lyrics:
        _hit(result, "9_ai_fiction_names", "AI 小说常用人名",
             _find(text, FICTION_NAMES) if len(set(_find(text, FICTION_NAMES))) >= 2 else [])
    dialect = _find(text, MODEL_DIALECT)
    _hit(result, "2_model_dialect", "模型腔／网文腔用语", dialect if len(dialect) >= 2 else [])
    official = _find(text, OFFICIALESE)
    _hit(result, "78_officialese", "官腔套话", official if len(set(official)) >= 2 else [])
    _hit(result, "79_overclaim", "结论强度词（需证据，仅提示）", _find(text, OVERCLAIM))
    jinxing = _find(text, JINXING)
    _hit(result, "73_jinxing_verb", "“进行＋动词”", jinxing if len(jinxing) >= 2 else [])
    _hit(result, "72_de_stacking", "层叠的“的”", detect_de_stacking(text))
    _hit(result, "74_bei_stacking", "被字句堆叠", detect_bei_stacking(text))
    if not lyrics:
        _hit(result, "82_zh_numerals", "时间、时长、价钱用了中文数字（偏好，仅提示）",
             [m.group(0) + "…" for m in ZH_DIGIT_RE.finditer(text)])
        _hit(result, "84_unfinished_state", "状态没说完（快睡着，→快睡着了／快睡着时，仅提示）",
             [text[max(0, m.start() - 6):m.end() + 1] for m in UNFINISHED_STATE.finditer(text)])
        _hit(result, "83_subject_drop", "句首缺主语（仅提示，需通读判断）",
             [text[m.start():m.end() + 8].strip() for m in SUBJECT_DROP.finditer(text)])
    _hit(result, "7_parallel_triad", "同头三连排比", [m.group(0) for m in TRIAD.finditer(text)])
    _hit(result, "75_four_char_parallel", "四字词排比", [m.group(0) for m in FOUR_CHAR_RUN.finditer(text)])
    _hit(result, "54_hedge_stacking", "限定词堆叠", detect_hedge_stacking(text))
    _hit(result, "37_transition_cluster", "连接词扎堆", detect_transition_clusters(text))
    _hit(result, "85_opener_sameness", "段首或连续句首雷同（仅提示）", detect_paragraph_openers(text))
    _hit(result, "42_opener_repetition", "句首复读", detect_opener_repetition(text))
    _hit(result, "58_em_dash_overuse", "破折号过多（每段≥2）", detect_dash_overuse(text))
    emojis = D.EMOJI.findall(text)
    _hit(result, "57_emojis", "表情符号", emojis)

    rep = detect_degenerate_repetition(text)
    if rep["degenerate"]:
        result["71_degenerate_repetition"] = {
            "label": "退化重复", "count": 1,
            "samples": ["%.0f%% 的八字片段重复；最多：%s" % (100 * rep["ratio"], rep.get("worst"))]}

    burst = detect_burstiness(text)
    if burst["monotonous"]:
        result["40_sentence_monotony"] = {"label": "句长单调", "count": 1,
                                          "samples": ["cv=%s，低于 0.35" % burst["cv"]]}
    para = detect_paragraph_monotony(text)
    if para.get("monotonous"):
        result["44_paragraph_monotony"] = {"label": "段落长度一致", "count": 1,
                                           "samples": ["cv=%s，低于 0.4" % para["cv"]]}

    # Character layer: reused from upstream unchanged.
    inv = D.detect_invisible_chars(prose_chars)
    zh_zw = zh_zero_width(prose_chars)
    inv_total = inv["count"] + len(zh_zw)
    if inv_total:
        samples = D._labelled_samples(inv["chars"]) if inv["count"] else []
        if zh_zw:
            samples.append("U+200B/U+2060 紧挨汉字: %d" % len(zh_zw))
        result["62_invisible_chars"] = {"label": "零宽／不可见字符", "count": inv_total,
                                        "samples": samples[:MAX_SAMPLES]}
    inv = {"count": inv_total}
    nbsp = D.detect_nonstandard_spaces(prose_chars)
    if nbsp["count"]:
        result["67_nonstandard_spaces"] = {"label": "非标准空格", "count": nbsp["count"],
                                           "samples": D._labelled_samples(nbsp["chars"])}
    trailing = D.detect_trailing_whitespace(prose_chars)
    if trailing["artifact"]:
        result["68_trailing_whitespace"] = {"label": "多余空白", "count": 1,
                                            "samples": ["行尾或文件首尾有多余空白"]}
    rules = D.detect_decorative_rules(prose_chars)
    if rules:
        result["70_decorative_rules"] = {"label": "装饰性分隔线", "count": rules["count"],
                                         "samples": rules["samples"]}
    homo = D.detect_homoglyphs(prose_chars)
    _hit(result, "66_homoglyphs", "混用字形（同形异码）", homo)

    if lyrics:
        cliches = _find(text, LYRIC_CLICHE)
        if len(set(cliches)) >= 3:
            _hit(result, "77_lyric_cliche_cluster", "歌词空泛意象扎堆", cliches)
        for key in [k for k in result if _fam(k) in LYRICS_OFF]:
            del result[key]
        burst, para = {"cv": None}, {"cv": None}

    sc = score(result, text, burst, para)
    n_units = units(text)
    result["_metrics"] = {
        "language": "zh",
        "mode": "lyrics" if lyrics else "prose",
        "han_chars": han_count(text),
        "word_equivalents": n_units,
        "sentences": burst.get("sentences"),
        "length_cv": burst.get("cv"),
        "paragraph_cv": para.get("cv"),
        "repetition_ratio": rep["ratio"],
        "evasion_defused": evasion,
        "invisible_chars": inv["count"],
        "nonstandard_spaces": nbsp["count"],
        "homoglyphs": len(homo),
        "ai_tell_score": sc["score"],
        "ai_tell_band": sc["band"],
        "patterns_flagged": sum(1 for k in result if not k.startswith("_")),
        "truncated": len(raw_text) > D._SCAN_CAP,
    }
    result["_metrics"].update(D.score_confidence(n_units, sc["scored_families"]))
    return result


def scan(raw_text: str, syntax: str = "markdown", lyrics: bool = False) -> dict:
    """Route by script: Chinese to scan_zh, everything else to upstream."""
    if lyrics or is_chinese(raw_text[:D._SCAN_CAP]):
        return scan_zh(raw_text, syntax, lyrics)
    result = D.scan(raw_text, syntax=syntax)
    result["_metrics"]["language"] = "en"
    return result


USAGE = """用法：detect_zh.py [--clean] [--lyrics] [--] [FILE]

扫描 FILE（不给则读 stdin），输出 JSON 报告。中文文本走中文规则，其他文本交给上游 detect.py。

  --clean   输出清理后的文本（去零宽字符、规范空格、裁剪空白），不输出报告
  --zh-digits  与 --clean 一起用：把时间、时长、价钱的中文数字改成阿拉伯数字（九点→9点）
  --lyrics  歌词模式：去掉段落标签，关闭重复、句长单调、四字排比等对歌词不适用的规则
  --        之后的参数一律当作文件名
  --help    显示本说明
"""


def main() -> int:
    import zipfile
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
    paths, flags, literal = [], set(), False
    for arg in sys.argv[1:]:
        if literal or not arg.startswith("-"):
            paths.append(arg)
        elif arg == "--":
            literal = True
        elif arg in ("--clean", "--lyrics", "--zh-digits"):
            flags.add(arg)
        elif arg in ("--help", "-h"):
            sys.stdout.write(USAGE)
            return 0
        else:
            print(json.dumps({"error": "未知选项：%s，见 --help" % arg}, ensure_ascii=False), file=sys.stderr)
            return 2
    try:
        text, newline = D.read_source(paths[:1])
    except (OSError, zipfile.BadZipFile) as e:
        print(json.dumps({"error": "无法读取输入：%s" % (getattr(e, "strerror", None) or e)},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    if not text.strip():
        print(json.dumps({"error": "输入为空"}, ensure_ascii=False), file=sys.stderr)
        return 1
    syntax = "latex" if paths and os.path.splitext(paths[0])[1].lower() == ".tex" else "markdown"
    if "--clean" in flags:
        cleaned = clean_zh(text, syntax=syntax)
        if "--zh-digits" in flags:
            cleaned = zh_digits(cleaned)
        if text.endswith("\n") and not cleaned.endswith("\n"):
            cleaned += "\n"
        sys.stdout.write(cleaned.replace("\n", newline) if newline != "\n" else cleaned)
        return 0
    print(json.dumps(scan(text, syntax, lyrics="--lyrics" in flags), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
