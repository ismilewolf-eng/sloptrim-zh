# 更新记录

## 0.1.0（2026-10-11）

- 首个版本。基于 sloptrim 0.9.4（commit 38dbb7c）。
- 新增 `scripts/detect_zh.py`：中文规则 63 条、57 个模式族（含中文新增 72–77），中文句长与段落节奏指标，歌词模式 `--lyrics`，中文文档中紧挨汉字的零宽字符清理。英文文本交给原版 `detect.py`。
- 新增中文 `SKILL.md` 与 `references/patterns-zh.md`，例句全部原创，每条附“保留”边界。
- 用 23 篇人写中文（维基百科条目、民国散文）和 8 篇 AI 风格样本做了初步校准，详见 README。
- 测试：`python -m unittest discover tests`。
