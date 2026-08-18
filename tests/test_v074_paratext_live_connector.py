from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tc_ai_bridge.paratext_connector import ConnectorState, ParatextConnectorClient
from tc_ai_bridge.paratext_notes import append_paratext_note, iter_notes_11, normalized_notes_11_copy

ROOT = Path(__file__).resolve().parent.parent
CONNECTOR = ROOT / 'paratext_connector'


class V074ParatextConnectorCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = (CONNECTOR / 'AiBridgeConnectorPlugin.cs').read_text('utf-8')
        cls.pipe = (CONNECTOR / 'NamedPipeBridgeServer.cs').read_text('utf-8')
        cls.protocol = (CONNECTOR / 'BridgeProtocol.cs').read_text('utf-8')
        cls.build = (CONNECTOR / 'build_connector.ps1').read_text('utf-8')
        cls.install = (CONNECTOR / 'install_connector.ps1').read_text('utf-8')

    def test_v075_app_retains_074_paratext_connector_compatibility(self):
        self.assertEqual((ROOT / 'VERSION').read_text('utf-8').strip(), '0.7.5')
        self.assertIn("__version__ = '0.7.5'", (ROOT / 'tc_ai_bridge/__init__.py').read_text('utf-8'))
        self.assertIn('#define MyAppVersion "0.7.5"', (ROOT / 'installer/translationCore-AI-Bridge.iss').read_text('utf-8'))
        self.assertIn('PluginVersion = "0.7.4"', self.plugin)

    def test_plugin_is_automatic_startup_plugin_and_subscribes_live_events(self):
        self.assertIn('IParatextStartupAutomaticPlugin', self.plugin)
        self.assertIn('_host.VerseRefChanged += OnVerseRefChanged', self.plugin)
        self.assertIn('_host.ActiveWindowSelectionChanged += OnActiveWindowSelectionChanged', self.plugin)
        self.assertIn('_host.ShuttingDown += OnShuttingDown', self.plugin)

    def test_connector_protocol_exposes_only_safe_live_actions(self):
        self.assertIn('action == "get_state"', self.plugin)
        self.assertIn('action == "set_reference"', self.plugin)
        self.assertIn('action == "create_note"', self.plugin)
        for dangerous in ('put_usfm', 'put_usx', 'write_scripture', 'delete_note', 'resolve_note'):
            self.assertNotIn('action == "' + dangerous + '"', self.plugin.lower())

    def test_connector_contains_no_scripture_write_api_call(self):
        for dangerous in ('PutUSFM(', 'PutUSX(', 'PutUSFMTokens('):
            self.assertNotIn(dangerous, self.plugin)
        self.assertIn('Scripture writing is disabled', self.plugin)

    def test_live_notes_use_official_project_notes_write_scope(self):
        self.assertIn('WriteLockScope.ProjectNotes', self.plugin)
        self.assertIn('project.RequestWriteLock', self.plugin)
        self.assertIn('project.AddNote', self.plugin)
        self.assertIn('CommentParagraph', self.plugin)
        self.assertIn('FormattedString', self.plugin)
        self.assertIn('noteAuthor = _host.UserInfo', self.plugin)
        self.assertIn('Project Note AUTHOR failed', self.plugin)
        self.assertIn('Project Note WRITE_LOCK failed', self.plugin)
        self.assertIn('Project Note ADD_NOTE failed', self.plugin)

    def test_live_note_anchor_is_exact_or_fails_closed_on_ambiguity(self):
        self.assertIn('FindMatchingScriptureSelections', self.plugin)
        self.assertIn('GetScriptureSelectionForVerse', self.plugin)
        self.assertIn('The selected text occurs more than once in this verse', self.plugin)
        self.assertIn('Select the exact occurrence inside Paratext', self.plugin)

    def test_reference_parsing_is_delegated_to_paratext_versification(self):
        self.assertIn('Versification.CreateReference(text)', self.plugin)
        self.assertIn('Versification.CreateReference(referenceText)', self.plugin)
        self.assertNotIn('BookNumber', self.plugin)
        self.assertNotIn('TryParseReference', self.plugin)

    def test_transport_is_windows_local_named_pipe_not_tcp_or_http(self):
        self.assertIn('NamedPipeServerStream', self.pipe)
        self.assertIn('translationCoreAIBridge', self.pipe)
        combined = (self.pipe + self.plugin).lower()
        self.assertNotIn('tcplistener', combined)
        self.assertNotIn('httplistener', combined)
        self.assertNotIn('http://', combined)
        self.assertNotIn('https://', combined)

    def test_windows_builder_compiles_against_installed_plugininterfaces(self):
        self.assertIn('Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe', self.build)
        self.assertIn('PluginInterfaces', self.build)
        self.assertIn('/target:library', self.build)
        self.assertIn('/platform:anycpu', self.build)
        self.assertIn('.ptxplg', self.build)

    def test_windows_builder_resolves_modern_paratext_core_interface_dependency(self):
        self.assertIn('CorePluginInterfaces.dll', self.build)
        self.assertIn('ParatextCorePluginInterfaces.dll', self.build)
        self.assertIn('GetReferencedAssemblies()', self.build)
        self.assertIn("'CorePluginInterfaces'", self.build)
        self.assertIn('$coreDependencyName', self.build)

    def test_windows_builder_always_surfaces_csc_diagnostics(self):
        self.assertIn('$compilerOutput = @(& $Csc @compileArgs 2>&1)', self.build)
        self.assertIn('C# compiler diagnostics:', self.build)
        self.assertIn('complete compiler diagnostics are printed immediately above', self.build)
        self.assertNotIn("$output = & (Join-Path $Here 'build_connector.ps1')", self.install)

    def test_installer_requires_paratext_closed_and_installs_plugin_extension(self):
        self.assertIn("Get-Process -Name 'Paratext'", self.install)
        self.assertIn('Close Paratext completely', self.install)
        self.assertIn("plugins\\translationCoreAIBridge", self.install)
        self.assertIn('translationCoreAIBridge.ptxplg', self.install)

    def test_windows_packager_carries_connector_and_start_menu_tools(self):
        exe = (ROOT / 'build_windows_exe.bat').read_text('utf-8')
        iss = (ROOT / 'installer/translationCore-AI-Bridge.iss').read_text('utf-8')
        self.assertIn('--add-data "paratext_connector;paratext_connector"', exe)
        self.assertIn('Install Paratext Live Connector', iss)
        self.assertIn('Uninstall Paratext Live Connector', iss)

    def test_python_client_state_and_note_payload_are_live_project_aware(self):
        client = ParatextConnectorClient()
        response = {
            'ok': True, 'user': 'Reviewer', 'project_name': 'Tamil', 'project_id': 'guid-1',
            'project_language': 'Tamil', 'reference': 'GEN 1:1', 'selected_text': 'ஆதியிலே',
            'selection_reference': 'GEN 1:1', 'before_context': '', 'after_context': ' தேவன்',
            'selection_offset': 0, 'sync_group': 'A', 'paratext_version': '9.5.110.1',
            'plugin_version': '0.7.4', 'state_revision': 9, 'last_event': 'selection_changed',
            'last_origin_id': '', 'capabilities': ['state','navigation','selection','project_notes']
        }
        with patch.object(client, '_exchange', return_value=response) as x:
            state = client.get_state()
        self.assertEqual(state.project_id, 'guid-1')
        self.assertEqual(state.selected_text, 'ஆதியிலே')
        self.assertEqual(state.paratext_version, '9.5.110.1')
        self.assertEqual(state.plugin_version, '0.7.4')
        with patch.object(client, '_exchange', return_value={'ok': True}) as x:
            client.create_note('GEN 1:1','ஆதியிலே','Review',project_id='guid-1',before_context='',after_context=' தேவன்')
            action, payload = x.call_args.args
        self.assertEqual(action, 'create_note')
        self.assertEqual(payload['project_id'], 'guid-1')
        self.assertEqual(payload['external_author'], 'AI Suggestion')
        self.assertEqual(payload['selected_text'], 'ஆதியிலே')


    def test_notes_export_uses_real_paratext_user_and_keeps_ai_as_external_source(self):
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'Notes_AI_Suggestion.xml'; dst=Path(td)/'export.xml'
            append_paratext_note(src,book_id='GEN',chapter=1,verse=1,verse_text='ஆதியிலே தேவன்',comment_text='Review this',reviewer='AI Bridge Reviewer',selected_text='ஆதியிலே')
            normalized_notes_11_copy(src,dst,paratext_user='Yesu Selva Benz')
            comment=ET.parse(dst).getroot().find('thread').find('comment')
            self.assertEqual(comment.attrib['user'],'Yesu Selva Benz')
            self.assertEqual(comment.attrib['extUser'],'AI Suggestion')
            # The companion source is preserved; normalization is export-only.
            original=ET.parse(src).getroot().find('thread').find('comment')
            self.assertEqual(original.attrib['user'],'AI Bridge Reviewer')

    def test_notes11_threads_are_connector_ready_and_fingerprinted(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'Notes_AI_Suggestion.xml'
            append_paratext_note(src,book_id='GEN',chapter=1,verse=1,verse_text='ஆதியிலே தேவன்',comment_text='Review this',reviewer='Member',selected_text='ஆதியிலே')
            items=iter_notes_11(src)
            self.assertEqual(len(items),1)
            self.assertEqual(items[0]['reference'],'GEN 1:1')
            self.assertEqual(items[0]['selected_text'],'ஆதியிலே')
            self.assertEqual(items[0]['content'],'Review this')
            self.assertEqual(len(items[0]['fingerprint']),64)
            self.assertFalse(items[0]['unsupported_reason'])

    def test_primary_verify_and_sync_ui_use_local_connector_not_registry_data_access(self):
        ui=(ROOT/'tc_ai_bridge/ui.py').read_text('utf-8')
        verify=ui[ui.index('    def _verify_paratext_project(self):'):ui.index('    def _sync_paratext_notes(self):')]
        sync=ui[ui.index('    def _sync_paratext_notes(self):'):ui.index('    def _recover_transactions(self):')]
        self.assertIn('_probe_paratext_connector',verify)
        self.assertIn('state.user',verify)
        self.assertNotIn('ParatextDataAccessClient',verify)
        self.assertIn('self.paratext_connector.create_note',sync)
        self.assertIn('Paratext will record the real current Paratext user',sync)
        self.assertNotIn('ParatextDataAccessClient',sync)



class ResponsiveUITests(unittest.TestCase):
    def setUp(self):
        from tc_ai_bridge.ui import BridgeApp
        self.tmp = tempfile.TemporaryDirectory()
        self.app = BridgeApp(settings_path=Path(self.tmp.name) / 'settings.json')
        self.app.withdraw(); self.app.update_idletasks()

    def tearDown(self):
        try: self.app.destroy()
        except Exception: pass
        self.tmp.cleanup()

    def _labels(self, widget):
        out=[]
        for child in widget.winfo_children():
            try: out.append(str(child.cget('text')))
            except Exception: pass
            out.extend(self._labels(child))
        return out

    def test_paratext_live_connector_controls_are_present_and_compact(self):
        labels='\n'.join(self._labels(self.app.production_tab))
        for text in ('Paratext · Live Connector + Project Notes','Connect / Refresh','Verify / Bind Project',
                     'Sync Notes','Export Notes XML…','Sync verse navigation','Auto-send review notes'):
            self.assertIn(text, labels)
        # One-time/diagnostic and duplicate note actions do not belong in the daily Production page.
        for text in ('Install Connector…','Bind Active Project','Create Live Note…','Verify Paratext Project…',
                     'Sync to Paratext…','Export Paratext Notes…','Sync Notes to Paratext…'):
            self.assertNotIn(text, labels)

    def test_production_page_has_vertical_scroll_and_stacks_on_small_screens(self):
        self.assertTrue(hasattr(self.app,'production_scroll_canvas'))
        self.app._layout_production_columns(True)
        left=self.app.production_left.grid_info(); right=self.app.production_right.grid_info()
        self.assertEqual((int(left['row']),int(left['column'])),(0,0))
        self.assertEqual((int(right['row']),int(right['column'])),(1,0))
        self.app._reflow_toolbar(self.app.production_toolbar,self.app.production_toolbar_widgets,2)
        rows={int(w.grid_info()['row']) for w in self.app.production_toolbar_widgets}
        self.assertGreater(max(rows),0)

    def test_live_project_binding_blocks_wrong_paratext_project(self):
        self.app.project = SimpleNamespace(path=Path(self.tmp.name)/'tc_project', book_id='gen', name='Genesis')
        self.app.project.path.mkdir(exist_ok=True)
        state=ConnectorState(connected=True,project_id='paratext-A',project_name='Tamil IRV')
        self.assertEqual(self.app._live_paratext_binding(state)[1],'unbound')
        self.app.settings.set_paratext_project_guid(self.app._paratext_project_key(),'paratext-A')
        self.assertEqual(self.app._live_paratext_binding(state)[1],'matched')
        wrong=ConnectorState(connected=True,project_id='paratext-B',project_name='Other project')
        self.assertEqual(self.app._live_paratext_binding(wrong)[1],'mismatch')
        with self.assertRaises(Exception): self.app._require_live_paratext_binding(wrong)


if __name__ == '__main__':
    unittest.main()
