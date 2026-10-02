# 电子书制作规范

本项目参考 Standard Ebooks 的目录与编辑理念，采用自有 **hanqing Chinese profile**，发行目标为有效的 EPUB 3。该定位不代表严格通过官方制作规范，也不代表 Standard Ebooks 出版或认证。[官方手册](https://github.com/standardebooks/manual)

每本书使用 `images/` 保存选定的封面与插图素材，`src/META-INF/container.xml` 与 `src/mimetype` 表达容器结构，`src/epub/` 下分设 `text/`、`images/`、`css/`，并保存 `content.opf`、`toc.xhtml`。项目模板中的 `core.css`、`local.css` 均为自写中文样式，不是官方同名文件；官方严格 profile 另有不可编辑的 `core.css`、`se.css`。[官方布局](https://github.com/standardebooks/manual/blob/master/2-filesystem.rst)

EPUB 3 基线包括合法的 OCF 打包、可解析的 XHTML、OPF 元数据、完整 manifest、明确 spine，以及带导航语义的目录。初期以可重排横排为默认，竖排另设配置并验证阅读器支持；电子书正文必须可选择、检索。[EPUB 3.3](https://www.w3.org/TR/epub-33/)

人工校勘确认的最终 XHTML 是权威内容源。模型识别、版面分析与中间数据均保留来源关系，但不能直接覆盖已确认正文。缺字、异文和存疑内容应进入校勘记录；增补句读、文字规范化与原书内容分开记录。

卷、篇、章节以 `section` 或 `article` 组织，标题层级反映原书结构；ID 在全书范围内唯一。注释保留注释者与层次，采用注释引用及回链，图片提供文字说明，语言标签与 OPF 一致。spine 由明确的章节顺序生成并人工复核，不能依据文件名猜测。[XHTML 规则](https://github.com/standardebooks/manual/blob/master/5-general-xhtml-and-css-patterns.rst)、[spine 规则](https://github.com/standardebooks/manual/blob/master/9-metadata.rst)

OPF 记录书名、作者及贡献者角色、语言、版本、来源与更新时间，使用本项目标识符和出版说明。系列采用 `belongs-to-collection`，以 `collection-type` 区分系列或套书，并记录次序。作者和系列分类是同一书籍的索引视图，不复制正文。[元数据规则](https://github.com/standardebooks/manual/blob/master/9-metadata.rst)

中文 profile 另定繁简、异体字、缺字、标点、夹注与字形策略。英语 titlecase、美式引号、断词、拼写现代化及英文可读性评分不能自动套用古籍；保留原文的决定应可追溯。[英语排版规则](https://github.com/standardebooks/manual/blob/master/8-typography.rst)

下一阶段将接入结构、链接、目录与注释检查，再执行 EPUBCheck 并在目标阅读器验收。可选尝试 `se lint` 与 `se build --check`，按实际支持情况评估差异；后者调用 EPUBCheck、Nu，安装 Ace 时追加其检查。通过工具检查不能代替校勘和阅读器测试。[EPUBCheck](https://www.w3.org/publishing/epubcheck/)、[SE build](https://github.com/standardebooks/tools/blob/master/se/commands/build.py)

**当前以上检查均尚未接入，也未完成 EPUB 合规或阅读器验证。**
