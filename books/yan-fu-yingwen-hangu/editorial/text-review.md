# 《英文漢詁》文字检查记录

检查时间：2026-10-03T18:37:57+08:00；检查者：Codex。

已完成一轮基于现有 Markdown 的文字勘误，修正 9 处文本问题，保留 10 项疑点。
改字依据为现有稿件上下文和同书术语对照；不据记忆补写缺失正文，不自动转换繁简、异体字、旧拼法或语法反例。
本记录不是逐字影像校勘或人工出版验收；转录忠实性、漏文及页覆盖仍待核对，出版 XHTML 尚未接受。

## 已修正文字

| 文件及行号 | 原读 | 改为 | 文内依据 |
| --- | --- | --- | --- |
| [005-chapter-03.md](../md/005-chapter-03.md)：117 | `指詞性辨昇` | `指詞性辨析` | 同一注释后文明确释为词性分析，辨昇为词语误写；只修正导入注释，不将其视为古籍正文。 |
| [009-chapter-07.md](../md/009-chapter-07.md)：629 | `Will 用用于第二三身` | `Will 用于第二三身` | 相邻用字无语法示例作用，为重复输入；保留原于字。 |
| [006-chapter-04.md](../md/006-chapter-04.md)：102 | `*books-s*` | `*book-s*` | 本段说明单数名词加 s 构成复数，紧接着明确写作 book-s；删除词根中重复的 s，保留分词素连字符。 |
| [012-chapter-10.md](../md/012-chapter-10.md)：79 | `專主關合計法` | `專主關合句法` | 同段反复论述挈合部关合句法，计法无对应术语；据本文一致用语订正。 |
| [015-chapter-13.md](../md/015-chapter-13.md)：51（2处） | `日子句` | `曰子句` | 本段给子句下定义，且同段开头为曰句主、曰谓语；两处日作称名动词，应为曰。 |
| [019-chapter-17.md](../md/019-chapter-17.md)：15 | `其成句者日子句` | `其成句者曰子句` | 与前句其不成句者曰仂语对举，按同段称名用法订正日、曰混淆。 |
| [019-chapter-17.md](../md/019-chapter-17.md)：582 | `Subjective Complemennt` | `Subjective Complement` | 同章多处同一术语写作 Subjective Complement；删除词中重复的 n。 |
| [019-chapter-17.md](../md/019-chapter-17.md)：588 | `Subordinatie Conjunction` | `Subordinative Conjunction` | 本处指相从挈合，与篇十的 Subordinative Conjunctions 及其单数释词相同，补回术语中缺失的 v。 |

完整编辑决定保存在 [decisions.jsonl](decisions.jsonl)，均待人工复核；修改前稿件保存在同目录的 `*.original.md`。

## 未决疑点

| 文件 | 保留原读或现象 | 待核事项 |
| --- | --- | --- |
| [001-prefatory-texts.md](../md/001-prefatory-texts.md) | `戢畢揣摩 / 規畢揣摩` | 前后对应语句用字不同，无法仅凭文内决定原读；保留并列疑点。 |
| [001-prefatory-texts.md](../md/001-prefatory-texts.md) | `皆可罔解 / 斝茶然私憂 / 篇時者觀化 / 爪華蹈衰` | 疑似识别问题，缺少能确定唯一原字的文本依据，暂不改。 |
| [001-prefatory-texts.md](../md/001-prefatory-texts.md) | `为 / 异 / 画 / 词` | 繁简与异体混用仅标记现象；未自动转换或将字形差异一律当错字。 |
| [001-prefatory-texts.md](../md/001-prefatory-texts.md) | `最重要的散作家、哲學家` | 导入注释中的散作家疑缺字；不能仅凭常见词语补字，暂保留。 |
| [006-chapter-04.md](../md/006-chapter-04.md) | `陰屬形昇陽屬 / 當今不爾爾者` | 形昇与重复爾字疑误，缺少能唯一确定替换或删除字的文内证据。 |
| [009-chapter-07.md](../md/009-chapter-07.md) | `欲不然䀈不可` | 䀈字在句中疑有识别错误，原字无法仅凭现有稿件确定。 |
| [012-chapter-10.md](../md/012-chapter-10.md) | `布魯達 Brutus 自解於衆 / 注释称安東尼的演講詞` | 正文指定的说话人与导入注释归属不一致；暂不根据记忆更改人名或注释。 |
| [014-chapter-12.md](../md/014-chapter-12.md) | `midsphiman / whit-ness / fulfil 賤言 / 會注重前系 / figthing / physicsist` | 拼写或用字疑误；词源说明及旧读法需要原文证据，不据现代拼写表批量改写。 |
| [019-chapter-17.md](../md/019-chapter-17.md) | `不娉娉於分立之字` | 娉娉疑为其他叠词之误，不能从现稿唯一确定原字；保留。 |
| [020-chapter-18.md](../md/020-chapter-18.md) | `文字必有句主，(或作句讀，皆音逗)` | 句主与括注读音、篇章讨论的句读不相应；可能是句豆等字的识别问题，暂不凭推断替换。 |

## 文本结构检查

按显式书目顺序检查 21 份工作 Markdown（包含页码表，不包含原稿快照）。
共有 163 条脚注定义；未发现未定义的脚注引用、重复脚注 ID 或失效的本地 Markdown 文件链接。
脚注引用与定义均有对应，未发现无正文引用的脚注定义。
正文节号 §1—§192 连续、顺序正确且无重复；18 篇文件顺序与清单一致。节号齐全不能证明段落内容没有遗漏。
页码表中未经证实的“已完成”声明已改为本轮文字检查范围；导入页域没有据此晋升为已核验页覆盖。

本轮覆盖的工作稿：

- [001-prefatory-texts.md](../md/001-prefatory-texts.md)
- [002-contents.md](../md/002-contents.md)
- [003-chapter-01.md](../md/003-chapter-01.md)
- [004-chapter-02.md](../md/004-chapter-02.md)
- [005-chapter-03.md](../md/005-chapter-03.md)
- [006-chapter-04.md](../md/006-chapter-04.md)
- [007-chapter-05.md](../md/007-chapter-05.md)
- [008-chapter-06.md](../md/008-chapter-06.md)
- [009-chapter-07.md](../md/009-chapter-07.md)
- [010-chapter-08.md](../md/010-chapter-08.md)
- [011-chapter-09.md](../md/011-chapter-09.md)
- [012-chapter-10.md](../md/012-chapter-10.md)
- [013-chapter-11.md](../md/013-chapter-11.md)
- [014-chapter-12.md](../md/014-chapter-12.md)
- [015-chapter-13.md](../md/015-chapter-13.md)
- [016-chapter-14.md](../md/016-chapter-14.md)
- [017-chapter-15.md](../md/017-chapter-15.md)
- [018-chapter-16.md](../md/018-chapter-16.md)
- [019-chapter-17.md](../md/019-chapter-17.md)
- [020-chapter-18.md](../md/020-chapter-18.md)
- [page-map.md](../md/page-map.md)

工作稿集合 SHA-256：`d2e06076a6ca2673c39a508484901107e2f99eef16003774ad63601664987628`。
摘要算法：按上列显式顺序拼接项目相对路径、制表符、每份当前 Markdown 的 SHA-256 与 LF，再计算 SHA-256。
