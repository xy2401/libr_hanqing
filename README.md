# libr_hanqing · 古籍数字化

把扫描古籍 PDF、影像型 EPUB 或已有文本 EPUB，整理为可选择、可检索、可重排的电子书。
项目采用 Python 工具链，参考 [Standard Ebooks](https://github.com/standardebooks/tools)
的出版源码结构，另定义适合中文古籍的排版与校勘规则。

当前已实现书目管理、作者/系列分类、出版源码初始化，以及 Markdown 至 XHTML 的提案转换、
人工接受、结构检查、候选 EPUB 打包和本地 EPUBCheck 调用。
PDF 渲染、EPUB 安全解包、可恢复识别稿管理、页覆盖与完整发行门禁仍待接入。
图片转 Markdown 由当前助手使用自身多模态能力直接看图转录，不调用外部识别接口或本地 OCR。

后续开发与助手协作遵循仓库根目录的 [AGENTS.md](AGENTS.md)。

## 目录结构

```text
libr_hanqing/
├── pyproject.toml              # Python 包与 hanqing 命令
├── src/hanqing/
│   ├── cli.py                  # CLI 入口
│   ├── models.py               # 作品、数字版本、作者和系列模型
│   ├── catalog.py              # 书目读取与校验
│   ├── scaffold.py             # 新书出版源码初始化
│   ├── pipeline.py             # 后续处理阶段的契约
│   ├── publication/            # 明确选文、XHTML 提案/接受、候选包
│   ├── validators/             # 资源、全书 ID、链接、目录检查
│   ├── providers/base.py       # 页面识别输入/结果类型及预留协议
│   ├── prompts/                # 可追踪的提示词版本
│   └── templates/              # 自有中文 EPUB 源码模板
├── books/<book-id>/            # 同一本数字版本只保存一份
│   ├── book.toml               # 作品作者、数字版本与书目标记
│   ├── md/                     # 确认的文字底本快照：Git 跟踪，不打包
│   ├── editorial/              # 已确认转换的映射/接受记录、选定封面的固定设计记录
│   ├── images/                 # 选定的封面、插图源素材
│   └── src/
│       ├── mimetype
│       ├── META-INF/container.xml
│       └── epub/
│           ├── content.opf
│           ├── toc.xhtml
│           ├── text/           # 校勘后的 XHTML：出版正文权威源
│           ├── css/
│           └── images/         # 发行图片
├── data/
│   ├── raw/<source-set-id>/         # 原始扫描集及处理中间稿，整体 Git 忽略
│   │   ├── original.pdf           # 原始底本，也可为 original.epub
│   │   ├── unpacked/              # 共享原始解包：页图、元数据、封面候选原图
│   │   ├── md.<work-id>/          # 持续整理的完整 Markdown、页码表与原稿快照
│   │   ├── editorial.<work-id>/   # 过程记录、疑点及保留的转换/检查记录
│   │   └── manifest.json          # 唯一清单：文件、来源、作品和处理历史
│   └── cache/                     # 共享工具缓存，Git 忽略
├── dist/                       # 最终 EPUB 等产物，Git 忽略
├── config/pipeline.toml         # 后续处理器的配置草案
├── schemas/                    # 中间数据契约
├── docs/                       # 架构与中文出版规范
└── tests/
```

`books/` 按稳定 ID 存储。作者和系列都可以多值，通过书目命令生成分类视图；
书籍 ID 以作者或系列 ID 为前缀，如 `yan-fu-zhengzhi-jiangyi`，不使用扫描版年份命名。
不嵌套成两套作者/系列目录，也不复制一本书的正文。不同底本形成不同数字版本。
`data/raw/` 按原始扫描集存储，与 `books/` 分开命名；一个扫描集可以包含一本或多本
独立作品，各书共享原始 PDF 和整本解包，分别维护自己的出版源码。

## 开始使用

要求 Python 3.11+。包安装后可使用 `hanqing`：

```powershell
python -m pip install -e .
hanqing init-book kong-zi-lunyu --work-id lunyu --title "論語" --author "孔子" --author-id kong-zi --series "十三經" --series-id shisan-jing --edition "古籍数字整理本"
hanqing catalog --group-by author
hanqing catalog --group-by series
hanqing catalog --author kong-zi --json
hanqing check-catalog
hanqing plan kong-zi-lunyu
```

也可使用 `uv sync` 和 `uv run hanqing ...`。初始化生成书目、扉页、版本说明与
容器文件，不生成古籍正文；已存在的书籍目录会报错，保护人工校勘成果。
匿名书籍可以省略作者参数；更多作者、注释者、编者和系列在 `book.toml` 中追加。
`--root` 放在子命令之前，可以指定另一项目根目录。

不安装依赖也可直接运行骨架与测试：

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
python -m hanqing --help
python -m unittest discover -s tests -v
```

## 底本与出版成果

将扫描文件保存到 `data/raw/ruan-yuan-shisan-jing/original.pdf`，其底本 ID、类型、路径、
真实 SHA-256、下载地址、现代出版信息、ISBN、扫描版主编/点校者和底本说明全部保存到
raw 的 `manifest.json`。`book.toml` 只保存出版书目，不包含 `sources`、`primary_source_id`
或扫描文件路径与哈希。`check-catalog` 不读取 raw 清单或原件；实际处理时仍须验证文件与哈希。
底本登记示例和复核约定见 [架构设计](docs/architecture.md)。

同一扫描集的解包、页图、原始响应和运行报告保存在 `data/raw/<source-set-id>/` 下。
整本原始解包集中放 `unpacked/`，保留页图、附带元数据和封面候选原图。
raw 是持续整理的工作目录；分作品的完整文字稿保存在 `md.<work-id>/`，过程记录保存在
`editorial.<work-id>/`，包括现代附加材料、疑点、页码表和原稿快照。修改工作稿前将原稿
保存在同目录的 `*.original.md`。`books/<book-id>/md/` 保留纳入 Git 的文字底本快照，
不自动跟随工作稿变化。项目整理完成后，逐项确认成品并复制进入 books，raw 材料始终保留。

`manifest.json` 是本地数据唯一清单：`files[]` 记录整理前后路径、哈希和来源关系，
`books[]` 登记独立作品的 `book_id`、`work_id`、`book_directory`、`markdown_directory`、
显式 `markdown_order`、`page_map` 与页域；`markdown_directory` 指向 raw 工作稿，
`markdown_snapshot_directory` 指向 books 的 Git 快照，`editorial_directory` 指向 raw 过程记录。
`files[].book_snapshot` 记录保留快照的路径和哈希。共享 PDF 与每本书的关系仅由该清单定义，
不再为各书复制来源字段或导入清单。
只有核验与 `unpacked/` 中保留的规范页图 SHA-256 一致后，才可删除重复副本，并在
`files[]` 中保留副本来源和规范页图路径。影像底本和运行 ID 只保存在 raw 清单中，原件保持原始字节。

例如，两本书的工作稿分别为 `data/raw/yan-fu-quanji-vol-06-2014/md.zhengzhi-jiangyi/` 和
同一扫描集的 `md.yingwen-hangu/`，对应的 Git 快照保留在各自的 `books/<book-id>/md/`。
两书共享该扫描集的 PDF 与解包；此前移出的文字稿和记录已恢复为 raw 副本。
两张封面候选原图仍在该扫描集的 `unpacked/`，由各 `books[]` 项的 `cover_candidate` 引用；
候选图尚未作为出版图片接受。

`books/` 的出版元数据与正文不带现代扫描版出版说明、ISBN、
版权页或扫描版主编/点校贡献。来源信息保存在 raw 清单对应作品的 `source_publication`，
出版取舍由 `publication_policy` 记录。现代点校说明不纳入古籍正文；混入古籍原序的材料
须逐段辨别。非出版 `md/` 底本保留原文，包括待剥离材料，不直接晋升为成品正文。

清单当前为 `schema_version=3`、`path_base="project"`，全部当前路径相对项目根目录，
分别指向 raw 影像/工作稿和 books 快照，不使用 `../` 跨目录。
EPUB 仅打包 `books/<book-id>/src/` 出版源码，不收录 `md/`、Markdown 或 `editorial/`。
Python wheel/sdist 也排除 `books/` 和 `data/`，由 `MANIFEST.in` 限定发行内容。

两本书的初轮文字勘误、局部影像修订与后续检查均保存在 raw 的 `editorial.<work-id>/`，
历史报告保持原字节。2026-10-04 继续对照主底本及必要外证后，所列54组编号疑点均已有
工作稿定读结论；34组得到本轮新证据，20组承接既有记录并核验当前读法。另保存14项
漏录、整段替换和推校复查记录；这些分组有交叠，不能视为全书错误数。
《英文漢詁》篇十六已按用户许可核完物理253–268页，恢复§150–165，复核§166–170与表格，
恢复21条RULE的顺序和原例；篇七§56–57的局部漏录也已恢复。原页复查撤回10处先前的
文字推校，保留底本旧拼法、疑误和原著观点。p210_1据早期扫描确认为原著注释，待出版差异提案恢复。
最新结论见 `editorial.<work-id>/source-settlement-2026-10-04.md`、对应验证记录及唯一清单
`finding_reviews[]`。所列疑点定读与篇十六勘定不代表全书逐页影像覆盖或人工接受完成。
已按用户确认的正文结构和注释范围接受本轮 XHTML 转换，生成两本候选 EPUB：
《政治講義》自敍与八會，《英文漢詁》敘、卮言与十八篇（§1–192，43 张表格）。
只收严复原文与可确认的原著注释，现代点校说明、注释和纸本目录留在 Markdown 底本，
原著夹注及英文语法例句保留。两本候选均通过 EPUBCheck 5.4.0，0 错误、0 警告；
接受记录与段落映射保存在各书 `editorial/`，候选检查摘要保存在 raw 对应作品的 `editorial.<work-id>/`。
books 的 editorial 仅保存明确接受的固定记录；校勘工作档案在 raw 持续维护。上述 raw 修订
尚未通过新的出版差异提案确认进入 books，现有候选包仍为此前接受的转换字节。全书页覆盖、出版修订接受和阅读器验收仍待处理，
当前为候选包，未正式发行。浏览器排版抽查受本地地址访问限制，未记为验收通过。

## 正文转换与候选构建

转换需要本地 [Pandoc](https://pandoc.org/installing.html)，不进行图片识别。
EPUBCheck 需要 Java 与[官方检查器](https://www.w3.org/publishing/epubcheck/docs/installation/)，
缓存可放 `data/cache/epubcheck/`；Python 包不绑定这些程序的安装路径。

在 raw 清单的每个 `books[]` 项中明确维护 `publication_plan`，按数组顺序选文，
不按文件名推断章节。每项指定 `chapter_id`、`title`、`markdown_path`、真实
`markdown_sha256`、从 1 开始且包含两端的 `line_range`、`epub_type`（`preface` 或 `chapter`）
和需要排除的现代注释引用 `omit_note_ids`。章节必须来自该书显式 `markdown_order`。
混排的现代材料通过选文范围排除；保留的脚注定义必须处于选文范围内，未解决的引用会报错。
取舍依据及排除范围保存在同一书籍项的 `publication_policy`。

以下展示新转换的操作顺序；当前两本书已执行，不需要重复运行：

```powershell
uv --cache-dir data/cache/uv run hanqing assemble-book yan-fu-zhengzhi-jiangyi --manifest data/raw/yan-fu-quanji-vol-06-2014/manifest.json
# 核对提案后，明确记录本轮转换的人工接受；不提升完整校勘状态。
uv --cache-dir data/cache/uv run hanqing accept-proposal yan-fu-zhengzhi-jiangyi --manifest data/raw/yan-fu-quanji-vol-06-2014/manifest.json --reviewer "复核者姓名"
uv --cache-dir data/cache/uv run hanqing check-publication books/yan-fu-zhengzhi-jiangyi/src
uv --cache-dir data/cache/uv run hanqing build-book yan-fu-zhengzhi-jiangyi --manifest data/raw/yan-fu-quanji-vol-06-2014/manifest.json --epubcheck-jar data/cache/epubcheck/epubcheck-5.4.0/epubcheck.jar
```

`assemble-book` 从清单明确指定的 raw 工作稿读取，只在 raw 的 `proposal.<book>/` 写提案、报告和段落映射；转换前验证 Markdown
的真实 SHA-256，保留文字与标点，不启用 Pandoc smart 标点、拼写现代化或繁简转换。
`accept-proposal` 仅在具体项目材料完成整理并获明确确认后调用。它验证底本、提案与原出版源码均未变化，复制文字底本为 Git 快照，保留 raw 工作稿，备份此前源码后将明确接受的转换
纳入 `books/<book>/src/`，并保存转换记录和段落映射。已有接受记录的正文须通过差异复核编辑，
不能用该命令再次覆盖。接受转换与消除校勘疑点、影像校勘、正式发行是分别记录的事项。

`build-book` 仅从固定的出版 `src/` 创建候选，写到 raw 的 `build.<book>/<book>.epub`；
提供检查器时，将官方报告写到 `validation.<book>/epubcheck.json`。
构建命令同时核对候选、报告、源码及段落映射的实际哈希/锚点，读取 raw 的工作复核记录，
自动保存 `editorial.<work-id>/publication-validation.json`；旧摘要按内容哈希保存在 raw，
并在清单中登记引用和当前文件哈希。初始化书籍只预留已确认记录目录，不创建待复核的工作档案。
候选字节变化后，阅读器与页覆盖状态恢复为待验收；相同字节的既有验收记录保留。
运行历史、构建输入摘要、工具版本和产物 SHA-256 保存在唯一 raw 清单。
现有提案、候选和检查报告默认拒绝覆盖，更新前须保留旧字节并维护历史记录。
候选包通过检查后也不会自动进入 `dist/` 或修改 `book.toml` 的发行状态。

两本书已制作 1400×2100 的原创水墨封面：用助手内置生图能力生成底画，再用楷体竖排繁体书名
与“嚴復”，采用宣纸色与疏淡留白。[政治講義封面](books/yan-fu-zhengzhi-jiangyi/images/cover.preview.jpg)表现中式议政与城郭民众，
[英文漢詁封面](books/yan-fu-yingwen-hangu/images/cover.preview.jpg)以地球仪、中西书册和汉语释义构成书案。
《英文漢詁》的 Noun／名物、Verb／云謂、Syntax／句法由内置生图融入对开的书页，
中英文字随纸面透视与水墨笔触一起绘制，书名和作者仍独立排在留白区。
源画、可编辑 SVG、预览和提示词已保存，发行 SVG 已关联到 OPF；封面完成不提升书籍的校勘或
发行状态。原油画封面的源画、源码、预览、发行图和制作记录均已按原字节备份，
保存在各书 `images/cover-oil.*` 与 `editorial/cover-oil-*`。《政治講義》采用共同拟定主题后的水墨版，
《英文漢詁》采用书页双语融入水墨画的新版。封面只保留最新版与油画版，中间水墨版本、
叠字版、提示词草案及处理临时文件已清理；实际提示词和最终设计记录保存在 editorial。
油画备选不加入出版 `src/`。
参照规范及水墨、AI 封面的差异见 [封面约定](docs/standards.md#封面)，编排工具见
[tools/README.md](tools/README.md)。

提交 Markdown 底本及快照、书目、经过校勘的 XHTML、样式、Markdown 至 XHTML 的段落映射和编辑决定。忽略原始 PDF/EPUB、
解包文件、页图、模型原始响应、缓存、密钥与发行包。原始底本需要另行备份。

## 处理路线

```text
导入登记 → 渲染/解包 → 多模态识别 → 待校勘提案
                                ↓ 人工接受与校勘
                      出版 XHTML → 候选打包 → 检查 → 本地发行产物
```

已有可用文本的 EPUB 优先提取文本和注释；影像型 EPUB 和扫描 PDF 才进入页图识别。
页图由当前助手使用自身多模态能力直接识别并写入 raw 的 `md.<work-id>/`，明确确认后复制文字快照进入 `books/<book-id>/md/`；禁止外部模型/识别
API、OCR 服务及本地 OCR 引擎。Python 负责解包、PDF 渲染、裁切/旋转、文件与清单管理、
校验和出版构建，图像准备工具不执行文字识别。
模型输出保留页序、区块和疑点，不能直接覆盖已接受的正文。繁简转换、异体字统一与
标点增补必须经过明确的编辑决定。最终电子书按中文 profile 检查，参见
[制作规范与 SE 差异](docs/standards.md)。

后续完善本地导入、安全解包、页图生成及可恢复稿件管理，并完成现有两本书的出版修订接受、
全书页覆盖说明和目标阅读器验收。`plan` 只展示阶段设计及实现范围，不调用模型或执行构建。
