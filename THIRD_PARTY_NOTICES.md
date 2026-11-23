# 第三方组件与许可声明

本项目代码按仓库根目录的 **Apache License 2.0** 发布。以下第三方数据、字体和依赖
不自动适用项目的 Apache-2.0 许可证，各自保留原有权利。

> 本文件只做归属声明和许可信息记录，**不构成对任何第三方数据的再分发授权**。

## 汇总

| 组件 | 本项目中的使用 | 上游地址 | 许可证状态 |
| --- | --- | --- | --- |
| hantang/search-wubi | `data/char_roots.json` 的逐字拆解、识别码 `flag`、PUA 字根字体来源 | <https://github.com/hantang/search-wubi> | **未声明许可证** |
| 86wb.ysepan.com | hantang/search-wubi 标注的字根拆解/字体上游 | <https://86wb.ysepan.com> | 公开页未提供明确的开源/再分发许可 |
| rime/rime-wubi | `data/chars.json`、`data/words.json`、`data/pools.json`、`_ref/wubi86.dict.yaml` | <https://github.com/rime/rime-wubi> | **LGPL-3.0** |
| KyleBing/rime-wubi86-jidian | 上游五笔编码参考方案 | <https://github.com/KyleBing/rime-wubi86-jidian> | **MIT** |
| CNMan/UnicodeCJK-WuBi | 上游五笔编码参考方案 | <https://github.com/CNMan/UnicodeCJK-WuBi> | 未声明；仅引用，不随项目分发其数据 |
| python-docx | `.docx` 解析 | <https://python-docx.readthedocs.io/> | **MIT** |

## 1. hantang/search-wubi

- 地址：<https://github.com/hantang/search-wubi>
- 本项目使用：
  - `data/data-wubi-v86.tsv`：逐字 `units`（PUA 字根字形）、`flag`（识别码）、`segments`（笔画段）
  - `data/data-chars.tsv`：字级、IDS、部首，用于常用字筛选和校验
  - `docs/static/font/黑体字根.ttf`：PUA 字根字形字体
- 生成结果：
  - `data/char_roots.json`
  - `web/fonts/wubi-roots.ttf`
- 该仓库 README 的「数据相关」一节写明：**“字根拆解和对应字体来自 86wb.ysepan.com”**。
- 许可证核查（2026-11-23）：
  - GitHub API 的 `license` 字段为空；
  - `https://api.github.com/repos/hantang/search-wubi/license` 返回 404；
  - 仓库根目录没有 `LICENSE` 文件；
  - 因此**不能确认允许再分发**。

**处理方式**：默认不在公开仓库提交 `data/char_roots.json` 和 `web/fonts/wubi-roots.ttf`。
如已获得权利人明确许可，再随项目分发，并保留本文件和 README 中的署名。

## 2. 86wb.ysepan.com

- 地址：<https://86wb.ysepan.com>
- 用途：hantang/search-wubi 标注的字根拆解和字体上游。
- 许可证状态：公开入口页未提供明确的开源/再分发许可声明；无法据此确认授权。

## 3. rime/rime-wubi

- 地址：<https://github.com/rime/rime-wubi>
- 本项目使用：
  - `data/chars.json`
  - `data/words.json`
  - `data/pools.json`
  - `_ref/wubi86.dict.yaml`（仅构建参考，不参与运行时）
- 许可证：**GNU Lesser General Public License v3.0（LGPL-3.0）**。
- 再分发这些派生数据前，请保留上游署名和许可证，并遵守 LGPL-3.0 的要求。
- 许可证文本：<https://github.com/rime/rime-wubi/blob/master/LICENSE>

## 4. KyleBing/rime-wubi86-jidian

- 地址：<https://github.com/KyleBing/rime-wubi86-jidian>
- 用途：hantang/search-wubi README 列出的五笔编码参考方案之一。
- 许可证：**MIT**。
- 本项目没有直接复制该仓库的完整数据；仅作为上游编码方案引用。

## 5. CNMan/UnicodeCJK-WuBi

- 地址：<https://github.com/CNMan/UnicodeCJK-WuBi>
- 用途：hantang/search-wubi README 列出的五笔编码参考方案之一。
- 许可证状态：未声明。
- 本项目不随项目分发该仓库数据，仅作为来源引用。

## 6. python-docx

- 地址：<https://python-docx.readthedocs.io/>
- 用途：解析 `.docx` 文章。
- 许可证：MIT。
- 安装：`python -m pip install python-docx`

## 引用要求

如果转载、分发或再发布本项目，请至少保留：

1. 本文件；
2. README 的「数据来源与许可」「引用与参考」章节；
3. 上述上游项目的名称、链接和许可证状态；
4. 若分发 `char_roots.json`/`wubi-roots.ttf`，附上权利人的许可证明。

如你是上述数据的权利人，认为本项目中的归属或使用方式需要调整，请通过项目 issue 联系维护者。
