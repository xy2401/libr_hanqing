# 本地数据区

每个原始扫描集的原件和处理数据统一放在 `raw/<source-set-id>/`，与出版书籍
`books/<book-id>/` 分开命名；一个扫描集可以对应一本或多本独立作品：

- `original.pdf` 或 `original.epub` 保存原始底本，保持原始字节。
- `unpacked/` 保存整本原始解包，保留页图、附带元数据和封面候选原图，供各作品共享。
- Markdown 文字底本保存在 `books/<book-id>/md/` 并纳入 Git，包括转录稿、`page-map.md` 和 `*.original.md` 原稿快照；raw 不再保存文字底本目录。
- `manifest.json` 是唯一清单；顶层 `source_set_id` 标识扫描集，`source_id`、`source_kind`、`source_path` 与 `source_sha256` 登记原件，`files[]` 保存路径、哈希和来源关系，`books[]` 定义每本书的 `book_id`、`work_id`、`book_directory`、`markdown_directory`、显式 `markdown_order`、`page_map` 与页域，并保存历次处理记录。

例如 `books/yan-fu-zhengzhi-jiangyi/md/` 和 `books/yan-fu-yingwen-hangu/md/`
共享 `raw/yan-fu-quanji-vol-06-2014/` 中的 `original.pdf` 与 `unpacked/`。
封面候选原图为 `unpacked/cover-zhengzhi-jiangyi.jpg` 和
`unpacked/cover-yingwen-hangu.jpg`，由对应 `books[]` 项的 `cover_candidate` 引用，
尚未作为出版图片接受。

现代扫描版出版社、ISBN、出版年份、主编/点校者、底本描述和导入说明保存在 raw 清单的
`bibliography` 与各 `books[]` 项的 `source_publication`，不写入古籍成品的元数据或版本说明。
`publication_policy` 记录现代附加材料的排除与混排材料复核要求；非出版 Markdown 底本完整保留原文。

重复页图须核验与 `unpacked/` 中保留的规范页图 SHA-256 一致后才能删除；
规范页图仍须存在，副本来源记录保留在 `manifest.json` 的 `files[]`，
`deduplicated_from` 保留旧副本路径，`path` 指向同字节规范页图。

清单使用 `schema_version=3`、`path_base="project"`。当前 `path`、原字节快照
`original_snapshot`、`source_path`、书籍/Markdown 目录、章节、页码表和封面候选引用
统一相对项目根目录；`original_path` 保留原导入路径。每项保存当前 `sha256` 与原始 `original_sha256`。
原件与书籍的关系只由清单的 `books[]` 定义；`book.toml` 不包含影像来源 ID、路径或哈希。

影像底本 ID 和运行 ID 只记录在 raw 清单中；目录仅按实际内容建立，不预设编号或包装层。
更新已有中间稿前，通过同目录原稿文件或内容缓存保留旧内容及其哈希，并在清单中登记，
不能丢失输入和 AI 原稿。现有 AI 稿仍未校勘，最终 EPUB 尚未生成。

Git 跟踪 Markdown 底本，但发行只收录 `books/<book-id>/src/`，排除整个 `md/`、Markdown 和
校勘记录；Python wheel/sdist 也不包含 `books/` 或 `data/`。EPUB runner 尚未实现。

`cache/` 保存可重建的共享工具缓存。`raw/` 和 `cache/` 均被 Git 忽略，
使用时由后续命令创建；处理器不得修改原件或丢失历史输入与结果。

忽略意味着数据不会随 Git 备份。原始底本应另做本地或对象存储备份；来源地址、
SHA-256 和底本说明仅保存在 raw 清单，不在可提交书目中重复登记。
