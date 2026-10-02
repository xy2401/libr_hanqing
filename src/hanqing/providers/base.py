"""未来多模态适配器共同实现的契约，尚无供应商实现。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

BlockKind = Literal["heading", "main", "annotation", "page-number", "seal", "illustration", "other"]


@dataclass(frozen=True)
class RecognitionRequest:
    source_id: str
    physical_page: int  # 文件中从 1 开始的页序，区别于原书版心页码。
    page_image: Path
    input_sha256: str
    prompt_version: str


@dataclass(frozen=True)
class TextBlock:
    id: str
    kind: BlockKind
    reading_order: int
    text: str
    bbox: tuple[float, float, float, float]  # 相对整页的 x0,y0,x1,y1，范围 0..1。
    uncertainties: tuple[str, ...] = ()


@dataclass(frozen=True)
class PageTranscription:
    source_id: str
    physical_page: int
    printed_page_label: str
    blocks: tuple[TextBlock, ...]
    warnings: tuple[str, ...] = ()


class RecognitionProvider(Protocol):
    def recognize_page(self, request: RecognitionRequest) -> PageTranscription:
        """返回待复核识别稿；不能把模型输出直接标记为已校勘。"""
        ...
