# 架构设计

## 身份与分类

区分三层身份：`work_id` 是作品，如 `lunyu`；`book.id` 是准备出版的数字版本，
如 `kong-zi-lunyu`；raw 清单中的 `source_id` 是登记的影像底本文件，如 `scan-001`。
其 `source_sha256` 标识原始字节。作品名称和作者显示名可修改，稳定 ID 不跟随分类变化。

书籍 ID 使用作者或系列 ID 前缀，如 `yan-fu-zhengzhi-jiangyi`；现代扫描版年份属于来源信息，
不作为古籍数字版名称。用户要求迁移 ID 时，目录、书目、OPF 标识符和清单当前引用一起更新，
raw 清单保留旧 ID 和迁移记录。

`source_set_id` 标识本地原始扫描集，存储于 `data/raw/<source-set-id>/`。
扫描集和数字版本分开命名，二者无需一一对应：同一底本文件可以包含多本独立作品，
由扫描集清单的 `books[]` 显式定义，各自使用 `books/<book-id>/` 的出版源码，
共享同一原始文件及其解包。影像底本 ID、路径、哈希和书籍关系只在 raw 清单中登记。

同书不同底本独立建书。校改参考其他来源时，在 raw 清单中明确主底本与参考关系，
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
| `data/raw/<source-set-id>/` | 原始影像底本、共享解包、响应、提案、候选包与处理记录 | 忽略 | 原件需备份；处理中间稿保留历史 |
| `data/cache/` | 可重建的共享工具缓存 | 忽略 | 是 |
| `books/<id>/book.toml` | 独立古籍书目、数字版本与书目标记 | 提交 | 由人工维护 |
| `books/<id>/md/` | Markdown 文字底本、页码表与原稿快照 | 提交 | 保留原文，供校勘核对；不打包 |
| `books/<id>/src/` | 已接受的 XHTML、导航、OPF、样式与发行图片 | 提交 | 正文为权威源 |
| `books/<id>/editorial/` | 校勘政策、编辑决定、Markdown 至 XHTML 的映射与复核证据 | 提交 | 由人工维护 |
| `dist/` | 验收通过的发行文件与发布清单 | 忽略 | 从固定输入构建 |

每个原始扫描集的本地数据统一保存在 `data/raw/<source-set-id>/`，整个目录被 Git 忽略。
原始底本直接命名为 `original.pdf` 或 `original.epub`；整本原始解包放 `unpacked/`，
保留页图、附带元数据和封面候选原图。分作品的 Markdown 文字底本保存在
`books/<book-id>/md/` 并纳入 Git，包括转录稿、`page-map.md` 与原稿快照；
不保存图片或重复解包页图，也不收录到 EPUB。

改写过的原始 Markdown 在同目录保存为 `*.original.md`。`manifest.json` 是本地数据
唯一清单，当前使用 `schema_version = 3`、`path_base = "project"`，顶层 `source_set_id` 标识扫描集，
`source_path` 为原件相对项目根目录的路径。原有文件映射全部并入 `files[]`：
`path` 为当前路径，`original_path` 保留原导入路径，`sha256` 和 `original_sha256`
分别记录当前与原始字节哈希；改写稿的 `original_snapshot` 指向保留原字节的快照。
再次修改已有快照的稿件时，不覆盖最初快照；另存 `*.before-text-review.original.md`
等阶段快照，在同一文件记录的 `revisions[]` 中保留修改前后哈希及快照路径。
所有当前路径字段统一相对项目根目录，包含 `source_path`、文件 `path`、`original_snapshot`、
各书的章节/页码表/目录/封面候选与出版取舍引用，避免使用 `../` 跨 raw 和 books。
核验重复页图与规范 `unpacked/` 页图的 SHA-256 一致，且规范文件仍存在后，可以删除
重复副本；其来源记录保留在 `files[]`，`deduplicated_from` 保留旧副本路径，
`path` 指向保留的同字节规范页图。

`books[]` 定义该底本中的一本或多本独立作品，包含 `book_id`、`work_id`、
`book_directory`、`markdown_directory`、显式 `markdown_order`、`page_map` 和页域。
`book_directory` 与 `markdown_directory` 均相对项目根目录。例如：

