# 电子书制作规范

本项目参考 Standard Ebooks 的目录与编辑理念，采用自有 **hanqing Chinese profile**，发行目标为有效的 EPUB 3。该定位不代表严格通过官方制作规范，也不代表 Standard Ebooks 出版或认证。[官方手册](https://github.com/standardebooks/manual)

每本书使用 `images/` 保存选定的封面与插图素材，`src/META-INF/container.xml` 与 `src/mimetype` 表达容器结构，`src/epub/` 下分设 `text/`、`images/`、`css/`，并保存 `content.opf`、`toc.xhtml`。项目模板中的 `core.css`、`local.css` 均为自写中文样式，不是官方同名文件；官方严格 profile 另有不可编辑的 `core.css`、`se.css`。[官方布局](https://github.com/standardebooks/manual/blob/master/2-filesystem.rst)

Markdown 文字底本保存在书籍根目录的 `md/`，纳入 Git，保留转录原文、页码表与原稿快照，供校勘核对。该目录与 `src/` 并列，不能加入 OPF、spine 或 EPUB；发行只收录 `src/` 出版源码，排除全部 Markdown 和 `editorial/`。底本可包含待剥离的现代附加材料，出版正文仍按下述古籍内容政策处理。EPUB runner 尚未实现。

EPUB 3 基线包括合法的 OCF 打包、可解析的 XHTML、OPF 元数据、完整 manifest、明确 spine，以及带导航语义的目录。初期以可重排横排为默认，竖排另设配置并验证阅读器支持；电子书正文必须可选择、检索。[EPUB 3.3](https://www.w3.org/TR/epub-33/)

人工校勘确认的最终 XHTML 是权威内容源。模型识别、版面分析与中间数据均保留来源关系，但不能直接覆盖已确认正文。缺字、异文和存疑内容应进入校勘记录；增补句读、文字规范化与原书内容分开记录。

卷、篇、章节以 `section` 或 `article` 组织，标题层级反映原书结构；ID 在全书范围内唯一。注释保留注释者与层次，采用注释引用及回链，图片提供文字说明，语言标签与 OPF 一致。spine 由明确的章节顺序生成并人工复核，不能依据文件名猜测。[XHTML 规则](https://github.com/standardebooks/manual/blob/master/5-general-xhtml-and-css-patterns.rst)、[spine 规则](https://github.com/standardebooks/manual/blob/master/9-metadata.rst)

OPF 记录古籍书名、原作作者及贡献者角色、语言、数字版本与更新时间，使用带作者或系列前缀的本项目标识符。现代扫描版出版社、ISBN、版权页、主编/点校者和共享 PDF 的说明保存在 raw 清单，不写入出版 OPF、版本说明或正文。现代点校说明与出版前言不自动进入古籍正文。系列采用 `belongs-to-collection`，以 `collection-type` 区分系列或套书，并记录实际作品次序；现代底本的全集卷次不自动复制为电子书系列信息。作者和系列分类是同一书籍的索引视图，不复制正文。[元数据规则](https://github.com/standardebooks/manual/blob/master/9-metadata.rst)

中文 profile 另定繁简、异体字、缺字、标点、夹注与字形策略。英语 titlecase、美式引号、断词、拼写现代化及英文可读性评分不能自动套用古籍；保留原文的决定应可追溯。[英语排版规则](https://github.com/standardebooks/manual/blob/master/8-typography.rst)

## 封面

封面使用 1400×2100 的 2:3 画布，形成自己的中文古籍视觉风格：默认以水墨、宣纸色、
疏淡留白和竖排题签表现作品主题。题签区只排古籍书名与作者；插画可少量排入必要的主题词，
例如对应的英文语法词与汉语解释，须准确、可读并在设计记录中说明。书名必须由支持繁体的字体
准确排入，不使用生图中不可控的文字作为权威书名。字体、字号和留白按缩略图及完整封面
检查，可随作品调整。参考 Standard Ebooks 的文件布局、尺寸和出版图片处理方式，
不强制套用其油画、League Spartan 或黑底白字版式。[官方封面规范](https://github.com/standardebooks/manual/blob/master/10-art-and-images.rst)

当前两本水墨封面采用楷体竖排：书名字形最大高 110px、竖向步进 142px，列中心 x=1110、
顶端 y=210；作者字形最大高 52px、步进 74px，列中心 x=950、顶端 y=650。
相同字号用于一列各字，字形在统一格中居中，保留至少 40px 画布边距，不加黑色标题区。

每本书的 `images/cover.source.png` 保留未改动的生成画，`images/cover.jpg` 是尺寸统一且
小于 1.5MB 的底画，`images/cover.svg` 保留可编辑书名与作者，`images/cover.preview.jpg`
是带字的完整预览。发行用 `src/epub/images/cover.svg` 嵌入底画，并将文字转为轮廓；
OPF 以 `cover-image` 指向这份 SVG，不依赖系统字体或外部图片路径。源画、提示词与设计
说明保存在书籍目录并纳入 Git，只有发行 SVG 进入出版 `src/`。

封面只长期保留最新版与最早油画版的源画、底画、源码、预览、发行图、实际提示词与设计记录。
中间版本、草案副本、试制图、检查日志和一次性脚本在新版核验后清理，不累积编号备份。
油画版平铺保存为 `images/cover-oil.*`，提示词与记录为 `editorial/cover-oil-*`。
`cover-oil.original.svg` 保留原始字节，`cover-oil.svg` 修正背景引用到 `cover-oil.jpg`，
便于编辑旧版；`cover-oil.epub.svg` 保存自包含的旧发行图。历史映射及 SHA-256 登记在
当前 `editorial/cover-design.md`，备选文件不进入出版 `src/`。

制作主题和构图直接在 `editorial/cover-design.md` 中拟定并维护最终设计，完整实际提示词保存为
`editorial/cover-prompt.txt`。不另存草案副本；验证使用的缓存副本完成检查后删除。

本次按用户要求使用助手内置生图能力制作原创封面画，生成内容是作品主题的象征性场景，
不作为底本影像或历史复原证据。Standard Ebooks 官方规则明确排除 AI 生成封面画，
水墨风格也区别于其指定的油画。因此本项目借鉴其文件布局和技术处理，采用自己的视觉
设计，属于本项目中文 profile，不能宣称严格符合
官方封面规则，也不冒用其标识。[官方封面画规则](https://github.com/standardebooks/manual/blob/master/10-art-and-images.rst)

Windows 开发环境可用仓库的 [封面编排工具](../tools/README.md) 创建这套封面文件；
它只处理尺寸、字体轮廓和 SVG/JPEG 编译，不调用模型或执行图片文字识别。

水墨插画中的书页文字与批注通过提示词和内置生图一起绘制，随纸面弯曲、透视及墨色变化，
形成相同的笔触与纸张渗化。不能用后期字体叠加代替场景文字。书名与作者题签仍由准确字体
独立编排，源 SVG 保留可编辑文字，发行 SVG 转为轮廓。场景文字保存在生成底画中，须直接
查看核对，并记录实际提示词和所用参考图；不视为原书页转录、出版正文或副标题。

下一阶段将接入结构、链接、目录与注释检查，再执行 EPUBCheck 并在目标阅读器验收。可选尝试 `se lint` 与 `se build --check`，按实际支持情况评估差异；后者调用 EPUBCheck、Nu，安装 Ace 时追加其检查。通过工具检查不能代替校勘和阅读器测试。[EPUBCheck](https://www.w3.org/publishing/epubcheck/)、[SE build](https://github.com/standardebooks/tools/blob/master/se/commands/build.py)

**当前 EPUB 发行阶段的检查 runner 尚未接入，尚未完成 EPUB 合规或阅读器验证。**
