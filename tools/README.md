# 项目辅助工具

## PDF 接收与无损解包

`hanqing intake-pdfs --plan <项目相对路径.json>` 使用 `src/hanqing/ingest.py` 的常规处理器。
计划必须显式指定各 PDF 与扫描集关系，不从标题自动生成出版书目：

```json
{
  "schema_version": 1,
  "files": [
    {
      "source_set_id": "example-source-set",
      "source_path": "data/inbox/example.pdf",
      "source_sha256": "实际文件的64位SHA-256",
      "page_count": 123
    }
  ]
}
```

处理前核验所有输入和目标冲突。原件移入 `work/<id>/original.pdf` 并再次核验，保持原始字节；
唯一 `manifest.json` 保存来源文件名、原始位置、PDF 元数据、目录、物理页序和原始流的对象关系。
新源集的 `books[]` 为空；后续明确选文和拆书后再填写，不创建成品书籍或 Markdown。

图片直接保存 pypdf 解析得到的原始编码字节，不用 `page.images`、Pillow 保存或 DPI 渲染。
JPEG/JPX 保存为 `.jpg` / `.jp2`，其他编码保存 `.bin` 与原始 PDF 字典；掩码和嵌套 Form
图片保留角色与引用。无图片页保存原始内容流及资源引用；字体和其他附加资源仍完整保留于原件。
图片的页面矩阵、裁切框和旋转记在清单；原图不擅自裁切或旋转，不承诺所有 `.bin` 能直接查看。
物理页数、图片数、整页图片数和识别覆盖分别记录。

默认每 25 页保存检查点；输出落盘并逐文件核验后才登记成功，旧清单在哈希缓存中保留。
`--check` 不写工作数据，`--resume` 核验同一原件与已存结果，只补未完成输出；已登记文件缺失或
哈希冲突时拒绝覆盖。失败记录保留完成页、失败页与错误。解包不识别文字、不调用外部识别服务。