| `book_id` | `work_id` | `markdown_directory` |
| --- | --- | --- |
| `yan-fu-zhengzhi-jiangyi` | `zhengzhi-jiangyi` | `books/yan-fu-zhengzhi-jiangyi/md` |
| `yan-fu-yingwen-hangu` | `yingwen-hangu` | `books/yan-fu-yingwen-hangu/md` |

两项的 `cover_candidate` 指向该扫描集 `data/raw/yan-fu-quanji-vol-06-2014/unpacked/`
中的两张候选原图，尚未作为出版图片接受。

两项共享 `data/raw/yan-fu-quanji-vol-06-2014/original.pdf` 与 `unpacked/`，
来源字段及与各书的关系全部保存在共享 raw 清单中，不写入 `book.toml`，
不在各书的 `editorial/` 复制导入清单；使用范围与章顺序由对应清单项明确登记。
不将整册扫描集作为唯一出版书籍。
`source_id` 和 `run_id` 只保存在 raw 清单中，不决定目录层级。
目录按实际内容建立，不预设编号或包装层。
处理器不得修改原件；更新已有中间稿前先保存旧内容及其哈希，在清单中保留历史关系，
避免丢失输入和 AI 原稿。

识别 JSONL 和 AI Markdown 是待复核中间稿。人工接受后的正文只在 XHTML 中编辑，
避免 JSON、Markdown 和 XHTML 三份正文同时演化。再次识别或结构化只生成提案与差异，
由编辑决定是否接受；处理器不得重写已经接受的 XHTML。目录整理不能作为完成校勘或
EPUB 转换的证据；文字勘误与影像逐字校勘分别记录，现有稿件尚未完成影像校勘与人工接受，最终 EPUB 尚未生成。

`books/` 面向古籍独立出版内容，`edition` 描述本项目数字整理版。
现代扫描版的出版社、ISBN、年份、主编/点校者、版权页与共享 PDF 的说明只保存在 raw：
扫描集的 `bibliography` 保存全卷出版信息，各作品的 `source_publication` 保存对应贡献、
底本说明和导入记录。古籍出版书目只保留作品与数字版本信息、原作作者/贡献者；现代扫描版
系列和卷次不自动作为古籍电子书系列元数据。`publication_policy` 明确排除现代附加材料；
现代说明与古籍原序合并在同一稿件时必须逐段复核，不丢弃原始影像或 Markdown 底本。
`md/` 作为非出版底本可保留现代附加材料原文，便于核对，不能直接加入成品正文。

发行只从 `books/<book-id>/src/` 收集文件，排除整个 `md/`、Markdown、`editorial/` 与 raw，
禁止递归打包整个书籍目录或在 OPF 引用底本。`config/pipeline.toml` 声明这一边界，
EPUB runner 尚未实现；Python wheel/sdist 由 `MANIFEST.in` 排除 `books/` 和 `data/`。

## 底本登记

`init-book` 仅生成出版书目与源码骨架。`book.toml` 的元数据模型不包含影像来源字段，
校验器拒绝旧 `sources`、`primary_source_id`，所有书目标记均不要求在书目中登记来源。
书目标记不代替实际校勘与发行验收。

底本类型、路径、真实 SHA-256、下载地址、现代出版信息和底本说明统一登记在
`data/raw/<source-set-id>/manifest.json`。当前清单使用以下顶层字段：

- `source_id`：影像底本 ID。
- `source_kind`：`pdf` 或 `epub`。
- `source_path`：原件相对项目根目录的 POSIX 路径。
- `source_sha256`：实际原件的 64 位十六进制 SHA-256。
- `books[]`：通过 `book_id`、书籍目录与使用范围定义该底本对应的出版书籍。

书目检查不读取 raw 清单，也不要求原件存在；`ingest` 将负责实际文件、类型、大小和
SHA-256 校验。哈希未知时如实标为未验证，不使用占位值。可以在 PowerShell
中用 `Get-FileHash -Algorithm SHA256 -LiteralPath <文件路径>` 计算真实哈希。

## 阶段和可恢复运行

