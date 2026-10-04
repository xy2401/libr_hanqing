import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


PROCESSOR = Path(__file__).resolve().parents[1] / "tools" / "apply-markdown-revision.py"


class WorkingRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        processor = self.root / "tools/apply-markdown-revision.py"
        processor.parent.mkdir()
        processor.write_bytes(PROCESSOR.read_bytes())
        spec = importlib.util.spec_from_file_location("working_revision", processor)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.base = self.root / "data/raw/example"
        self.markdown = self.base / "md.example/chapter.md"
        self.editorial = self.base / "editorial.example"
        self.markdown.parent.mkdir(parents=True)
        self.editorial.mkdir()
        self.markdown.write_text("錯字\n", encoding="utf-8")
        self.page = self.base / "unpacked/page-0001.jpg"
        self.page.parent.mkdir()
        self.page.write_bytes(b"source-image-bytes")
        self.book = self.root / "books/author-example/src/chapter.xhtml"
        self.book.parent.mkdir(parents=True)
        self.book.write_bytes(b"accepted-text")
        self.manifest = self.base / "manifest.json"
        relation = {"book_id":"author-example","work_id":"example",
                    "markdown_directory":"data/raw/example/md.example",
                    "editorial_directory":"data/raw/example/editorial.example"}
        self.data = {"schema_version":3,"path_base":"project","source_set_id":"example","source_id":"source-one",
                     "books":[relation],"files":[self.module.artifact(self.root,self.markdown),self.module.artifact(self.root,self.page)]}
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")
        self.plan = self.editorial / "revision-plan.json"
        self.value = {"schema_version":1,"revision_id":"image-revision-example","scope":"one-verified-word",
                      "prompt":"Correct the verified transcription error.","operations":[{
                          "book_id":"author-example","path":"data/raw/example/md.example/chapter.md",
                          "expected_sha256":self.module.digest(self.markdown),"evidence_pages":[self.module.artifact(self.root,self.page)],
                          "reason":"verified-source-reading","finding_ids":["example-one"],
                          "edits":[{"old":"錯","new":"正","occurrences":1}]}]}
        self.save_plan()

    def save_plan(self):
        self.plan.write_text(json.dumps(self.value), encoding="utf-8")

    def test_stale_markdown_and_changed_evidence_refused_without_writes(self):
        self.markdown.write_text("another revision\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"Stale input"):
            self.module.apply(self.root,self.manifest,self.plan)
        self.assertFalse(list(self.markdown.parent.glob("*.original.md")))
        self.markdown.write_text("錯字\n",encoding="utf-8")
        self.page.write_bytes(b"changed-image")
        with self.assertRaisesRegex(ValueError,"Changed source image"):
            self.module.apply(self.root,self.manifest,self.plan)
        self.assertEqual(self.markdown.read_text(encoding="utf-8"),"錯字\n")
        self.assertFalse(list(self.markdown.parent.glob("*.original.md")))

    def test_recording_metadata_rejected_before_check_or_apply_writes(self):
        valid = json.loads(json.dumps(self.value))
        for field, operation in [("prompt", False), ("scope", False),
                                 ("reason", True), ("finding_ids", True)]:
            for check in (True, False):
                with self.subTest(field=field, check=check):
                    self.value = json.loads(json.dumps(valid))
                    target = self.value["operations"][0] if operation else self.value
                    del target[field]
                    self.save_plan()
                    before = {p.relative_to(self.root): p.read_bytes()
                              for p in self.root.rglob("*") if p.is_file()}
                    with self.assertRaisesRegex(ValueError, field):
                        self.module.apply(self.root, self.manifest, self.plan, check=check)
                    after = {p.relative_to(self.root): p.read_bytes()
                             for p in self.root.rglob("*") if p.is_file()}
                    self.assertEqual(after, before)

    def test_book_path_and_wrong_occurrence_count_refused(self):
        self.value["operations"][0]["path"]="books/author-example/src/chapter.xhtml"
        self.save_plan()
        with self.assertRaisesRegex(ValueError,"raw working directory"):
            self.module.apply(self.root,self.manifest,self.plan)
        self.value["operations"][0]["path"]="data/raw/example/md.example/chapter.md"
        self.value["operations"][0]["edits"][0]["occurrences"]=2
        self.save_plan()
        with self.assertRaisesRegex(ValueError,"Unexpected replacement count"):
            self.module.apply(self.root,self.manifest,self.plan)
        self.assertEqual(self.book.read_bytes(),b"accepted-text")

    def test_check_then_apply_preserves_snapshot_and_accepted_text(self):
        before_manifest=self.manifest.read_bytes()
        self.module.apply(self.root,self.manifest,self.plan,check=True)
        self.assertEqual(self.manifest.read_bytes(),before_manifest)
        self.module.apply(self.root,self.manifest,self.plan)
        self.assertEqual(self.markdown.read_text(encoding="utf-8"),"正字\n")
        self.assertEqual(next(self.markdown.parent.glob("*.original.md")).read_text(encoding="utf-8"),"錯字\n")
        self.assertEqual(self.book.read_bytes(),b"accepted-text")
        result=json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertFalse(result["working_revisions"][0]["accepted_xhtml_updated"])
        recorded_processor = result["working_revisions"][0]["processor"]
        self.assertEqual(recorded_processor["path"], "tools/apply-markdown-revision.py")
        self.assertEqual(recorded_processor["sha256"], self.module.digest(self.root / recorded_processor["path"]))
        self.assertEqual(result["books"][0]["publication_plan_working_input_status"],"stale-after-working-revision")

    def use_text_plan(self):
        self.value["method"] = "existing-markdown-context"
        operation = self.value["operations"][0]
        del operation["evidence_pages"]
        operation["text_evidence"] = [{**self.module.artifact(self.root, self.markdown),
                                       "id": "internal-example", "quote": "錯字"}]
        operation["edits"][0].update(reason="Explicit internal comparison", evidence_ids=["internal-example"])
        self.save_plan()

    def test_text_revision_records_quotes_and_before_snapshot_without_image_claim(self):
        self.use_text_plan()
        self.module.apply(self.root, self.manifest, self.plan)
        result = json.loads(self.manifest.read_text(encoding="utf-8"))
        revision = result["working_revisions"][0]
        record = revision["records"][0]
        self.assertEqual(revision["method"], "existing-markdown-context")
        self.assertEqual(record["category"], "text-based-working-revision")
        self.assertNotIn("evidence_pages", record)
        evidence = record["text_evidence"][0]
        snapshot = self.root / evidence["input_snapshot"]["path"]
        self.assertEqual(self.module.digest(snapshot), evidence["sha256"])
        self.assertIn(evidence["quote"], snapshot.read_text(encoding="utf-8"))
        self.assertEqual(self.book.read_bytes(), b"accepted-text")

    def test_text_revision_rejects_missing_or_stale_basis_and_bulk_replacement(self):
        self.use_text_plan()
        operation = self.value["operations"][0]
        for change, message in [
            (lambda: operation["text_evidence"][0].update(quote="absent phrase"), "quote is missing"),
            (lambda: operation["text_evidence"][0].update(quote="錯字", sha256="0" * 64), "Changed text evidence"),
            (lambda: operation.update(replacement={"path": "unused"}), "explicit edits"),
        ]:
            change()
            self.save_plan()
            with self.assertRaisesRegex(ValueError, message):
                self.module.apply(self.root, self.manifest, self.plan)
        self.assertEqual(self.markdown.read_text(encoding="utf-8"), "錯字\n")
        self.assertFalse(list(self.markdown.parent.glob("*.original.md")))

    def test_text_revision_requires_edit_to_reference_known_evidence(self):
        self.use_text_plan()
        self.value["operations"][0]["edits"][0]["evidence_ids"] = ["unknown-basis"]
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "reference its evidence"):
            self.module.apply(self.root, self.manifest, self.plan)
        self.assertFalse(list(self.markdown.parent.glob("*.original.md")))


if __name__ == "__main__":
    unittest.main()
