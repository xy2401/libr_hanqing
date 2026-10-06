# 架构设计

## 身份与分类

区分三层身份：`work_id` 是作品，如 `lunyu`；`book.id` 是准备出版的数字版本，
如 `kong-zi-lunyu`；work 清单中的 `source_id` 是登记的影像底本文件，如 `scan-001`。
其 `source_sha256` 标识原始字节。作品名称和作者显示名可修改，稳定 ID 不跟随分类变化。

书籍 ID 使用作者或系列 ID 前缀，如 `yan-fu-zhengzhi-jiangyi`；现代扫描版年份属于来源信息，
不作为古籍数字版名称。用户要求迁移 ID 时，目录、书目、OPF 标识符和清单当前引用一起更新，
work 清单保留旧 ID 和迁移记录。

`source_set_id` 标识本地原始扫描集，存储于 `data/work/<source-set-id>/`。
扫描集和数字版本分开命名，二者无需一一对应：同一底本文件可以包含多本独立作品，
由扫描集清单的 `books[]` 显式定义，各自使用 `books/<book-id>/` 的出版源码，
共享同一原始文件及其解包。影像底本 ID、路径、哈希和书籍关系只在 work 清单中登记。

同书不同底本独立建书。校改参考其他来源时，在 work 清单中明确主底本与参考关系，
并按校勘政策使用。多册文件的卷册顺序需要显式记录；后续导入器不能按文件名猜测，
也不能自动拼接不同底本的正文。首个端到端样例先以单一主文件走通流程。