| 阶段 | 职责 | 接受条件 |
| --- | --- | --- |
| `ingest` | 登记本地输入，不修改原件 | 来源身份、文件类型和哈希验证 |
| `prepare` | PDF 渲染；EPUB 解包并区分文本/影像/混合内容 | 页数与页序可核对，解包路径合法 |
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

这是后续工作流的设计，当前只实现 `plan` 展示，本地处理 runner 尚未实现。
识别不由 Python runner 调用模型。Markdown 底本放 `books/<book-id>/md/`，其他本地处理结果
按实际内容保存在 `data/raw/<source-set-id>/`；各次运行以清单中的 `run_id` 和内容哈希追踪。
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
`schemas/page-transcription.schema.json`。一条 JSONL 对应一个物理页，区分文件中的
`physical_page` 与原书页码 `printed_page_label`；每个区块有稳定 ID、类型、阅读次序、
文字、相对于整页的坐标和疑点。schema 校验后还要检查坐标顺序、区块 ID 唯一性和页覆盖。
这些运行期检查尚未实现。不要把模型自报的置信度当成校勘通过条件。

`editorial/source-map.jsonl` 保存 Markdown 文字底本段落与 XHTML 的对应关系，不复制正文。
建议每条记录包含 `markdown_path`、`markdown_anchor`、`xhtml_path` 与 `xhtml_id`。
影像底本 ID、文件哈希、页图坐标及影像至 Markdown 的对应关系只在 raw 清单中保存。
文字底本可通过其页码表与 raw 清单回溯影像；一页可对应多个段落，一段正文也可跨页。

`editorial/decisions.jsonl` 保存编辑决定：疑点 ID、来源位置、原读、采用读法、理由、
编辑者与时间；句读、繁简、异体字和他本校改分别记录。正文缺字不能凭记忆补齐；
保留缺字符号或字形图片等方案由书籍校勘政策决定。

已有文字底本时，未明确要求影像核对的“校勘／勘误”默认执行文字检查；疑点先记录为待核，
不自行启动看图转录、逐页影像比对或全书重新识别。

基于现有 Markdown 的文字勘误单独记录于 `editorial/text-review.md`，明确文本检查范围、
改字依据和未决疑点。`review.toml` 的 `text_review` 子表记录该轮检查及稿件摘要，
不改变顶层人工复核状态；raw 清单中的 `text_reviews[]` 记录本地处理历史。
文字勘误不能证明转录忠实、正文无遗漏或页图覆盖完整，也不能作为 `proofread` 的验收。

`review.toml` 初始为 `pending`。未来接受复核时须记录复核者、时间、已处理页/排除页、
出版源码摘要及未处理疑点数；正文变更后旧复核证据失效。`book.toml` 中的
`draft / recognized / proofread / ready / released` 仅为书目标记，当前可人工填写，
不证明已经通过检查。发行门禁必须检查实际复核证据与校验报告。

## Python 模块边界与推进顺序

当前核心全部使用标准库：CLI、元数据、分类、初始化、阶段契约、页面数据类型和资源模板。
后续接入本地 PDF 引擎和 EPUB 验证工具，隔离于边界模块；图片识别使用助手自身多模态能力，
不实现模型供应商 SDK、外部识别接口或本地 OCR 后端，也不把 SE 工具集作为启动骨架的强制依赖。

后续依次增加：

1. `importers/` 与 `renderers/`：本地导入、安全解包、页图和来源 manifest。
2. 识别稿管理与本地处理 runner：助手看图转录，Python 登记 Markdown、校验来源与页覆盖、逐页保存进度。
3. `editorial/` 与 `publication/`：提案转换、差异接受、注释及来源映射；确认后人工编辑 XHTML。
4. `validators/`：页覆盖、未决疑点、链接/ID/目录、EPUBCheck 和复核摘要检查。
5. `publication/` 构建器：先打候选包，再验收，最后保存同一包及发行清单。

首版保持本地 CLI 与单书工作流。批量下载、网页校勘、队列、模型投票、系列自动拆卷和
独立书籍仓库导出放在端到端样例验证之后。中文版规则及 SE 差异见 `standards.md`。
