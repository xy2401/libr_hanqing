# 封面编排工具

`build-cover.ps1` 将已有的 2:3 原创画编排为本项目的中文封面，保留画稿原字节。
它使用 Windows GDI+ 的中文字体轮廓、Node.js 和 `sharp` 完成尺寸统一、SVG 编译及预览渲染；
没有图片识别或模型调用。它是独立的开发辅助工具，不是尚未实现的 EPUB runner。

要求 Windows、PowerShell、楷体（KaiTi），以及能加载 `sharp` 的 Node.js。
默认 `-Profile ink` 使用楷体竖排、留白与墨色文字；`-Profile oil` 使用 Microsoft YaHei
粗体横排和黑色标题区，支持恢复原油画编排。可用 `-FontFamilyName` 显式选择支持繁体的字体。
工具依赖不加入 Python 包。其他操作系统仍可直接使用已编译的封面 SVG；源 SVG 可在支持
相同字体的矢量编辑器中编辑，再将文字转为轮廓、嵌入底画后导出发行 SVG。

首次编排前，把助手内置生图工具生成的未改动画放在目标书的 `images/cover.source.png`。
书名和作者取自该书的 `book.toml`，例如：

```powershell
.\tools\build-cover.ps1 -BookDirectory books/yan-fu-zhengzhi-jiangyi -Title '政治講義' -Author '嚴復'
```

Node.js 未在 PATH 中时使用 `-NodeExecutable` 指定可执行文件，`sharp` 不在默认模块查找路径
时用 `-SharpModule` 指定该包的完整路径。未提供这两个参数时使用标准 Node.js 安装环境。

输出 `images/cover.jpg`、`images/cover.svg`、`images/cover.preview.jpg` 和
`src/epub/images/cover.svg`。工具默认拒绝已有输出，避免覆盖已经接受的设计；
调整封面时在被忽略的缓存目录中产生提案，选定并核验新版后清理临时文件；长期只保留最新版与油画版。
本次备份使用 `images/cover-oil.*` 和 `editorial/cover-oil-*`，旧版 SVG 的背景引用已另存
为可用的油画引用；`cover-oil.original.svg` 保留更改引用前的原字节。
工具不修改 OPF，采用封面后须显式登记 `cover-image` 并检查引用。

该工具支持当前两本书所用的竖排单列标题与油画版的横排单行标题；它不提供任意长度标题、多列排版或所有语言的
字距处理。输入画比例不符、文字过宽和底画超过 1.5MB 时会报错，不擅自裁掉图像主体。

## 从可编辑 SVG 编译文字

`compile-cover-svg.ps1` 从已经编辑的 `images/cover.svg` 生成自包含的发行 SVG 和预览，
用于题签等可编辑文字的编译，不重画底图。水墨书页中的双语词和批注由内置生图融入画面，
不使用该工具贴字替代。可编辑文字使用 Windows 本地字体，发行图中转为轮廓；
相对目录内的 JPEG 底画嵌入 SVG。正文生成和图片文字识别都不在该工具职责内。

```powershell
.\tools\compile-cover-svg.ps1 -SourceSvg books/yan-fu-yingwen-hangu/images/cover.svg -OutputSvg data/cache/cover-candidate.svg -PreviewPath data/cache/cover-candidate.jpg
```

与首次编排工具一样，可用 `-NodeExecutable` 和 `-SharpModule` 指定运行环境，默认拒绝已有输出。
确认候选后，更新书籍的 `src/epub/images/cover.svg` 和 `images/cover.preview.jpg`，核对保留版本的哈希并清理缓存候选。
支持平铺的 `title`、`desc`、`image`、`rect`、`path` 和纯 `text` 元素；文字可有单一或逐字
x/y 坐标，以及六参数仿射矩阵。矩阵在编译时应用于轮廓，发行图不保留 transform；
它不是任意 SVG/CSS 的通用转换器。字体须已在本地安装，当前汉文题签使用 KaiTi。
