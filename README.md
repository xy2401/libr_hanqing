# libr_hanqing · 古籍数字化

把扫描古籍 PDF、影像型 EPUB 或已有文本 EPUB，整理为可选择、可检索、可重排的电子书。
项目采用 Python 工具链，参考 [Standard Ebooks](https://github.com/standardebooks/tools)
的出版源码结构，另定义适合中文古籍的排版与校勘规则。

当前是**可运行的项目骨架**：书目管理、作者/系列分类、出版源码初始化已实现；
PDF 渲染、EPUB 解包、识别稿管理、校勘检查和 EPUB 构建尚待接入。
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
│   ├── providers/base.py       # 页面识别输入/结果类型及预留协议
│   ├── prompts/                # 可追踪的提示词版本
│   └── templates/              # 自有中文 EPUB 源码模板
├── books/<book-id>/            # 同一本数字版本只保存一份
│   ├── book.toml               # 作品作者、数字版本与书目标记
│   ├── md/                     # Markdown 文字底本与原稿快照：Git 跟踪，不打包
│   ├── editorial/              # 校勘说明、决定、来源映射与复核记录
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
Markdown 文字底本放入各自的 `books/<book-id>/md/`，包括转录稿、`page-map.md` 和原稿
Markdown，并纳入 Git；图片仍保留在 raw，不复制整本页图。
修改 Markdown 前将原稿保存在同目录的 `*.original.md`。

`manifest.json` 是本地数据唯一清单：`files[]` 记录整理前后路径、哈希和来源关系，
`books[]` 登记独立作品的 `book_id`、`work_id`、`book_directory`、`markdown_directory`、
显式 `markdown_order`、`page_map` 与页域。共享 PDF 与每本书的关系仅由该清单定义，
不再为各书复制来源字段或导入清单。
只有核验与 `unpacked/` 中保留的规范页图 SHA-256 一致后，才可删除重复副本，并在
`files[]` 中保留副本来源和规范页图路径。影像底本和运行 ID 只保存在 raw 清单中，原件保持原始字节。

例如，两本书的文字底本分别为 `books/yan-fu-zhengzhi-jiangyi/md/` 和
`books/yan-fu-yingwen-hangu/md/`，共享 raw 中 `yan-fu-quanji-vol-06-2014` 扫描集的 PDF 与解包。
两张封面候选原图仍在该扫描集的 `unpacked/`，由各 `books[]` 项的 `cover_candidate` 引用；
候选图尚未作为出版图片接受。

`books/` 的出版元数据与正文不带现代扫描版出版说明、ISBN、
版权页或扫描版主编/点校贡献。来源信息保存在 raw 清单对应作品的 `source_publication`，
出版取舍由 `publication_policy` 记录。现代点校说明不纳入古籍正文；混入古籍原序的材料
须逐段辨别。非出版 `md/` 底本保留原文，包括待剥离材料，不直接晋升为成品正文。

清单当前为 `schema_version=3`、`path_base="project"`，全部当前路径相对项目根目录，
统一指向 raw 影像和各书的 `md/`，不使用 `../` 跨目录。
EPUB 仅打包 `src/` 出版源码，不收录 `md/`、Markdown 或 `editorial/`；其 runner 尚未实现。
Python wheel/sdist 也排除 `books/` 和 `data/`，由 `MANIFEST.in` 限定发行内容。

两本书的 Markdown 已完成一轮文字勘误：修正 15 处明确的文本问题，保留 21 项疑点。
改字依据与检查范围见《[政治講義](books/yan-fu-zhengzhi-jiangyi/editorial/text-review.md)》和
《[英文漢詁](books/yan-fu-yingwen-hangu/editorial/text-review.md)》的文字检查记录。
本轮依据现有文字及文内对照，影像逐字校勘、页覆盖核验和人工接受仍未完成；当前尚未生成最终 EPUB。

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
页图由当前助手使用自身多模态能力直接识别并写入 `books/<book-id>/md/`；禁止外部模型/识别
API、OCR 服务及本地 OCR 引擎。Python 负责解包、PDF 渲染、裁切/旋转、文件与清单管理、
校验和出版构建，图像准备工具不执行文字识别。
模型输出保留页序、区块和疑点，不能直接覆盖已接受的正文。繁简转换、异体字统一与
标点增补必须经过明确的编辑决定。最终电子书按中文 profile 检查，参见
[制作规范与 SE 差异](docs/standards.md)。

下一步优先拿一部真实底本，依次接入本地导入、页图生成、助手直接看图转录和可恢复稿件管理，
再完成人工校勘与 EPUBCheck。`plan` 当前只展示阶段设计，不调用模型或执行构建。
