# 本地数据区

`raw/<book-id>/<source-id>/` 保存下载的原始 PDF/EPUB，保持原始字节；
`work/<book-id>/<run-id>/` 保存解包、渲染页图、模型响应、待校勘提案和检查报告；
`cache/` 保存可重建缓存。这三个目录均被 Git 忽略，使用时由后续命令创建。

忽略意味着数据不会随 Git 备份。原始底本应另做本地或对象存储备份；来源地址、
SHA-256 和底本说明记录在可提交的 `books/<book-id>/book.toml`。