在已有 pypdf 的 Python 运行时使用：

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
python -m hanqing intake-pdfs --plan data/cache/intake-plan.json --check
python -m hanqing intake-pdfs --plan data/cache/intake-plan.json
python -m hanqing intake-pdfs --plan data/cache/intake-plan.json --resume
python -m unittest discover -s tests -p test_ingest.py -v
```

`pyproject.toml` 的可选 `pdf` 依赖固定 pypdf 6.19.0，锁文件依据
[PyPI 发行元数据](https://pypi.org/pypi/pypdf/6.19.0/json) 登记，未为本轮下载或安装该版本。
本轮执行与定向测试复用 Codex 已有 PDF Python 运行时的 pypdf 6.10.0，实际版本保存到工作清单。
解析器原始流接口属于内部接口，升级时须重新核验字节保留；默认骨架环境缺少此可选模块时会明确报错。

## 按需渲染 PDF 页图

`hanqing render-pdf-page --manifest <work清单> --page <物理页> --dpi 300` 使用现有的
`pypdfium2` 和 Pillow 环境生成整页 PNG，只准备视读材料，不识别文字，也不自动安装依赖。
本轮实际复用 pypdfium2 5.13.0 / PDFium 153.0.7999.0，仅渲染第一卷物理页 384。
参数 `dpi` 按 PDF 画布通常的 1/72 单位换算；特殊 UserUnit 的物理尺寸换算尚未支持。

```powershell
python -m hanqing render-pdf-page --manifest data/work/<source-set-id>/manifest.json --page 1 --dpi 300
```

处理前验证原件哈希和明确物理页；输出存入源集的 `rendered/page-NNNN-300dpi.png`。
唯一清单的 `pdf_renderings[]` 保存原件路径/哈希、引擎版本、页面框、原旋转、整页视图尺寸、
额外旋转/裁切、注释绘制选项、输出尺寸和真实哈希，`files[]` 登记渲染图。
原始 `unpacked/` 与 `pdf_unpack.pages[].images` 保持原始流含义。已登记的相同配置只核验并复用；
未知文件、不同配置、修改后的图片均拒绝覆盖。范围为 72–600 分辨率单位，限制单页 3000 万像素。
本处理器不绘制交互表单字段；含表单、特殊单位及复杂混合版面的完整支持仍待实现。
没有图片的页也可能是 PDF 原生文字，须查看渲染图后判定，不能把 `images=[]` 当作空白页。

## 登记助手逐页转录稿

`hanqing record-transcriptions --input <项目内输入.json>` 保存助手已通过自身多模态能力写出的文本。
它不调用模型、识别接口或 OCR，也不由页图自动生成文字。
输入为 schema 1 的 JSON：

```json
{
  "schema_version": 1,
  "source_set_id": "example-source-set",
  "source_sha256": "原件实际SHA-256",
  "run_id": "example-p0001-p0020-v1",
  "method": "assistant-direct-multimodal",
  "assistant": "Codex",
  "model": null,
  "markdown_directory": "data/work/example-source-set/md.example-work",
  "scope": {"first_physical_page": 1, "last_physical_page": 20},
  "notes": ["待校勘工作稿；保留现代附注"],
  "pages": [{
    "image_path": "data/work/example-source-set/unpacked/page-0001.jpg",
    "image_sha256": "页图实际SHA-256",
    "visual_preparation": [],
    "transcription": {
      "source_id": "example-source-set-pdf",
      "physical_page": 1,
      "printed_page_label": "甲",
      "warnings": ["页末有续文"],
      "blocks": [{"id": "p0001-main-1", "kind": "main", "reading_order": 1,
                  "text": "助手看图录入的原文①。", "bbox": [0.1, 0.1, 0.9, 0.8],
                  "uncertainties": ["难辨字待核"]}]
    }
  }]
}
```

`transcription` 对应 `schemas/page-transcription.schema.json`；框坐标相对整页归一化，
目测框必须说明为估计值。裁切准备记录可登记图片、坐标旁录、各自哈希、整页哈希、
像素矩形、倍率与整页尺寸；当前检查来源及文件哈希，视觉和坐标判断由助手负责。
同一 run 的配置须一致，输入可以只含下一批已写出的页稿；不覆盖已登记文字。
保存 `page-NNNN.md` 和 `page-map.md`，在唯一 work 清单中保存输入/提示词/schema 哈希、
助手信息、完整结构、疑点和完成页。未知模型留空。原注号按原字符保留，不改成自动脚注编号。
页图可以是该物理页已登记的原始图片，也可以是 `pdf_renderings[]` 中来源和整页参数一致的渲染图；
登记器核验实际哈希，并为渲染图保存 `image_origin` 来源记录，不将其冒充原始扫描图片。

同一页需要更正时，提交完整修订页对象及原页图哈希，使用
`--revision-id <稳定修订ID> --revision-reason "原页核对依据"`。
更正前核验旧稿，保留 `page-NNNN.<修订ID>.original.md`、旧结构与输入历史；
工作稿的影像校勘及出版接受状态不提升，books 不随之更新。不要给初录注册命令传入已接受出版 XHTML。
`scoped-transcription-draft-complete` 仅表示声明页域内稿件已保存，不表示校勘、人工接受或成品完成。

既有逐页稿的文字推校使用同一命令的 `--revision-method existing-markdown-context`，
同时指定修订 ID 和依据。输入继承原看图转录 run 的配置与页图关联，不能将本次文字判断
冒充新的图片识别；每个受改页增加 `text_evidence[]`，每项包含当前工作稿的 `path`、真实
`sha256` 与原样 `quote`。命令核验依据，保存修订方法、引文和修改前快照。
引用受改页时，记录的 `input_snapshot` 指向实际旧字节；其他共享该页的旧试录 run 转而引用
旧稿与旧映射的实际字节，避免把新文字配上旧哈希。此前任务报告标为历史输入，修订后另行重验。

最小定向验证：`python -m unittest discover -s tests -p test_transcription.py -v`。
完整识别队列、跨文件中断自动修复和视觉页覆盖复核仍待实现。

## 核验初录任务与保存复核标记

`hanqing check-transcriptions --manifest <work清单> --task <task-id>` 使用
`transcription_audit.py` 核验明确任务：清单的 `recognition_tasks[]` 指定任务页域、方法，
`regions[]` 明确指定各区域的 `label`、`first`、`last` 与 `run_id`，不按文件名自动选稿。
区域须依次连续覆盖任务，各 run 的页域一致，逐页结果已保存且仍保持未校勘状态。
检查原件、每页图片/渲染图、Markdown、输入历史、页码映射和裁切记录的真实哈希，
核对 Markdown 与登记区块文字一致，保存 `editorial.<task-id>/transcription-report.md`。
旧报告字节与清单保留在内容哈希历史中；当前报告哈希及检查范围记在唯一清单，重复核验保留旧 audit。

```powershell
python -m hanqing check-transcriptions --manifest data/work/<source-set-id>/manifest.json --task <task-id>
python -m unittest discover -s tests -p test_transcription.py -v
python -m unittest discover -s tests -p test_pdf_render.py -v
```

报告汇总初录疑点、跨页边界和区块性质说明；标记数不等于错误数。
`initial-transcription-draft-complete` 只表示声明的任务页稿及文件覆盖检查完成，
校勘、文字/视觉完整性复核和出版接受仍分别待办，books 与候选 EPUB 不随之更新。

## 登记逐页文字校勘

`hanqing record-text-review --input <工作目录中的校勘输入.json>` 接受助手已阅读并判断的文字，
不识别图片、不自动找错。schema 1 输入在对应源集内，包含 `source_set_id`、稳定 `review_id`、
清单中已定义的 `task_id`、`method="existing-markdown-context"`、明确 `policy` 与 `pages[]`。
任务中显式 run 决定当前稿件；每页登记 `physical_page`、`markdown_path`、实际 `markdown_sha256`、
`notes[]` 和 `findings[]`。每项疑点包含全轮唯一 `id`、当前稿中原样 `quote`、`reason`，
以及 `pending-image-check`、`retained-from-text` 或 `corrected-from-text` 状态。

```powershell
python -m hanqing record-text-review --input data/work/<source-set-id>/editorial.<review-id>/input-p0001-p0012.json
```

只登记实际读过的页；分批追加同一轮，完整输入按内容哈希保留。
它核验当前页稿与引文，生成 `editorial.<review-id>/text-review.md`，唯一清单的 `text_reviews[]`
保存逐页阅读记录、汇总及报告真实哈希。修改前报告按原字节缓存，旧阅读点不能被不同判断覆盖。
同一轮全页已读且当前哈希均相符，才记 `text-reading-pass-complete-pending-image-check`；
稿件改变后旧点失效，重新阅读使用新 review ID，不能把读过旧版本算成读过新版本。

后文明确解释某个旧译名等疑点时，可追加 `resolutions[]`：`finding_id` 指向原待核项，
`status="retained-from-text"`、`reason` 说明保留依据；`evidence[]` 包含证据物理页、
`markdown_path`、`markdown_sha256` 与原样 `quote`。原逐页判断保留，报告另列后续说明；
汇总按有效的新说明计数，证据变化也会使说明失效。它不执行改字；文字修订另用上述显式修订命令。
纠正项、据文保留项和待核项的数量是记录条数，不能推断为全书实际错误数。
文字阅读、原页字形核验、出版接受与发行分别记录，不能由一轮文字阅读提升其他状态。

## 迁移旧数据目录

```powershell
uv --cache-dir data/cache/uv run --no-sync hanqing migrate-data-layout --check
uv --cache-dir data/cache/uv run --no-sync hanqing migrate-data-layout
```

将旧 `data/raw/` 迁为 `data/work/`，创建 `data/inbox/`，把包、检查报告和构建历史归入
对应的 `books/<book-id>/dist/`。预检拒绝目标冲突，迁移核验全部文件字节；保留旧清单快照和
历史报告/计划原字节，当前清单更新位置并记录旧路径映射。新打包命令不再读取或回写工作清单。
Windows 拒绝整目录移动时逐文件迁移，失败时回移；逐一核验后在
`data/cache/layout-migration/layout-complete.json` 保存迁移回执。

## 保存有明确依据的工作稿修订

`apply-markdown-revision.py` 读取 work 中显式的 JSON 修订计划，核验工作稿、
规范页图和替换材料的真实 SHA-256，按指定原读、采用读法和出现次数修改，
或应用助手已对照页图写出的整段替换文件。它不识别图片、不猜字、不选择出版范围。
计划的 `schema_version` 为 1，必须有非空的 `revision_id`、`scope`、`prompt` 和 `operations`；默认方法为 `assistant-native-multimodal`，每项操作登记 `book_id`、`path`、`expected_sha256`、
`evidence_pages`、`finding_ids`、`reason`，以及 `edits` 或带哈希的 `replacement`。
局部核录的节号、页域和未确认字形通过 `transcription_scope` 显式记录。

文字勘误显式设 `method="existing-markdown-context"`，只允许逐项 `edits`，不用整稿
`replacement` 或页图证据。每项操作的 `text_evidence` 保存当前 work 工作稿的 `id`、
`path`、真实 `sha256` 和原样 `quote`；每个改字须有 `reason` 和对应的 `evidence_ids`。
工具核验引用与哈希，保存受改工作稿的证据快照，将决定记为文字修订。
文内依据的编辑判断仍由助手完成，文字检查不登记为影像校勘。

```powershell
uv --cache-dir data/cache/uv run --no-sync python tools/apply-markdown-revision.py --manifest data/work/<source-set-id>/manifest.json --plan data/work/<source-set-id>/editorial.<work-id>/revision-plan.json --check
```

先用 `--check` 做只读预检；去掉该选项才应用修订。工具在改写前保留同目录
`*.<revision-id>.original.md`，保存 work 编辑差异与决定、更新唯一清单的当前哈希，
并保留历史清单。记录所需字段、文本匹配次数或任一证据哈希不符时，在写入前拒绝执行。
books 快照、已接受 XHTML 和 EPUB 不随之更新；旧出版计划明确标为工作输入已变化，
其旧哈希和行域保留，后续须另做出版提案。磁盘写入中断时用保留快照恢复，
不要把该辅助工具视为跨文件事务或发行验收。

## 为字形核对准备局部图片

`crop-source-image.ps1` 使用现有 Windows System.Drawing 裁切并放大页图，不做文字识别。
坐标以整页左上角为原点，单位为像素；裁切矩形必须在页图内，放大倍率为 1–4。
输出 PNG 及同名 `.json`，保存整页尺寸、矩形、倍率与输入/输出真实 SHA-256，拒绝覆盖已有图片。

```powershell
.\tools\crop-source-image.ps1 -Source data/work/<source-set-id>/unpacked/page-0001.jpg -Output data/cache/inspection.png -X 100 -Y 200 -Width 400 -Height 300 -Scale 2
```

助手直接查看整页和局部图定读。保留所用图片及参数，并在唯一 work 清单中登记其整页来源；
字典提供候选字义，不能代替原页证明具体字形或段落确实存在。

## 恢复 work 项目材料

`restore-working-materials.py` 用于恢复此前从 work 移入 books 的完整 Markdown 和过程记录。
它读取唯一清单的作品关系，将 `books/<id>/md/` 复制回 `md.<work-id>/`，
将 `editorial/` 复制到 `editorial.<work-id>/`；逐文件核验 SHA-256，拒绝覆盖不同的 work 工作稿。
随后更新工作目录、出版计划和快照关联，保留原件、books 文件与历史运行/接受记录。
这是恢复工具；日常在 work 整理，确认成品后由出版命令复制快照，不反复用它覆盖工作成果。

```powershell
uv --cache-dir data/cache/uv run --no-sync python tools/restore-working-materials.py --manifest data/work/yan-fu-quanji-vol-06-2014/manifest.json
```

## 将工作记录归回 work

整理过程中使用 `archive-working-editorial.py` 清理 books 中误放的待复核记录副本。
它只处理工作说明、复核状态、文字检查、待复核编辑决定及候选摘要五类文件；先验证 work 的
当前文件或历史快照保留同一字节，再移除 books 副本，更新当前和历史报告位置。
已确认转换的映射/接受记录、选定封面的设计/提示词和出版源码继续保留在 books。

```powershell
uv --cache-dir data/cache/uv run --no-sync python tools/archive-working-editorial.py --manifest data/work/yan-fu-quanji-vol-06-2014/manifest.json
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
