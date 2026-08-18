from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tc_ai_bridge.paratext_notes import (
    COMMENT_CHILD_ORDER,
    append_paratext_note,
    validate_comment_list,
    validate_notes_11,
    convert_comment_list_to_notes_11,
)


class ParatextCommentListTests(unittest.TestCase):
    """Keep regression coverage for the user's real CommentList export while using Notes 1.1 for sync."""

    def _write_sample_commentlist(self, p: Path):
        root=ET.Element('CommentList')
        c=ET.SubElement(root,'Comment',{'Thread':'8a14411f','User':'Yesu Selva Benz','VerseRef':'JOS 3:4','Language':'ta','Date':'2025-10-21T14:40:12.9545534+05:30'})
        for tag,text in [
            ('SelectedText','3,000 அடிகள்'),('StartPosition','27'),('ContextBefore','\\v 4 உங்களுக்கும் அதற்கும் '),('ContextAfter',' தூரம்'),
            ('Status',''),('Type',''),('ConflictType','unknownConflictType'),('Verse','\\v 4 உங்களுக்கும் அதற்கும் 3,000 அடிகள் தூரம்'),
            ('ReplyToUser',''),('HideInTextWindow','false'),('Contents','ஒரு கிலோமீட்டர்')]:
            ET.SubElement(c,tag).text=text
        ET.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)

    def test_supplied_commentlist_pattern_remains_readable(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'export.xml'; self._write_sample_commentlist(p)
            info=validate_comment_list(p)
            self.assertEqual(info['format'],'CommentList'); self.assertEqual(info['comments'],1)

    def test_commentlist_can_migrate_to_official_notes_11(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'export.xml'; dst=Path(td)/'Notes_AI_Suggestion.xml'; self._write_sample_commentlist(src)
            convert_comment_list_to_notes_11(src,dst)
            info=validate_notes_11(dst)
            self.assertEqual(info['format'],'Paratext Notes 1.1'); self.assertEqual(info['threads'],1)
            root=ET.parse(dst).getroot(); thread=root.find('thread'); sel=thread.find('selection'); comment=thread.find('comment')
            self.assertEqual(sel.attrib['selectedText'],'3,000 அடிகள்')
            self.assertEqual(sel.attrib['startPos'],'27')
            self.assertEqual(comment.attrib['extUser'],'AI Suggestion')
            self.assertEqual(comment.findtext('content'),'ஒரு கிலோமீட்டர்')

    def test_notes_11_writer_appends_distinct_threads(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Notes_AI_Suggestion.xml'
            _,a=append_paratext_note(p,book_id='JOS',chapter=3,verse=4,verse_text='ஒரு சோதனை வசனம்',comment_text='First',reviewer='Member A',selected_text='சோதனை')
            _,b=append_paratext_note(p,book_id='JOS',chapter=3,verse=4,verse_text='ஒரு சோதனை வசனம்',comment_text='Second',reviewer='Member A',selected_text='வசனம்')
            root=ET.parse(p).getroot(); threads=root.findall('thread')
            self.assertEqual(len(threads),2)
            self.assertEqual(threads[0].attrib['id'],a); self.assertEqual(threads[1].attrib['id'],b)
            self.assertEqual(threads[0].find('comment').attrib['extUser'],'AI Suggestion')

    def test_child_order_definition_covers_optional_commentlist_fields(self):
        self.assertIn('AssignedUser',COMMENT_CHILD_ORDER)
        self.assertIn('TagAdded',COMMENT_CHILD_ORDER)
        self.assertIn('TagRemoved',COMMENT_CHILD_ORDER)
        self.assertLess(COMMENT_CHILD_ORDER.index('Verse'),COMMENT_CHILD_ORDER.index('ReplyToUser'))
        self.assertLess(COMMENT_CHILD_ORDER.index('HideInTextWindow'),COMMENT_CHILD_ORDER.index('Contents'))


if __name__=='__main__':
    unittest.main()
