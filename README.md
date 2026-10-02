# libr_hanqing · 古籍数字化

把扫描古籍 PDF、影像型 EPUB 或已有文本 EPUB，整理为可选择、可检索、可重排的电子书。
项目采用 Python 工具链，参考 [Standard Ebooks](https://github.com/standardebooks/tools)
的出版源码结构，另定义适合中文古籍的排版与校勘规则。

当前是**可运行的项目骨架**：书目管理、作者/系列分类、出版源码初始化已实现；
PDF 渲染、EPUB 解包、多模态识别、校勘检查和 EPUB 构建尚待接入。

后续开发与助手协作遵循仓库根目录的 [AGENTS.md](AGENTS.md)。

## 目录结构

```text
libr_hanqing/
├── pyproject.toml              # Python 包与 hanqing 命令
├── src/hanqing/
│   ├── cli.py                  # CLI 入口
│   ├── models.py               # 作品、数字版本、作者、系列和底本模型
│   ├── catalog.py              # 书目读取与校验
│   ├── scaffold.py             # 新书出版源码初始化
│   ├── pipeline.py             # 后续处理阶段的契约
│   ├── providers/base.py       # 多模态模型适配器接口
│   ├── prompts/                # 可追踪的提示词版本
│   └── templates/              # 自有中文 EPUB 源码模板
├── books/<book-id>/            # 同一本数字版本只保存一份
│   ├── book.toml               # 作者、系列、底本、版本和书目标记
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
│   ├── raw/<book-id>/<source-id>/  # 原始 PDF/EPUB，Git 忽略
│   ├── work/<book-id>/<run-id>/    # 解包、页图、识别稿与检查报告，Git 忽略
│   └── cache/                     # 可重建缓存，Git 忽略
├── dist/                       # 最终 EPUB 等产物，Git 忽略
├── config/pipeline.toml         # 后续处理器的配置草案
├── schemas/                    # 中间数据契约
├── docs/                       # 架构与中文出版规范
└── tests/
```

`books/` 按稳定 ID 存储。作者和系列都可以多值，通过书目命令生成分类视图；
不嵌套成两套作者/系列目录，也不复制一本书的正文。不同底本形成不同数字版本。

## 开始使用

要求 Python 3.11+。包安装后可使用 `hanqing`：

```powershell
python -m pip install -e .
hanqing init-book lunyu-ruan-yuan --work-id lunyu --title "論語" --author "孔子" --author-id kong-zi --series "十三經" --series-id shisan-jing --edition "阮元校刻十三經注疏本"
hanqing catalog --group-by author
hanqing catalog --group-by series
hanqing catalog --author kong-zi --json
hanqing check-catalog
hanqing plan lunyu-ruan-yuan
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

将扫描文件保存到 `data/raw/lunyu-ruan-yuan/scan-001/original.pdf`，在书目文件中登记
`sources`、`primary_source_id`、真实 SHA-256、下载地址和底本说明。来源文件无需存在于
每个 Git 克隆中，`check-catalog` 仅校验登记内容；实际处理时仍须验证文件与哈希。
底本登记示例和复核约定见 [架构设计](docs/architecture.md)。

提交书目、经过校勘的 XHTML、样式、来源映射和编辑决定。忽略原始 PDF/EPUB、
解包文件、页图、模型原始响应、缓存、密钥与发行包。原始底本需要另行备份。

## 处理路线

```text
导入登记 → 渲染/解包 → 多模态识别 → 待校勘提案
                                ↓ 人工接受与校勘
                      出版 XHTML → 候选打包 → 检查 → 本地发行产物
```

已有可用文本的 EPUB 优先提取文本和注释；影像型 EPUB 和扫描 PDF 才进入页图识别。
模型输出保留页序、区块和疑点，不能直接覆盖已接受的正文。繁简转换、异体字统一与
标点增补必须经过明确的编辑决定。最终电子书按中文 profile 检查，参见
[制作规范与 SE 差异](docs/standards.md)。

下一步优先拿一部真实底本，依次接入本地导入、页图生成、一个模型适配器和可恢复识别，
再完成人工校勘与 EPUBCheck。`plan` 当前只展示阶段设计，不调用模型或执行构建。
