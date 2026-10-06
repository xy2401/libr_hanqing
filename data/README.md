# 本地数据区

```text
data/
├── inbox/                 待处理原件的转运区
├── work/
│   └── <source-set-id>/   已开始整理的项目材料
│       ├── original.pdf  或 original.epub，保持原始字节
│       ├── unpacked/     整本解包与共享页图
│       ├── md.<work-id>/  完整 Markdown 工作稿及原稿快照
│       ├── editorial.<work-id>/  来源、校勘和过程记录
│       ├── proposal.<book-id>/   待接受的转换提案
│       └── manifest.json 工作区唯一清单
└── cache/                工具缓存、历史快照及迁移日志

books/<book-id>/
├── md/                   已确认并纳入 Git 的文字底本快照
├── src/                  已接受的出版源码，打包唯一输入
├── editorial/            已接受的固定制作记录
└── dist/                 本书的包、构建与检查记录，忽略 Git
```

新收到的 PDF、EPUB 或页图先放 `inbox/`。实际开始整理时，核验原件，归入
`work/<source-set-id>/` 并登记原始文件名、字节哈希和来源；不把已处理原件副本留在转运区。
`intake-pdfs` 已支持按显式计划批量接收 PDF，并核验、提取原始编码流；自动拆书与排队仍为规划。
inbox、work 和 cache 全部忽略 Git。

work 是持续整理区，保留原件、解包、完整文字工作稿、现代附加材料、历史快照和校勘依据。
新接收的扫描集先有原件、`unpacked/` 与唯一清单，`books[]` 为空；后续明确拆书后再建立关系。
`pdf_unpack.pages[]` 记录物理页序、图片对象、矩阵、裁切框、旋转与流哈希；无图片页保存原始
内容流及资源引用，不把图片数量直接当作物理页覆盖。PDF 中的完整字体和其他资源仍保留在原件。
一个扫描集可以在 `manifest.json` 的 `books[]` 定义一本或多本作品；作者/系列前缀用于稳定
book-id，不按原始 PDF 数量推断拆书。各作品共享原件与解包，分别维护工作稿和出版源码。

唯一工作清单使用 `schema_version=3`、`path_base="project"`。当前路径相对项目根目录，
保存来源身份、真实哈希、文件映射、页域、作品关系及整理历史；历史导入路径保持原记录。
现代出版信息仅在工作区保存，不写入成品书目或出版正文。确认成品后复制快照进入 books，
work 项目材料继续保留；两处不自动同步。重复页图仅在核验与保留的规范页图同字节后去除。

打包独立读取本书 `book.toml` 与 `src/`，不需要工作清单或原始数据：

```powershell
uv --cache-dir data/cache/uv run --no-sync hanqing build-book <book-id>
```

默认输出 `books/<book-id>/dist/<book-id>.epub`；同名 `.build.json` 保存构建记录。
提供 EPUBCheck 时，同名 `.epubcheck.json` 保存官方报告，`.validation.json` 保存检查摘要。
`--output books/<book-id>/dist/<新文件名>.epub` 可保存新候选，已有字节拒绝覆盖。
只有 `src/` 进入 EPUB；md、editorial、dist 和所有工作数据均不打包。Python wheel/sdist
也不收录 books 或 data。候选构建不会自动表示全文勘定、阅读器验收或正式发行完成。

旧 raw 目录、包和检查报告通过 `hanqing migrate-data-layout` 迁移。
旧清单快照与历史报告保持原字节，当前清单记录 `data_layout_migrations`；历史文件中的
旧 `data/raw/` 路径按此迁移关系定位。旧构建及包状态保存到各书 `dist/build-history.json`，
work 不再维护 `build_runs`。已有勘定稿保留在 work，未自动覆盖 books 的接受快照。

忽略意味着这些本地数据不会随 Git 备份；原件和完整工作区需要另行备份。
