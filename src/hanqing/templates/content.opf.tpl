<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="$language">
	<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
		<dc:identifier id="book-id">urn:hanqing:book:$book_id</dc:identifier>
		<dc:title>$title</dc:title>
		<dc:language>$language</dc:language>
$creators
$collections
		<meta property="dcterms:modified">$modified</meta>
	</metadata>
	<manifest>
		<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>
		<item id="core-css" href="css/core.css" media-type="text/css"/>
		<item id="local-css" href="css/local.css" media-type="text/css"/>
		<item id="titlepage" href="text/titlepage.xhtml" media-type="application/xhtml+xml"/>
		<item id="colophon" href="text/colophon.xhtml" media-type="application/xhtml+xml"/>
	</manifest>
	<spine>
		<itemref idref="titlepage"/>
		<itemref idref="colophon"/>
	</spine>
</package>
