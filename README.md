# sloptrim-zh

中文去 AI 味工具：一个 Claude Code / Codex Skill，加一个本地检测脚本。

它找出中文文本里的模板化表达和机器痕迹，给 0–100 分，再按分数决定改多少：分数低就几乎不动，分数高才整篇重写。改写时保留事实、数字、归因和限定词，不替作者编内容。

只用 Python 标准库，不联网，不调用模型。

> 本项目基于 [sloptrim](https://github.com/seyedehsanhadi/sloptrim)（Apache-2.0）修改，中文模式目录参照 [Humanizer-zh](https://github.com/op7418/Humanizer-zh)（MIT）的汉化思路。与两位原作者无关联，也未获其背书。详见 [NOTICE](NOTICE)。

## 和两个上游项目的关系

| | sloptrim | Humanizer-zh | sloptrim-zh |
|---|---|---|---|
| 语言 | 英文 | 中文 | 中文（英文自动转交原版） |
| 形式 | Skill + 检测脚本 + 钩子 | 只有 Skill 提示词 | Skill + 检测脚本 |
| 打分 | 有，按分数分档改写 | 无 | 有，沿用原版思路，中文重新校准 |
| 模式数 | 71 | 31 | 77 个编号（删 7 个英文专属，新增 6 个中文） |

汉化方法沿用 Humanizer-zh 汉化 Humanizer 的做法：

1. 中文同样成立的模式保留，例句用中文重写；
2. 英文专属的删掉（缩写、标题大小写、分号括号统计等）；
3. 补上中文特有的：层叠的“的”、“进行＋动词”、被字句堆叠、四字词排比、“随着……的发展”开头；
4. 每条附“保留”边界，避免机械地删排比、删破折号；
5. 优先级：先保事实和确定程度，再顾文体和作者声音，最后才改表达。

检测脚本是新增的中文实现。原版 `detect.py` 原样保留，负责英文文本和零宽字符等字符层检查。

## 安装

```bash
git clone https://github.com/<你的账号>/sloptrim-zh.git ~/.claude/skills/sloptrim-zh
```

Windows PowerShell：

```powershell
git clone https://github.com/<你的账号>/sloptrim-zh.git $HOME\.claude\skills\sloptrim-zh
```

Codex 用户把目录放到 `~/.codex/skills/` 下。重启后说“帮我去一下 AI 味”或调用 `/sloptrim-zh`。

## 单独使用检测脚本

```bash
python scripts/detect_zh.py 文章.md              # 输出 JSON 报告
python scripts/detect_zh.py --lyrics 歌词.txt    # 歌词模式
python scripts/detect_zh.py --clean 文章.md > 干净.md
```

报告里最重要的是 `_metrics.ai_tell_score`、`ai_tell_band` 和 `confidence`：

| 分数 | 档位 | Skill 的处理 |
|---|---|---|
| 0–20 | clean | 只清字符，不改写 |
| 21–40 | light tells | 只改被标出的句子 |
| 41–60 | mixed | 整体改写 |
| 61–100 | heavy / pervasive tells | 整体改写 |

不到约 180 个汉字时 `confidence` 为 low 或 none，分数不可靠。

### 歌词模式

`--lyrics` 去掉 `[Verse]`、`[Chorus]` 等段落标签，关闭重复、句长单调、四字排比、句首复读等规则（这些在歌词里是正常形式），另外打开“歌词空泛意象扎堆”（余生、人海、宿命、星河……出现三种以上）。

## 校准

中文打分线用一小批文本做过初步校准，不是大规模验证：

- **人写**：23 篇，12 篇中文维基百科条目，11 篇民国时期散文与小说（朱自清、鲁迅、胡适、许地山，取自维基文库，部分为繁体）。全部在 0–16 分，均为 clean。
- **AI 风格**：8 篇，覆盖景点介绍、公众号文章、产品发布、年终总结、探店帖、科普、读后感、演讲稿。6 篇在 43–69 分；年终总结 25 分；小红书风格探店帖 15 分。

已知局限：

- AI 样本由维护者用模型生成，规则也参照了这些样本，存在过拟合风险。欢迎提交更多真实样本。
- 小红书、公众号的网络口语，人和 AI 写出来很像，检测脚本基本分不开。
- 公文、工作总结的官腔是人类长期写作习惯，脚本对它们打分偏低是有意为之。
- 人写样本缺少当代散文和网络文本。

校准语料不随仓库分发。

## 测试

```bash
python -m unittest discover tests
```

覆盖每条检测规则的命中与不命中、分数下限、中英文路由、代码块忽略、零宽字符清理、歌词模式、命令行和“不联网”。

## 伦理

分数描述的是眼前这段文字，不判断作者是谁，不能用来指控任何人，也不用于规避学术诚信审查。见 [ETHICS.md](ETHICS.md)。

## 许可

Apache-2.0，见 [LICENSE.txt](LICENSE.txt) 与 [NOTICE](NOTICE)。Humanizer-zh 的 MIT 许可文本见 `references/HUMANIZER-ZH-LICENSE.txt`。
