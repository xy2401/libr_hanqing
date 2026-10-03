"""阶段契约。这里不执行 OCR、网络请求或电子书构建。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    name: str
    purpose: str
    output: str
    gate: str


STAGES = (
    Stage("ingest", "登记底本与 SHA-256", "data/raw/<source-set>/manifest.json", "来源信息仅保存在 raw，保存原始字节"),
    Stage("prepare", "PDF 渲染 / EPUB 安全解包并判定内容类型", "data/raw/<source-set>/unpacked/", "页数、页序与文件路径检查"),
    Stage("recognize", "逐页多模态识别，保留阅读顺序和疑点", "books/<book>/md/", "文字底本纳入 Git，来源可追踪；manifest.json 定义书籍关系"),
    Stage("assemble", "把识别稿转为待校勘 XHTML 提案", "data/raw/<source-set>/proposal.<book>/", "仅生成提案，人工接受后进入 books/<book>/src/"),
    Stage("proofread", "对照底本校勘正文与注释", "books/<book>/src/ + editorial/", "人工复核、覆盖页检查、疑点全部处理"),
    Stage("build", "仅从 src/ 出版源码打包候选电子书", "data/raw/<source-set>/build.<book>/", "固定构建输入；排除 md/、Markdown 和校勘记录"),
    Stage("validate", "检查候选 EPUB、链接与中文排版", "data/raw/<source-set>/validation.<book>/", "EPUBCheck 与阅读器验收通过"),
    Stage("release", "将验收通过的相同字节保存为发行产物", "dist/<book>/<revision>/", "校勘证据有效，记录源码提交与产物哈希"),
)
