# 项目辅助工具

## 保存有明确依据的工作稿修订

`apply-markdown-revision.py` 读取 raw 中显式的 JSON 修订计划，核验工作稿、
规范页图和替换材料的真实 SHA-256，按指定原读、采用读法和出现次数修改，
或应用助手已对照页图写出的整段替换文件。它不识别图片、不猜字、不选择出版范围。
计划的 `schema_version` 为 1，必须有非空的 `revision_id`、`scope`、`prompt` 和 `operations`；默认方法为 `assistant-native-multimodal`，每项操作登记 `book_id`、`path`、`expected_sha256`、
`evidence_pages`、`finding_ids`、`reason`，以及 `edits` 或带哈希的 `replacement`。
局部核录的节号、页域和未确认字形通过 `transcription_scope` 显式记录。

文字勘误显式设 `method="existing-markdown-context"`，只允许逐项 `edits`，不用整稿
`replacement` 或页图证据。每项操作的 `text_evidence` 保存当前 raw 工作稿的 `id`、
`path`、真实 `sha256` 和原样 `quote`；每个改字须有 `reason` 和对应的 `evidence_ids`。
工具核验引用与哈希，保存受改工作稿的证据快照，将决定记为文字修订。
文内依据的编辑判断仍由助手完成，文字检查不登记为影像校勘。

```powershell
uv --cache-dir data/cache/uv run --no-sync python tools/apply-markdown-revision.py --manifest data/raw/<source-set-id>/manifest.json --plan data/raw/<source-set-id>/editorial.<work-id>/revision-plan.json --check
```

先用 `--check` 做只读预检；去掉该选项才应用修订。工具在改写前保留同目录
`*.<revision-id>.original.md`，保存 raw 编辑差异与决定、更新唯一清单的当前哈希，
并保留历史清单。记录所需字段、文本匹配次数或任一证据哈希不符时，在写入前拒绝执行。
books 快照、已接受 XHTML 和 EPUB 不随之更新；旧出版计划明确标为工作输入已变化，
其旧哈希和行域保留，后续须另做出版提案。磁盘写入中断时用保留快照恢复，
不要把该辅助工具视为跨文件事务或发行验收。

## 为字形核对准备局部图片

`crop-source-image.ps1` 使用现有 Windows System.Drawing 裁切并放大页图，不做文字识别。
坐标以整页左上角为原点，单位为像素；裁切矩形必须在页图内，放大倍率为 1–4。
输出 PNG 及同名 `.json`，保存整页尺寸、矩形、倍率与输入/输出真实 SHA-256，拒绝覆盖已有图片。

```powershell
.\tools\crop-source-image.ps1 -Source data/raw/<source-set-id>/unpacked/page-0001.jpg -Output data/cache/inspection.png -X 100 -Y 200 -Width 400 -Height 300 -Scale 2
```

助手直接查看整页和局部图定读。保留所用图片及参数，并在唯一 raw 清单中登记其整页来源；
字典提供候选字义，不能代替原页证明具体字形或段落确实存在。

## 恢复 raw 项目材料

`restore-raw-materials.py` 用于恢复此前从 raw 移入 books 的完整 Markdown 和过程记录。
它读取唯一清单的作品关系，将 `books/<id>/md/` 复制回 `md.<work-id>/`，
将 `editorial/` 复制到 `editorial.<work-id>/`；逐文件核验 SHA-256，拒绝覆盖不同的 raw 工作稿。
随后更新工作目录、出版计划和快照关联，保留原件、books 文件与历史运行/接受记录。
这是恢复工具；日常在 raw 整理，确认成品后由出版命令复制快照，不反复用它覆盖工作成果。

```powershell
uv --cache-dir data/cache/uv run --no-sync python tools/restore-raw-materials.py --manifest data/raw/yan-fu-quanji-vol-06-2014/manifest.json
```

## 将工作记录归回 raw

整理过程中使用 `archive-working-editorial.py` 清理 books 中误放的待复核记录副本。
它只处理工作说明、复核状态、文字检查、待复核编辑决定及候选摘要五类文件；先验证 raw 的
当前文件或历史快照保留同一字节，再移除 books 副本，更新当前和历史报告位置。
已确认转换的映射/接受记录、选定封面的设计/提示词和出版源码继续保留在 books。

```powershell
uv --cache-dir data/cache/uv run --no-sync python tools/archive-working-editorial.py --manifest data/raw/yan-fu-quanji-vol-06-2014/manifest.json
```

## 封面编排工具

`build-cover.ps1` 将已有的 2:3 原创画编排为本项目的中文封面，保留画稿原字节。
它使用 Windows GDI+ 的中文字体轮廓、Node.js 和 `sharp` 完成尺寸统一、SVG 编译及预览渲染；
没有图片识别或模型调用。它是独立的封面辅助工具；正文转换、候选构建与检查由 Python CLI 负责。

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
