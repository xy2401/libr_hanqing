# 架构设计

## 身份与分类

区分三层身份：`work_id` 是作品，如 `lunyu`；`book.id` 是准备出版的数字版本，
如 `lunyu-ruan-yuan`；`source.id` 是登记的底本文件，如 `scan-001`。文件的 SHA-256
标识原始字节。作品名称和作者显示名可修改，稳定 ID 不跟随分类变化。

同书不同底本独立建书。多个来源可以挂在同一数字版本中，但须明确主底本，其他来源
只按校勘政策使用。多册文件的卷册顺序需要显式记录；后续导入器不能按文件名猜测，
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
| `data/raw/` | 下载后的原始底本，保持原始字节 | 忽略 | 依赖外部来源，需备份 |
| `data/work/` | 解包、页图、识别响应、提案、候选 EPUB、检查报告 | 忽略 | 通常可重跑；模型结果应缓存 |
| `data/cache/` | 可重建缓存 | 忽略 | 是 |
| `books/<id>/book.toml` | 书目、底本登记与书目标记 | 提交 | 由人工维护 |
| `books/<id>/src/` | 已接受的 XHTML、导航、OPF、样式与发行图片 | 提交 | 正文为权威源 |
| `books/<id>/editorial/` | 校勘政策、编辑决定、来源映射与复核证据 | 提交 | 由人工维护 |
| `dist/` | 验收通过的发行文件与发布清单 | 忽略 | 从固定输入构建 |

识别 JSONL 是中间稿，Markdown 只用于校勘说明。人工接受后的正文只在 XHTML 中编辑，
避免 JSON、Markdown 和 XHTML 三份正文同时演化。再次识别或结构化只生成提案与差异，
由编辑决定是否接受；处理器不得重写已经接受的 XHTML。

## 底本登记

`book.toml` 的书目基本信息由 `init-book` 生成。登记底本时，将下列顶层字段放在第一个
`[[creators]]`、`[[series]]` 或 `[[sources]]` 之前：

```toml
primary_source_id = "scan-001"
```

然后在文件末尾添加来源表。下例中的 SHA-256 空串须在处理前替换成真实的 64 位十六进制值；
`draft` 可以暂留空串，但不能用占位哈希冒充验证结果。

```toml
[[sources]]
id = "scan-001"
kind = "pdf" # 或 epub
path = "data/raw/lunyu-ruan-yuan/scan-001/original.pdf"
sha256 = ""
url = "https://example.org/source"
description = "阮元校刻本；补充藏书机构、卷册与扫描信息"
```

来源路径使用相对项目根目录的 `/` 形式。原始文件可能不在当前克隆中，所以书目检查
不要求文件存在；`ingest` 将负责实际文件、类型、大小和 SHA-256 校验。可以在 PowerShell
中用 `Get-FileHash -Algorithm SHA256 -LiteralPath <文件路径>` 计算真实哈希。

## 阶段和可恢复运行

| 阶段 | 职责 | 接受条件 |
| --- | --- | --- |
| `ingest` | 登记本地输入，不修改原件 | 来源身份、文件类型和哈希验证 |
| `prepare` | PDF 渲染；EPUB 解包并区分文本/影像/混合内容 | 页数与页序可核对，解包路径合法 |
| `recognize` | 逐页或区域调用多模态模型 | 结构输出合法，疑点显式保留 |
| `assemble` | 识别稿转换为卷/章/注释的 XHTML 提案 | 阅读顺序明确，提案可对照底本 |
| `proofread` | 人工对照、接受提案并校勘 XHTML | 无未处理疑点，所有应处理页有覆盖说明 |
| `build` | 从固定出版源码打包候选 EPUB | manifest、spine 与构建输入固定 |
| `validate` | 校勘证据、结构、链接、EPUBCheck 和阅读器检查 | 所有必需检查通过 |
| `release` | 保存已经验收的相同产物字节 | 哈希一致，附发行清单 |

这是后续 runner 的设计，当前只实现 `plan` 展示。工作目录用
`data/work/<book-id>/<run-id>/` 隔离。每次运行的 manifest 应保存：输入文件和页图哈希、
底本 ID、渲染参数、程序版本、模型供应商和模型名、提示词版本、schema 版本、
请求参数、完成页、错误、消耗记录和预算。

缓存键由输入内容及上述有效配置共同决定；提示词或模型变更不能复用旧识别结果。
逐页结果落盘后才标记成功，恢复时仅补跑未完成页。失败重试有次数上限，达到预算停止；
多个版本的识别结果保留，不以同名文件覆盖。密钥只从环境或忽略的本地配置读取，
不写入书目、运行记录或模型日志。

EPUB 解包器需要拒绝路径穿越、绝对路径与符号链接，并限制文件数量和解压大小。
PDF 页面先保留整页，再记录裁切、旋转和区域坐标关系；原书双页、版心、页码、正文与
夹注必须能回溯，不能用只剩文字的 OCR 结果替代来源证据。

## 中间数据与校勘证据

多模态接口定义于 `providers/base.py`，页面结果契约见
`schemas/page-transcription.schema.json`。一条 JSONL 对应一个物理页，区分文件中的
`physical_page` 与原书页码 `printed_page_label`；每个区块有稳定 ID、类型、阅读次序、
文字、相对于整页的坐标和疑点。schema 校验后还要检查坐标顺序、区块 ID 唯一性和页覆盖。
这些运行期检查尚未实现。不要把模型自报的置信度当成校勘通过条件。

`editorial/source-map.jsonl` 只保存来源关系，不再复制整份正文。建议每条记录包含
`source_id`、`source_sha256`、`physical_page`、`block_id`、`bbox`、`xhtml_path` 与 `xhtml_id`。
一个原书页可对应多个段落，一段正文也可跨页。书签/页码导航以后从这份映射生成。

`editorial/decisions.jsonl` 保存编辑决定：疑点 ID、来源位置、原读、采用读法、理由、
编辑者与时间；句读、繁简、异体字和他本校改分别记录。正文缺字不能凭记忆补齐；
保留缺字符号或字形图片等方案由书籍校勘政策决定。

`review.toml` 初始为 `pending`。未来接受复核时须记录复核者、时间、已处理页/排除页、
出版源码摘要及未处理疑点数；正文变更后旧复核证据失效。`book.toml` 中的
`draft / recognized / proofread / ready / released` 仅为书目标记，当前可人工填写，
不证明已经通过检查。发行门禁必须检查实际复核证据与校验报告。

## Python 模块边界与推进顺序

当前核心全部使用标准库：CLI、元数据、分类、初始化、阶段契约、模型接口和资源模板。
供应商 SDK、PDF 引擎和 EPUB 验证工具在后续实现时接入，隔离于边界模块；不让书目管理
依赖某一家模型 API，也不把 SE 工具集作为启动骨架的强制依赖。

后续依次增加：

1. `importers/` 与 `renderers/`：本地导入、安全解包、页图和来源 manifest。
2. `providers/<vendor>.py` 与 `runner.py`：单一供应商实现、输出验证、逐页缓存与预算。
3. `editorial/` 与 `publication/`：提案转换、差异接受、注释及来源映射；确认后人工编辑 XHTML。
4. `validators/`：页覆盖、未决疑点、链接/ID/目录、EPUBCheck 和复核摘要检查。
5. `publication/` 构建器：先打候选包，再验收，最后保存同一包及发行清单。

首版保持本地 CLI 与单书工作流。批量下载、网页校勘、队列、模型投票、系列自动拆卷和
独立书籍仓库导出放在端到端样例验证之后。中文版规则及 SE 差异见 `standards.md`。
