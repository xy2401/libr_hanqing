"""阶段契约。这里不执行 OCR、网络请求或电子书构建。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    name: str
    purpose: str
    output: str
    gate: str


STAGES = (
    Stage("ingest", "从转运区登记底本与 SHA-256", "data/inbox/ → data/work/<source-set>/manifest.json", "原件经核验后归入工作区，保存原始字节"),
    Stage("prepare", "PDF 原始流提取 / 页面渲染 / EPUB 安全解包", "data/work/<source-set>/unpacked/", "物理页序与流哈希检查；流提取不等于页面渲染"),
    Stage("recognize", "逐页多模态识别，保留阅读顺序和疑点", "data/work/<source-set>/md.<work>/", "work 保留完整工作稿；books/md 保存确认的 Git 快照"),
    Stage("assemble", "把识别稿转为待校勘 XHTML 提案", "data/work/<source-set>/proposal.<book>/", "仅生成提案，人工接受后进入 books/<book>/src/"),
    Stage("proofread", "对照底本校勘正文与注释", "data/work/<source-set>/editorial.<work>/ + books/<book>/src/", "工作记录保存在 work；成品完成后逐项确认，疑点全部处理"),
    Stage("build", "仅从 src/ 出版源码打包候选电子书", "books/<book>/dist/", "固定构建输入；不依赖工作清单，排除 md/、Markdown 和校勘记录"),
    Stage("validate", "检查候选 EPUB、链接与中文排版", "books/<book>/dist/", "保存实际包与检查记录；EPUBCheck 与阅读器验收分别记录"),
    Stage("release", "保存验收通过的相同产物字节及发行说明", "books/<book>/dist/", "校勘证据有效，记录源码提交与产物哈希"),
)