作者与系列是 `book.toml` 的多值字段，不决定存储位置。贡献者支持角色
`author`、`editor`、`commentator`、`annotator`、`translator`、`compiler`；未署名可以留空。
古籍刊印注疏作者使用 `commentator`，书上手写批注者使用 `annotator`，OPF 映射对应
[MARC 角色](https://www.loc.gov/marc/relators/relatermprint1.html)。
系列使用自己的 ID 和可选整数次序。初期全部从 TOML 生成视图，不维护另一个数据库；
书量变大后可增加可重建的 SQLite 索引。

## 数据归属

| 区域 | 保存内容 | Git | 是否可重建 |
| --- | --- | --- | --- |
| `data/inbox/` | 新放入的 PDF/EPUB/影像原件，等待开始整理 | 忽略 | 原件需另行备份 |
| `data/work/<source-set-id>/` | 原始影像、共享解包、完整 Markdown 工作稿、来源与过程记录和待接受提案 | 忽略 | 原件需备份；确认成品后仍保留项目材料 |
| `data/cache/` | 可重建的共享工具缓存 | 忽略 | 是 |
| `books/<id>/book.toml` | 独立古籍书目、数字版本与书目标记 | 提交 | 由人工维护 |
| `books/<id>/md/` | 确认的文字底本、页码表与原稿快照 | 提交 | 固定 Git 快照，不自动跟随 work 改动；不打包 |
| `books/<id>/src/` | 已接受的 XHTML、导航、OPF、样式与发行图片 | 提交 | 正文为权威源 |
| `books/<id>/editorial/` | 明确接受的 Markdown 至 XHTML 映射/转换记录、选定封面的固定设计记录、最终整理说明 | 提交 | 逐项确认的固定记录；不存待复核工作档案 |
| `books/<id>/dist/` | 候选/发行包、构建记录、官方检查报告与检查摘要 | 忽略 | 从本书固定 src 构建，不依赖 work |

每个原始扫描集的本地数据统一保存在 `data/work/<source-set-id>/`，整个目录被 Git 忽略。
原始底本直接命名为 `original.pdf` 或 `original.epub`；整本原始解包放 `unpacked/`，
保留页图、附带元数据和封面候选原图。分作品的 Markdown 工作稿保存在 `md.<work-id>/`，
过程记录保存在 `editorial.<work-id>/`；现代附加材料、疑点和原始来源信息完整保留。
`editorial` 是编辑与制作记录：工作中的校勘说明、复核状态、文字勘误和编辑决定只在 work 维护；打包检查属于 books 的 dist。books 中的同名目录保存明确接受的固定记录，避免两处工作档案同时演化。
`books/<book-id>/md/` 是纳入 Git 的文字底本快照，包括转录稿、`page-map.md` 与原稿快照，
不保存图片或重复解包页图，也不收录到 EPUB。项目整理完成后逐项确认并复制成品进入 books，
不得为整理 Git 或清理出版信息而移走 work 的项目材料。两处文件不自动双向同步。

改写过的原始 Markdown 在同目录保存为 `*.original.md`。`manifest.json` 是本地数据
唯一清单，当前使用 `schema_version = 3`、`path_base = "project"`，顶层 `source_set_id` 标识扫描集，
`source_path` 为原件相对项目根目录的路径。原有文件映射全部并入 `files[]`：
`path` 为当前路径，`original_path` 保留原导入路径，`sha256` 和 `original_sha256`
分别记录当前与原始字节哈希；改写稿的 `original_snapshot` 指向保留原字节的快照。
再次修改已有快照的稿件时，不覆盖最初快照；另存 `*.before-text-review.original.md`
等阶段快照，在同一文件记录的 `revisions[]` 中保留修改前后哈希及快照路径。
所有当前路径字段统一相对项目根目录，包含 `source_path`、文件 `path`、`original_snapshot`、
各书的章节/页码表/目录/封面候选与出版取舍引用，避免使用 `../` 跨 work 和 books。
核验重复页图与规范 `unpacked/` 页图的 SHA-256 一致，且规范文件仍存在后，可以删除
重复副本；其来源记录保留在 `files[]`，`deduplicated_from` 保留旧副本路径，
`path` 指向保留的同字节规范页图。

`books[]` 定义该底本中的一本或多本独立作品，包含 `book_id`、`work_id`、
`book_directory`、`markdown_directory`、显式 `markdown_order`、`page_map` 和页域。
`markdown_directory`、`markdown_order` 与 `page_map` 指向 work 工作稿；
`markdown_snapshot_directory` 指向 books Git 快照，`editorial_directory` 指向 work 过程记录。
`files[].book_snapshot` 保存对应快照的路径、真实哈希和记录时间，历史接受记录继续指向当时的快照。
所有目录均相对项目根目录。例如：

| `book_id` | `work_id` | `markdown_directory` |
| --- | --- | --- |
| `yan-fu-zhengzhi-jiangyi` | `zhengzhi-jiangyi` | `data/work/yan-fu-quanji-vol-06-2014/md.zhengzhi-jiangyi` |
| `yan-fu-yingwen-hangu` | `yingwen-hangu` | `data/work/yan-fu-quanji-vol-06-2014/md.yingwen-hangu` |

两项的 `cover_candidate` 指向该扫描集 `data/work/yan-fu-quanji-vol-06-2014/unpacked/`
中的两张候选原图，尚未作为出版图片接受。

两项共享 `data/work/yan-fu-quanji-vol-06-2014/original.pdf` 与 `unpacked/`，
来源字段及与各书的关系全部保存在共享 work 清单中，不写入 `book.toml`，
不在各书的 `editorial/` 复制导入清单；使用范围与章顺序由对应清单项明确登记。
不将整册扫描集作为唯一出版书籍。
`source_id` 和 `run_id` 只保存在 work 清单中，不决定目录层级。
目录按实际内容建立，不预设编号或包装层。
处理器不得修改原件；更新已有中间稿前先保存旧内容及其哈希，在清单中保留历史关系，
避免丢失输入和 AI 原稿。

识别 JSONL 和 AI Markdown 是待复核中间稿。人工接受后的正文只在 XHTML 中编辑，
避免 JSON、Markdown 和 XHTML 三份正文同时演化。再次识别或结构化只生成提案与差异，
由编辑决定是否接受；处理器不得重写已经接受的 XHTML。目录整理不能作为完成校勘或
EPUB 转换的证据；文字勘误与影像逐字校勘分别记录。现有两本书已明确接受本轮正文结构与
注释取舍并生成候选 EPUB，但影像校勘、页覆盖、未决疑点和完整发行验收仍未完成。

`books/` 面向古籍独立出版内容，`edition` 描述本项目数字整理版。
现代扫描版的出版社、ISBN、年份、主编/点校者、版权页与共享 PDF 的说明只保存在 work：
扫描集的 `bibliography` 保存全卷出版信息，各作品的 `source_publication` 保存对应贡献、
底本说明和导入记录。古籍出版书目只保留作品与数字版本信息、原作作者/贡献者；现代扫描版
系列和卷次不自动作为古籍电子书系列元数据。`publication_policy` 明确排除现代附加材料；
现代说明与古籍原序合并在同一稿件时必须逐段复核，不丢弃原始影像或 Markdown 底本。
`md/` 作为非出版底本可保留现代附加材料原文，便于核对，不能直接加入成品正文。

发行只从 `books/<book-id>/src/` 收集文件，排除整个 `md/`、Markdown、`editorial/` 与 work，
禁止递归打包整个书籍目录或在 OPF 引用底本。`config/pipeline.toml` 声明这一边界，
候选 EPUB 构建已实现；Python wheel/sdist 由 `MANIFEST.in` 排除 `books/` 和 `data/`。

## 底本登记

`init-book` 仅生成出版书目与源码骨架。`book.toml` 的元数据模型不包含影像来源字段，
校验器拒绝旧 `sources`、`primary_source_id`，所有书目标记均不要求在书目中登记来源。
书目标记不代替实际校勘与发行验收。

底本类型、路径、真实 SHA-256、下载地址、现代出版信息和底本说明统一登记在
`data/work/<source-set-id>/manifest.json`。当前清单使用以下顶层字段：

- `source_id`：影像底本 ID。
- `source_kind`：`pdf` 或 `epub`。
- `source_path`：原件相对项目根目录的 POSIX 路径。
- `source_sha256`：实际原件的 64 位十六进制 SHA-256。
- `books[]`：通过 `book_id`、书籍目录与使用范围定义该底本对应的出版书籍。

书目检查不读取 work 清单，也不要求原件存在；`ingest` 将负责实际文件、类型、大小和
SHA-256 校验。哈希未知时如实标为未验证，不使用占位值。可以在 PowerShell
中用 `Get-FileHash -Algorithm SHA256 -LiteralPath <文件路径>` 计算真实哈希。

## 阶段和可恢复运行

| 阶段 | 职责 | 接受条件 |
| --- | --- | --- |
| `ingest` | 登记本地输入，不修改原件 | 来源身份、文件类型和哈希验证 |
| `prepare` | PDF 原始图片流提取或页面渲染；EPUB 解包并区分文本/影像/混合内容 | 页数与页序可核对，解包路径合法 |
| `recognize` | 当前助手用自身多模态能力逐页或区域看图，转写 Markdown | 来源可回溯，疑点显式保留 |
| `assemble` | 识别稿转换为卷/章/注释的 XHTML 提案 | 阅读顺序明确，提案可对照底本 |
| `proofread` | 人工对照、接受提案并校勘 XHTML | 无未处理疑点，所有应处理页有覆盖说明 |
| `build` | 从固定出版源码打包候选 EPUB | manifest、spine 与构建输入固定 |
| `validate` | 校勘证据、结构、链接、EPUBCheck 和阅读器检查 | 所有必需检查通过 |
| `release` | 保存已经验收的相同产物字节 | 哈希一致，附发行清单 |

识别阶段由当前助手直接查看原始页图完成，禁止调用外部模型/识别 API、OCR 服务或
本地 OCR 引擎，也不设置此类兜底。Python 工具负责解包、PDF 渲染、图片裁切/旋转、
文件与清单管理、校验和构建；查看或处理图像的工具不执行文字识别。
已有文本 EPUB 可以直接提取文本与注释。

这是完整工作流的阶段契约；当前已实现显式计划的 PDF 接收和原始编码流提取、正文提案/明确接受、
候选打包和结构/EPUBCheck 检查，以及助手逐页稿的本地登记、明确单页的 PDF 渲染和任务页序/哈希检查。复杂页图准备、安全 EPUB 解包与完整识别管理仍待接入。
`plan` 只展示契约与实现范围。
识别不由 Python runner 调用模型。Markdown 工作稿与其他本地处理结果按实际内容保存在
`data/work/<source-set-id>/`，books 保留确认快照与接受的出版材料；各次运行以清单中的
`run_id` 和内容哈希追踪。复制进入 books 不表示 work 项目可以删除，也不自动提升验收状态。
每次运行记录应保存：输入文件和页图哈希、底本 ID、图像处理参数、程序版本、
识别方式、已知助手/模型信息、提示词版本、schema 版本、完成页与错误。
未知模型信息留空，不根据文件时间或内容猜测。

缓存键由输入内容及上述有效配置共同决定；提示词或模型变更不能复用旧识别结果。
逐页结果落盘后才标记成功，恢复时仅补未完成页，显式记录失败页；
更新识别稿前通过同目录的原稿文件或内容缓存保留旧版本，在清单中登记对应哈希与处理记录。
密钥只从环境或忽略的本地配置读取，
不写入书目、运行记录或模型日志。

EPUB 解包器需要拒绝路径穿越、绝对路径与符号链接，并限制文件数量和解压大小。
PDF 页面先保留整页，再记录裁切、旋转和区域坐标关系；原书双页、版心、页码、正文与
夹注必须能回溯，不能用只剩文字的 OCR 结果替代来源证据。

## 中间数据与校勘证据

`providers/base.py` 保留页面输入/结果类型及未接入的协议声明，不作为外部识别服务的实现入口。
页面结构结果契约见
`schemas/page-transcription.schema.json`。每个结构结果对应一个物理页，区分文件中的
`physical_page` 与原书页码 `printed_page_label`；每个区块有稳定 ID、类型、阅读次序、
文字、相对于整页的坐标和疑点。schema 校验后还要检查坐标顺序、区块 ID 唯一性和页覆盖。
`record-transcriptions` 接收包含这些逐页对象的显式 JSON 输入，检查每页区块 ID 唯一、
阅读序号、归一化坐标、授权页域声明和来源哈希；`recognition_runs[]` 保存完整区块与疑点。
逐页 Markdown 落盘后才记成功，可补存同一配置下的未完成页；已有页冲突默认拒绝。
显式修订只作用于待校勘工作稿，保留原稿、原结构结果与理由。输入校验失败时不写页稿；
跨文件中断的自动恢复及失败队列仍待实现。页数保存齐全只表示本批初录齐全，不能证明视觉内容无遗漏。
不要把模型自报的置信度当成校勘通过条件。

`editorial/source-map.jsonl` 保存 Markdown 文字底本段落与 XHTML 的对应关系，不复制正文。
当前每条记录包含 `markdown_path`、`markdown_sha256`、`markdown_lines`（含两端的行域）、
`xhtml_path`、`element_id` 和元素类型，路径相对项目根目录。
影像底本 ID、文件哈希、页图坐标及影像至 Markdown 的对应关系只在 work 清单中保存。
文字底本可通过其页码表与 work 清单回溯影像；一页可对应多个段落，一段正文也可跨页。

work 的 `editorial.<work-id>/decisions.jsonl` 保存工作中的编辑决定：疑点 ID、来源位置、原读、采用读法、理由、
编辑者与时间；句读、繁简、异体字和他本校改分别记录。正文缺字不能凭记忆补齐；
保留缺字符号或字形图片等方案由书籍校勘政策决定。

已有文字底本时，未明确要求影像核对的“校勘／勘误”默认执行文字检查；疑点先记录为待核，
不自行启动看图转录、逐页影像比对或全书重新识别。

已有影像证据的工作稿修订可用 `tools/apply-markdown-revision.py`：显式计划限定原读、采用读法、
页域和输入哈希，助手对照页图转写，工具仅负责保存快照、差异、编辑决定和清单历史。
文字勘误使用同一工具的 `existing-markdown-context` 方法，限定逐项修改，登记有真实哈希的
文内引文及每个改字的依据；不要求页图，也不将文字判断记为影像识别。具体计划格式见 `tools/README.md`。
修订只落入 work；旧出版计划的哈希与行域保留，并标为工作输入已变化。books 底本快照、
已接受 XHTML 和候选 EPUB 须经新的差异提案分别确认，不能自动覆盖。局部段落或例词偏离
也不能推定整篇错误或整书已通过校勘；扩大影像核录范围遵守执行许可约定。

基于现有 Markdown 的文字勘误单独记录于 work 的 `editorial.<work-id>/text-review*.md`，明确文本检查范围、
改字依据和未决疑点。`review.toml` 的 `text_review` 子表记录该轮检查及稿件摘要，
不改变顶层人工复核状态；work 清单中的 `text_reviews[]` 记录本地处理历史。
文字勘误不能证明转录忠实、正文无遗漏或页图覆盖完整，也不能作为 `proofread` 的验收。

已有结构化逐页稿使用 `record-transcriptions --revision-method existing-markdown-context` 保存
有引文及实际哈希的文字修订；原看图 run 的配置与来源不改写，本轮方法记录在修订项。
共享同一路径的旧试录记录转而指向修改前快照与旧映射，保持历史字节和哈希一致。
`record-text-review` 将实际逐段阅读、疑点和判断登记为独立阅读点，绑定当前任务指定的 run 和页稿哈希。
后文支持的保留说明追加到 `resolutions[]`，保留先前疑点记录，证据字节变化后不能沿用说明。
它只检查提供的记录及字节，不判断正文、不覆盖页稿；完整文字阅读状态不会改动影像校勘或出版状态。

work 的 `editorial.<work-id>/review.toml` 初始为 `pending`，在首次制作提案时初始化，books 不创建工作复核档案。
未来接受复核时须记录复核者、时间、已处理页/排除页、
出版源码摘要及未处理疑点数；正文变更后旧复核证据失效。`book.toml` 中的
`draft / recognized / proofread / ready / released` 仅为书目标记，当前可人工填写，
不证明已经通过检查。发行门禁必须检查实际复核证据与校验报告。

## Python 模块边界与推进顺序

当前 Python 核心使用标准库：CLI、元数据、分类、初始化、阶段契约、页面数据类型、资源模板、
出版提案/接受、候选打包与结构校验。转换通过子进程调用本地 Pandoc，官方校验通过 Java
调用本地 EPUBCheck；这些依赖与扫描处理隔离，不执行图片识别。
PDF 接收与编码流提取通过可选本地 pypdf 依赖实现；明确单页渲染使用现有 pypdfium2 / Pillow 环境。图片识别使用助手自身多模态能力，
不实现模型供应商 SDK、外部识别接口或本地 OCR 后端，也不把 SE 工具集作为启动骨架的强制依赖。

已实现的出版路径：

- `publication/markdown.py`：明确行域与现代注释排除、本地 Pandoc 转换、语言与原注语义、段落映射。
- `publication/assemble.py`：读取唯一 work 清单中的 `publication_plan`，核验真实底本哈希，
  从声明的 work 工作稿生成 `proposal.<book>/`；具体材料完成整理并明确接受后复制 Git 底本快照，
  段落映射指向此固定快照，保留 work 工作稿、此前源码与接受记录。已有不同快照拒绝自动覆盖。
- `publication/package.py`：固定 `books/<book>/src/` 输入，合法 OCF 候选打包、本地 EPUBCheck。
- `publication/evidence.py`：核对候选、官方报告与当前出版源码哈希，验证段落锚点和文字底本哈希，
  只读取 books 中接受的固定复核记录，在本书 `dist/` 保存同名 `.validation.json` 并归档旧字节；仅在相同候选字节下保留此前阅读器/页覆盖记录。
- `validators/publication.py`：资源、全书 ID、片段链接、目录目标与 spine 检查。
- `workspace.py`：将旧 `data/raw/` 迁为 `data/work/`，创建待处理原件的 `data/inbox/`，核验所有迁移字节及目标冲突；把已有包和检查记录移到各书 `dist/`。
- `ingest.py`：显式计划限定 inbox PDF 路径、源集 ID、原件哈希和物理页数；全部预检后接收原件，
  保存 schema 3 清单。直接读取原始编码图片流而不调用 `page.images` / 图片保存重编码，保留 PDF 字典、
  对象号、矩阵、裁切框和旋转。无图片页另存原始内容流及资源引用；所有字体及附加资源仍完整保留在 PDF 原件。
  输出完成并核验后检查点落盘，历史清单保存至内容哈希缓存；恢复验证已存字节，只补未完成输出，拒绝冲突。
  `unpack_runs[]` 记录实际工具版本、输入哈希、参数、完成页和错误，`books[]` 不按 PDF 数量自动填充。
- `pdf_render.py`：核验明确 PDF 物理页和原件哈希，按需生成整页 PNG；渲染图保存在 work 的
  `rendered/`，来源、引擎与参数登记于唯一清单 `pdf_renderings[]`，不改写原始编码流清单，不做识别。
- `transcription.py`：保存助手已视读写出的结构化逐页文字，校验原始页图或已登记整页渲染的关系与哈希；
  每页落盘后检查点更新，重复相同输入复用，显式修订保留原稿及理由。
- `transcription_audit.py`：按任务明确的区域页域与 run ID 检查连续覆盖、工作稿与区块一致、真实图片/稿件/
  映射/输入历史哈希；保存复核标记报告。文件覆盖检查与文字校勘、视觉完整性复核和出版接受独立。

work 清单的 `assembly_runs[]` 保存识别、整理和转换历史；它是工作数据的唯一清单，
不新增导入清单。提案目录中的转换报告与段落映射属于处理输出，不是来源关系副本。
接受后的 `editorial/conversion-review.json` 和 `source-map.jsonl` 只记录文字底本至出版源码
的取舍与映射，不包含扫描出版元数据。`build-book` 不接受工作清单参数，仅从本书 `src/` 打包，
将包、同名 `.build.json`、`.epubcheck.json` 与 `.validation.json` 保存到 `books/<id>/dist/`。
旧 `build_runs` 和包状态移入各书 `dist/build-history.json`，work 不再维护它们；其来源及迁移前完整清单仍保留。
工作档案和打包记录有独立生命周期，接受转换不自动提升完整校勘、阅读器或发行状态。

迁移命令提供 `--check` 预检，拒绝合并既有 work 或覆盖目标文件。旧清单保存在缓存的迁移快照，
历史计划、报告、原稿和页图保持原字节；当前清单更新位置，`data_layout_migrations` 记录旧路径到新路径的关系。
历史文件内嵌的 `data/raw/` 路径代表当时的位置，回溯时按此映射定位，不为迁移改写旧证据或哈希。

后续仍需增加：

1. `importers/` 与 `renderers/`：安全 EPUB 解包、复杂版面、交互表单与特殊页面单位的可视页图。
2. 完整识别稿管理：基于已实现的逐页登记，增加失败队列、中断修复和实际视觉页覆盖复核。
3. `editorial/`：已接受正文的差异复核与持续校勘，避免再次生成覆盖校勘成果。
4. `validators/`：实际页覆盖、未决疑点和复核摘要门禁、目标阅读器验收。
5. `publication/` 发行流程：完整验收后保存已经检查的相同包及发行清单。

首版保持本地 CLI 与单书工作流。批量下载、网页校勘、队列、模型投票、系列自动拆卷和
独立书籍仓库导出放在端到端样例验证之后。中文版规则及 SE 差异见 `standards.md`。
