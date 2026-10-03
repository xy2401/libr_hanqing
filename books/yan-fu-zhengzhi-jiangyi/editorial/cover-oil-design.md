# 《政治講義》封面设计记录

设计日期：2026-10-03。书籍 ID：`yan-fu-zhengzhi-jiangyi`。封面阶段：设计完成、已关联出版源码；全书仍为 draft。

晚清议事讲堂：以空座、案卷与窗光表现政治思想和公共讨论。墨绿与暖赭色为主色。
这是作品主题的象征性场景，不是具体历史建筑、书页或器物的复原证据；画中书页的笔触不用于转录。

## 生成与排版

- 画稿由助手内置 `image_gen.imagegen` 工具生成，模式为 built-in；不是扫描底本封面。
- 模型具体标识与随机种子未由工具返回，保持未知；透明背景为 false。
- 最终提交的完整生成提示词保存在 [cover-prompt.txt](cover-prompt.txt)。
- 原画 1024×1536，原字节保存于 `images/cover.source.png`；机械缩放至 1400×2100，未裁切主体。
- 编排用 Windows Microsoft YaHei（微软雅黑）Bold。发行 SVG 中仅保留字形轮廓，不嵌入字体文件。
- 标题区：x=0、y=1700、宽 1400、高 320；书名与作者居中，白字黑底。
- 书名字形高 80px、顶端 y=1770；“嚴復”字形高 40px、顶端 y=1910；两行字形间距 60px。
- 汉字排版步进为字号加 5px；可编辑 SVG 逐字保存 x 坐标，字号按实际字形高度计算。
- JPEG 底画和预览由 Node.js `sharp` 编译，质量 90；发行 SVG 嵌入 JPEG，文字转为轮廓。
- 可编辑源码为 `images/cover.svg`，带字完整预览为 `images/cover.preview.jpg`；OPF 的 `cover-image` 指向 `src/epub/images/cover.svg`。

## 规范范围

参考 [Standard Ebooks 官方封面规范](https://github.com/standardebooks/manual/blob/master/10-art-and-images.rst)
的画布、油画风格、黑色标题区、字形高度和素材/源码/发行文件分工。中文字体属于本项目的中文 profile。
官方规则排除 AI 生成封面画；本项目按用户的生图要求采用 AI 原创画，不宣称严格符合官方规范，
不使用官方品牌标识，不认定这些生成画已获官方公有领域审查。

文件尺寸、SVG 自包含性和 OPF 引用须实际检查，封面设计不代表正文校勘、EPUBCheck 或阅读器验收完成。

## 本次验证

已检查两种 JPEG 均为 1400×2100；底画小于 1.5MB。源画与内置生图工具输出逐字节相同，
发行 SVG 中的 JPEG 与底画逐字节相同；发行文字均为路径，图片没有外部引用。
重新渲染当前发行 SVG 所得预览与保存的预览逐字节一致。
已查看完整封面及 240×360 缩略图，核对书名与作者字形、主体和标题区的遮挡关系。
OPF 的唯一 `cover-image` 引用有效，书籍状态仍为 draft。

本次编译环境：Node.js v24.19.0、sharp 0.35.4、Windows GDI+；这些工具只编排和渲染封面。
项目 19 项单元测试通过，`uv build` 成功；Python 发行包继续排除书籍与 raw 数据。
本轮未生成最终 EPUB，未执行 EPUBCheck 或阅读器验收。

## 文件记录

下列路径相对本书目录。源画在复制到仓库时核对原字节，生成提示词另行保存。

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `images/cover.source.png` | 2,766,258 | `eb1bf4889af47b70fa15d79d4b4c8e071230fcb3bcea14cb49e0886d181a851d` |
| `images/cover.jpg` | 595,371 | `c42dda74def461959b5f256096b5dd71aabfc05eaf1002932e2f0db6b1a1c258` |
| `images/cover.svg` | 706 | `a2faf1752bfbd48573178a009c583a41998690d625906a68605e9d2d618a0a0a` |
| `images/cover.preview.jpg` | 516,283 | `c8df001bb1d728325ef3cfece05f79fde59b635895905f167c65b32822d03a28` |
| `src/epub/images/cover.svg` | 806,161 | `d45259f1f6d4eca5317f23f45626fdab79d653316ea3e8313842f14d1a6008d2` |
| `editorial/cover-prompt.txt` | 1,562 | `a92c17b41a56f2ff04bab8fa991d92d9d22ee8b4518232a9bc0877934f569b15` |
