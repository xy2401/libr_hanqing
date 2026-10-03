# 《政治講義》封面设计记录

设计日期：2026-10-03。书籍 ID：`yan-fu-zhengzhi-jiangyi`。当前采用水墨主题版，全书仍为 draft。

中式长案公议、政务文书与城郭民众，表现中国语境中的公共治理和社会生活。排除国外议会、半圆议席和西式建筑。
按用户共同拟定的主题规范生成，保留宣纸色、墨色留白与右侧竖排题签。
画面是主题性艺术构图，不复原具体历史会议、人物、地理资料或底本书页。

## 生成与编排

- 画稿由助手内置 `image_gen.imagegen` 生成，模式为 built-in；最终提交的完整提示词见 [cover-prompt.txt](cover-prompt.txt)。
- 主题与制作规范见本记录，完整实际提示词独立保存。
- 工具未返回具体模型标识或随机种子，保持未知；透明背景为 false。
- 原画 1024×1536，原字节保存在 `images/cover.source.png`；机械缩放至 1400×2100，未裁切主体。
- Windows KaiTi（楷体）Regular 编排准确的繁体书名与“嚴復”；发行 SVG 将六字转为轮廓，不依赖外部字体。
- 书名竖排最大字形高 110px，步进 142px，列中心 x=1110，首格顶端 y=210；作者最大字形高 52px，步进 74px，列中心 x=950，首格顶端 y=650。
- 各列统一字号、字形在格中居中，至少 40px 画布边距；墨色文字 `#202924`，不使用黑色标题区。
- `images/cover.svg` 保留可编辑文字；`images/cover.preview.jpg` 为带字完整预览；`src/epub/images/cover.svg` 嵌入 JPEG 底画。
- OPF 唯一的 `cover-image` 指向当前发行 SVG，不引用历史备选。
- 编排环境为 Windows GDI+、Node.js v24.19.0、sharp 0.35.4，JPEG 质量 90；本轮未改变编排工具代码。

## 规范范围

参考 [Standard Ebooks 的尺寸与素材/源码/发行分工](https://github.com/standardebooks/manual/blob/master/10-art-and-images.rst)，
采用本项目自己的水墨视觉设计。AI 生成画与水墨风格属于已说明的项目差异，不宣称严格符合官方封面规范。
封面改版不改变正文、文字底本或校勘状态，本轮未生成最终 EPUB，未执行 EPUBCheck 或阅读器验收。

## 本次验证

已查看两张完整封面和 240×360 缩略图，核对主题构图、书名、作者与留白关系。
原画与内置生图输出逐字节一致；两种 JPEG 均为 1400×2100，底画小于 1.5MB。
发行 SVG 嵌入底画，六个汉字均为轮廓；重新渲染所得预览与保存的预览逐字节一致。
OPF 仅引用当前主题版，书籍状态保持 draft。六项当前文件哈希与八项油画版文件哈希均核对通过。
`uv build` 成功；本轮未修改代码，不重复运行此前已通过的 19 项书目/骨架单元测试。

## 当前文件

路径相对本书目录。

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `images/cover.source.png` | 3,098,691 | `213300918e0173c19e93647fe2d5bbbed8571513f34009dd7717a4c96af69de7` |
| `images/cover.jpg` | 570,933 | `0439733f01851e8b05469248bd0ab5c59009796ca4745fccaa691c985f9385dc` |
| `images/cover.svg` | 667 | `57b73627b1e6c2104728419a68b8d883a3a4909b84c600b8b0d31a981ec5a476` |
| `images/cover.preview.jpg` | 582,600 | `785f8fce4718211e3fd2374836a547934354f23f9872ed317d851b9f342968d1` |
| `src/epub/images/cover.svg` | 793,430 | `d7db4606c792c577cbf4abffb0db9e958c58d69a28de5675bfac15f81081247b` |
| `editorial/cover-prompt.txt` | 2,329 | `9ac24b44f9ac8c2825c8fcfd68de54d344cd696a079dffa1829de04a96f643ee` |

## 保留范围

按用户要求只保留最新版与最早油画版，保留版本的源画、源码、预览、发行图、实际提示词和设计记录继续保存。中间水墨版本、叠字版、提示词草案副本及封面处理缓存已清理。

## 油画版备份

[油画版预览](../images/cover-oil.preview.jpg)。油画原画、排版和制作记录继续按原字节保留，
`cover-oil.svg` 使用独立的油画底图链接；原记录中的无前缀路径按本节映射读取。
全部备份都保存在出版 `src/` 外，不作为新 EPUB 的候选 manifest 项。

| 改版前路径 | 当前备份路径 | SHA-256 |
| --- | --- | --- |
| `images/cover.source.png` | `images/cover-oil.source.png` | `eb1bf4889af47b70fa15d79d4b4c8e071230fcb3bcea14cb49e0886d181a851d` |
| `images/cover.jpg` | `images/cover-oil.jpg` | `c42dda74def461959b5f256096b5dd71aabfc05eaf1002932e2f0db6b1a1c258` |
| `images/cover.svg` | `images/cover-oil.original.svg` | `a2faf1752bfbd48573178a009c583a41998690d625906a68605e9d2d618a0a0a` |
| `images/cover.preview.jpg` | `images/cover-oil.preview.jpg` | `c8df001bb1d728325ef3cfece05f79fde59b635895905f167c65b32822d03a28` |
| `src/epub/images/cover.svg` | `images/cover-oil.epub.svg` | `d45259f1f6d4eca5317f23f45626fdab79d653316ea3e8313842f14d1a6008d2` |
| `editorial/cover-prompt.txt` | `editorial/cover-oil-prompt.txt` | `a92c17b41a56f2ff04bab8fa991d92d9d22ee8b4518232a9bc0877934f569b15` |
| `editorial/cover-design.md` | `editorial/cover-oil-design.md` | `a1003b9d350f1465975a7bd77c0f1af1e5475b442e61d59ead5b1458584c931c` |
| `images/cover.svg (background link adapted)` | `images/cover-oil.svg` | `fd68b816ce9a6598d4f6ef5a43de3275665aeddeefed8d77bad276bde562a40d` |
