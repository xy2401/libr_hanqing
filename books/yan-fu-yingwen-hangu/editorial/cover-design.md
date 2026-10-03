# 《英文漢詁》封面设计记录

设计日期：2026-10-03。书籍 ID：`yan-fu-yingwen-hangu`。当前采用双语书页融入水墨画的版本，全书仍为 draft。

地球仪、中西书册与释义笺组成水墨书案。对开的书页左侧写 Noun、Verb、Syntax，右侧对应名物、云謂、句法；中英字迹与书页一起绘制，随纸面透视、弯曲与墨色变化。右侧留白独立竖排书名与作者。

## 提示词与生成

使用助手内置 `image_gen.imagegen` 编辑加字前的原始底画，重画书页双语与批注；不使用后期字体贴字代替水墨场景文字。

- 完整实际提示词：[cover-prompt.txt](cover-prompt.txt)；主题与制作规范见本记录。
- 模式：built-in edit；`transparent_background=false`，没有调用外部接口或本地 OCR。
- 生成时参考加字前的底画，输入 SHA-256 为 `8fd3e91955e18a92c514ba76cc07f771447ce863fe1590a92a41fa92b1ba3f48`。该中间底画已按用户要求清理，哈希仅作为生成记录保留。
- 返回文件：`exec-284d146a-deae-47cc-9b7d-2acb99144513.png`。具体模型标识与随机种子未返回，保持未知。
- 生成原画保留在 `images/cover.source.png`，没有再对书页局部贴字或修改；所有场景文字都在这张位图中。
- 三组术语及少量词义说明用于封面主题，是艺术构图，不是原书页影像、原书引文、正文或副标题。已直接查看完整图和书页细节；细小背景笔墨只作氛围，不视为可用转录。

## 题签与出版资源

原画按 2:3 比例机械缩放到 1400×2100，不裁切主体；JPEG 底画小于 1.5MB。
只有正式书名“英文漢詁”和作者“嚴復”用 Windows KaiTi Regular 独立编排。
书名字形最大高 110px、步进 142px、列中心 x=1110、首格顶部 y=210；作者字形最大高 52px、步进 74px、列中心 x=950、首格顶部 y=650，墨色 `#202924`，保留至少 40px 画布边距。

`images/cover.svg` 的可编辑文字仅为书名和作者；发行 SVG 将这六个题签字转为六条轮廓，嵌入完整 JPEG 底画。场景中的双语属于底画，不增加 SVG 文字、轮廓或矩阵。
`images/cover.preview.jpg` 是完整预览，OPF 唯一 `cover-image` 指向 `src/epub/images/cover.svg`，旧版备选只保存在出版 `src/` 之外。
本轮使用已有 `tools/build-cover.ps1` 编排；环境为 Windows GDI+、Node.js v24.19.0、sharp 0.35.4，JPEG 质量 90。

## 规范范围

参考 [Standard Ebooks 的尺寸及素材、源码、发行分工](https://github.com/standardebooks/manual/blob/master/10-art-and-images.rst)，采用本项目自有的中文古籍水墨 profile。AI 生成画及水墨风格属于项目差异，不宣称严格符合官方封面规范。
本轮调整封面资源及提示词，不改变正文、文字底本或校勘状态，未生成最终 EPUB，也未执行 EPUBCheck 或阅读器验收。

## 本次验证

已直接查看完整封面、放大的书页细节和 240×360 缩略图，核对三组中英文、纸面透视、墨色与留白。三组术语之外的背景笔墨仅作为插画氛围，不声称全部细字可辨认。
原画与内置生图返回文件逐字节一致，实际提示词与提交实参一致；原画为 2:3，两种 JPEG 均为 1400×2100，底画小于 1.5MB。
源 SVG 仅有书名与作者两个文字元素，发行图为六个题签字的轮廓，没有插画文字叠层或 transform；嵌入 JPEG 与保存底画逐字节一致。发行 SVG 重渲染所得 JPEG 与保存预览逐字节一致。
OPF 仅引用当前发行图，书籍仍为 draft；六项当前文件与八项油画版文件的 SHA-256 均核对通过。
`uv build` 成功，wheel 与 sdist 均未收录 books 或 data。本轮未改 Python 代码；没有重跑上轮已通过的十九项书目/骨架测试。

## 当前文件

路径相对本书目录。

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `images/cover.source.png` | 2,749,563 | `be3ad4716ad6d76646eb2b1f0566ce225dea84b99aa51b5f4f8fd3a62459d16b` |
| `images/cover.jpg` | 479,660 | `31ae38330db3e14c1d6c11d80bb0eefe35b2f8d1614ddc360cc5fbdd25b3528c` |
| `images/cover.svg` | 771 | `e54390f35eb38076de36df180b0a1d1d12ce53c86b4b99d2b2e7bf7e3f699e5e` |
| `images/cover.preview.jpg` | 492,069 | `227703179599182099d31847a4f2857b6441de8d31af04a5c7fccd82f46b3882` |
| `src/epub/images/cover.svg` | 669,577 | `7ca968d17cabe0e459f0c531eca447321de4d8809f800ad7e7ab3d10622f598f` |
| `editorial/cover-prompt.txt` | 3,336 | `cbc1565a9fa523de88fce2958bf38624f3886206b807172e30c49bbdd35b8dba` |

## 保留范围

按用户要求只保留最新版与最早油画版，保留版本的源画、源码、预览、发行图、实际提示词和设计记录继续保存。中间水墨版本、叠字版、提示词草案副本及封面处理缓存已清理。

## 油画版备份

[油画版预览](../images/cover-oil.preview.jpg)。油画原画、排版和制作记录继续按原字节保留，
`cover-oil.svg` 使用独立的油画底图链接；原记录中的无前缀路径按本节映射读取。
全部备份都保存在出版 `src/` 外，不作为新 EPUB 的候选 manifest 项。

| 改版前路径 | 当前备份路径 | SHA-256 |
| --- | --- | --- |
| `images/cover.source.png` | `images/cover-oil.source.png` | `c28dd82ca85177777d284eba2a914dea77991ed97b46d0c0d56d2123bc5f1d94` |
| `images/cover.jpg` | `images/cover-oil.jpg` | `89d465fe36aa881b24751c560b54d7ec8039841829fe30a8cea3c909c9215310` |
| `images/cover.svg` | `images/cover-oil.original.svg` | `ba01c946bff6ed9970a052cc45b083c222e9d4ff896cef32348c7e6c47d9c2c2` |
| `images/cover.preview.jpg` | `images/cover-oil.preview.jpg` | `4f679bc9148e257249726583540cbacbea33ca14629e4b0d5e2a5e8a8473b48b` |
| `src/epub/images/cover.svg` | `images/cover-oil.epub.svg` | `8b08652975a6bb565428fa049d0cdb3a3c69f33a045b8a86a6f081d88e26a540` |
| `editorial/cover-prompt.txt` | `editorial/cover-oil-prompt.txt` | `9509af47b7dc91ceace1272f28bff21903112dbac3b6b27a6a318e6a72b777ea` |
| `editorial/cover-design.md` | `editorial/cover-oil-design.md` | `01b64774814b41f8abeb0051fbb6b9f510d0b054e983d4cb19678b34c9591b83` |
| `images/cover.svg (background link adapted)` | `images/cover-oil.svg` | `56e863231c793a87966a9aa4f4cb6d352e67c9016b84821c85b7a14bf8487ea7` |
