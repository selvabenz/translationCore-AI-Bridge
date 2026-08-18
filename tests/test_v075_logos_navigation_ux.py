from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tc_ai_bridge.logos_connector import (
    LogosConnectorError,
    bridge_to_logos_reference,
    logos_state_to_bridge_reference,
    _USFM_TO_LOGOS,
    _LOGOS_ABBR_TO_USFM,
)
from tc_ai_bridge.navigation import NavigationBroker, NavigationOwnership, normalize_reference
from tc_ai_bridge.secret_store import AppSettings
from tc_ai_bridge.ui import BridgeApp, _CollapsibleSection

ROOT = Path(__file__).resolve().parents[1]


class V075CoreTests(unittest.TestCase):
    def test_v075_real_tk_ui_tests_are_isolated_in_windows_certification(self):
        s=(ROOT/'tests'/'run_windows_certification.py').read_text('utf-8')
        self.assertIn("or '.V075UITests.' in test_id",s)

    def test_version_and_windows_packaging_are_075_and_include_logos_helper(self):
        self.assertEqual((ROOT / 'VERSION').read_text('utf-8').strip(), '0.7.5')
        self.assertIn("__version__ = '0.7.5'", (ROOT / 'tc_ai_bridge/__init__.py').read_text('utf-8'))
        iss=(ROOT/'installer'/'translationCore-AI-Bridge.iss').read_text('utf-8')
        self.assertIn('#define MyAppVersion "0.7.5"',iss)
        build=(ROOT/'build_windows_exe.bat').read_text('utf-8')
        self.assertIn('--add-data "logos_connector;logos_connector"',build)
        self.assertIn('translationCore-AI-Bridge-v0.7.5',build)

    def test_logos_helper_is_ascii_safe_for_windows_powershell_51(self):
        # Windows PowerShell 5.1 treats UTF-8-without-BOM scripts as the active ANSI
        # code page. Keep this helper ASCII-only so symbols such as arrows cannot
        # become mojibake and break parsing on a real Windows machine.
        raw=(ROOT/'logos_connector'/'logos_bridge.ps1').read_bytes()
        self.assertTrue(raw)
        self.assertTrue(all(b < 128 for b in raw), 'logos_bridge.ps1 must remain ASCII-only for Windows PowerShell 5.1')
        self.assertNotIn(b'\xef\xbb\xbf', raw[:3])

    def test_logos_client_captures_helper_stderr_instead_of_discarding_it(self):
        s=(ROOT/'tc_ai_bridge'/'logos_connector.py').read_text('utf-8')
        self.assertIn('stderr=subprocess.PIPE',s)
        self.assertIn("PowerShell: ' + detail",s)
        self.assertNotIn('stderr=subprocess.DEVNULL',s)

    def test_logos_helper_recreates_stale_com_launcher_after_logos_restart(self):
        s=(ROOT/'logos_connector'/'logos_bridge.ps1').read_text('utf-8')
        # COM objects are held by the typed C# shim and cleared/recreated after a stale call.
        self.assertIn('private static void ResetComObjects()',s)
        self.assertIn('_application = null;',s)
        self.assertIn('_launcher = null;',s)
        self.assertGreaterEqual(s.count('ReadApplication()'),2)

    def test_logos_helper_uses_imported_typed_com_interfaces_and_has_no_network_or_scripture_write(self):
        s=(ROOT/'logos_connector'/'logos_bridge.ps1').read_text('utf-8')
        # Fix 5 imports the installed Logos type library in memory, then discovers the actual
        # COM interfaces supported by each RCW via QueryInterface. This avoids assuming that
        # TypeLibConverter emitted members on a particular coclass/type name.
        self.assertIn('TypeLibConverter',s)
        self.assertIn('LoadTypeLibEx',s)
        self.assertIn('Marshal.QueryInterface',s)
        self.assertIn('CompatibleInterfaces',s)
        self.assertIn('FindProperty',s)
        self.assertIn('FindMethod',s)
        self.assertIn('GetOpenPanels',s)
        self.assertIn('GetCurrentReferencesAndHeadwords',s)
        self.assertIn('CreateNavigationRequest',s)
        self.assertIn('GetDataType',s)
        self.assertIn('ParseReference',s)
        self.assertNotIn('class LogosRawDispatch',s)
        self.assertNotIn('IDispatchNative',s)
        # Do not regress to exact imported-type assumptions such as LogosLauncher.Application.
        self.assertNotIn('Get(launcher, "LogosLauncher", "Application")',s)
        self.assertNotIn('Get(app, "LogosApplication", "ApiVersion")',s)
        low=s.lower()
        for forbidden in ('tcplistener','httplistener','http://','https://','password','api_key','write_scripture','putusfm'):
            self.assertNotIn(forbidden,low)

    def test_logos_interop_is_in_memory_and_never_reports_a_phantom_cached_dll(self):
        s=(ROOT/'logos_connector'/'logos_bridge.ps1').read_text('utf-8')
        self.assertIn('in-memory TypeLibConverter',s)
        self.assertIn('Interop.Logos4Lib.InMemory.dll',s)
        self.assertNotIn('Interop.Logos4Lib." + fingerprint',s)
        self.assertNotIn('logosInterop',s)
        self.assertNotIn('interop_path',s)
        self.assertIn('logos_com_path',s)

    def test_logos_helper_exposes_runtime_interface_diagnostic_action(self):
        s=(ROOT/'logos_connector'/'logos_bridge.ps1').read_text('utf-8')
        self.assertIn('public static Dictionary<string, object> Diagnose()',s)
        self.assertIn("'diagnose' {",s)
        self.assertIn('launcher_interfaces',s)
        self.assertIn('application_interfaces',s)

    def test_logos_state_distinguishes_detection_from_navigation_readiness(self):
        from tc_ai_bridge.logos_connector import LogosConnectorClient
        degraded=LogosConnectorClient._state({'detected':True,'connected':False,'navigation_ready':False,'api_version':0,'message':'COM unavailable'})
        self.assertTrue(degraded.detected); self.assertFalse(degraded.connected); self.assertFalse(degraded.navigation_ready)
        ready=LogosConnectorClient._state({'detected':True,'connected':True,'navigation_ready':True,'api_version':3,'book_abbrev':'Ge','chapter':'1','verse':'5'})
        self.assertTrue(ready.detected); self.assertTrue(ready.connected); self.assertTrue(ready.navigation_ready); self.assertEqual(ready.reference,'GEN 1:5')

    def test_all_standard_66_books_have_unique_bidirectional_mapping(self):
        # The first Logos release is intentionally fail-closed outside the standard 66-book set.
        self.assertEqual(len(_USFM_TO_LOGOS),66)
        self.assertEqual(len(_LOGOS_ABBR_TO_USFM),66)
        self.assertEqual(set(_USFM_TO_LOGOS),set(_LOGOS_ABBR_TO_USFM.values()))
        self.assertEqual(len(set(_USFM_TO_LOGOS.values())),66)
        self.assertEqual(len(set(k.lower() for k in _LOGOS_ABBR_TO_USFM)),66)

    def test_standard_book_mapping_in_both_directions(self):
        cases={
            'GEN 1:5':'Genesis 1:5',
            'PSA 23:4':'Psalms 23:4',
            '1SA 17:4':'1 Samuel 17:4',
            '2KI 5:1':'2 Kings 5:1',
            'MAT 5:3':'Matthew 5:3',
            'REV 22:21':'Revelation 22:21',
        }
        for source,expected in cases.items():
            self.assertEqual(bridge_to_logos_reference(source),expected)
        reverse=[('Ge','1','5','GEN 1:5'),('Ps','23','4','PSA 23:4'),('1Sa','17','4','1SA 17:4'),('Mt','5','3','MAT 5:3'),('Re','22','21','REV 22:21')]
        for book,ch,vs,expected in reverse:
            self.assertEqual(logos_state_to_bridge_reference(book,ch,vs),expected)
        self.assertEqual(logos_state_to_bridge_reference('Ge','1','5a'),'GEN 1:5a')

    def test_invalid_or_noncanonical_reference_fails_closed(self):
        for bad in ('', 'Genesis 1:1', 'XYZ 1:1', 'GEN 0', 'GEN 1:title'):
            with self.subTest(bad=bad):
                with self.assertRaises(LogosConnectorError):
                    bridge_to_logos_reference(bad)
        self.assertEqual(logos_state_to_bridge_reference('Unknown','1','1'),'')
        self.assertEqual(normalize_reference('not a ref'),'')

    def test_navigation_broker_suppresses_connector_echoes_and_duplicate_polls(self):
        now=[100.0]
        broker=NavigationBroker(echo_window_seconds=2.5,clock=lambda:now[0])
        broker.set_bridge_reference('GEN 1:5')
        broker.record_outbound('paratext','GEN 1:5','p1')
        broker.record_outbound('logos','GEN 1:5','l1')
        self.assertIsNone(broker.new_event('GEN 1:5','paratext'))
        self.assertIsNone(broker.new_event('GEN 1:5','logos'))
        now[0]+=3.0
        # Same unchanged state remains a duplicate poll even after the echo window.
        self.assertIsNone(broker.new_event('GEN 1:5','logos'))
        event=broker.new_event('GEN 1:6','logos')
        self.assertIsNotNone(event); self.assertEqual(event.reference,'GEN 1:6'); self.assertEqual(event.origin,'logos')
        self.assertIsNone(broker.new_event('GEN 1:6','logos'))
        event=broker.new_event('GEN 1:7','paratext')
        self.assertIsNotNone(event); self.assertEqual(event.origin,'paratext')

    def test_navigation_broker_ignores_stale_pre_navigation_poll_then_accepts_user_change_after_confirmation(self):
        now=[10.0]; broker=NavigationBroker(settling_window_seconds=1.4,clock=lambda:now[0])
        broker.set_bridge_reference('GEN 1:5')
        broker.observe_state('logos','GEN 1:5')
        broker.record_outbound('logos','GEN 1:6','to-6')
        # Logos can still expose its old panel reference briefly after Navigate().
        self.assertIsNone(broker.new_event('GEN 1:5','logos'))
        now[0]+=.65
        self.assertIsNone(broker.new_event('GEN 1:5','logos'))
        # Confirmation of the requested reference remains an echo, not a new event.
        self.assertIsNone(broker.new_event('GEN 1:6','logos'))
        # Once confirmed, a different Logos reference can immediately be a human change.
        now[0]+=.05
        event=broker.new_event('GEN 1:7','logos')
        self.assertIsNotNone(event); self.assertEqual(event.reference,'GEN 1:7')

    def test_navigation_broker_does_not_suppress_different_reference_forever_if_outbound_never_confirms(self):
        now=[20.0]; broker=NavigationBroker(settling_window_seconds=1.0,clock=lambda:now[0])
        broker.set_bridge_reference('GEN 1:5')
        broker.observe_state('logos','GEN 1:8')
        broker.record_outbound('logos','GEN 1:6','to-6')
        self.assertIsNone(broker.new_event('GEN 1:8','logos'))
        now[0]+=1.01
        event=broker.new_event('GEN 1:8','logos')
        self.assertIsNotNone(event); self.assertEqual(event.reference,'GEN 1:8')

    def test_navigation_broker_accepts_new_user_change_even_when_other_connector_has_outbound(self):
        now=[1.0]; broker=NavigationBroker(clock=lambda:now[0])
        broker.set_bridge_reference('GEN 1:1')
        broker.record_outbound('logos','GEN 1:1','old')
        event=broker.new_event('GEN 1:2','logos')
        self.assertIsNotNone(event); self.assertEqual(event.reference,'GEN 1:2')
        broker.record_outbound('paratext','GEN 1:2','forwarded')
        self.assertIsNone(broker.new_event('GEN 1:2','paratext'))

    def test_rejected_external_event_rolls_back_and_retries_only_after_context_changes(self):
        broker=NavigationBroker()
        broker.set_bridge_reference('GEN 1:5')
        event=broker.new_event('GEN 1:8','logos',context='project-a|dirty')
        self.assertIsNotNone(event); self.assertEqual(broker.current_reference,'GEN 1:8')
        broker.reject_event(event,'GEN 1:5',context='project-a|dirty')
        self.assertEqual(broker.current_reference,'GEN 1:5')
        # Repeated polling must not nag while the reason for rejection is unchanged.
        self.assertIsNone(broker.new_event('GEN 1:8','logos',context='project-a|dirty'))
        # Saving/discarding work or selecting a different project changes context and allows retry.
        retry=broker.new_event('GEN 1:8','logos',context='project-a|clean')
        self.assertIsNotNone(retry); broker.commit_event(retry)
        self.assertEqual(broker.current_reference,'GEN 1:8')

    def test_navigation_ownership_uses_named_windows_mutex_and_is_idempotent(self):
        owner=NavigationOwnership()
        self.assertTrue(owner.acquire()); self.assertTrue(owner.acquire()); self.assertTrue(owner.owned)
        owner.release(); self.assertFalse(owner.owned)
        src=(ROOT/'tc_ai_bridge'/'navigation.py').read_text('utf-8')
        self.assertIn(r'Local\translationCoreAIBridge.NavigationOwner',src)
        self.assertIn('CreateMutexW',src); self.assertIn('WaitForSingleObject',src); self.assertIn('ReleaseMutex',src)

    def test_logos_helper_generations_are_queue_isolated_and_startup_timeout_is_longer(self):
        from tc_ai_bridge.logos_connector import LogosConnectorClient
        client=LogosConnectorClient(timeout=3.5)
        self.assertGreaterEqual(client.startup_timeout,8.0)
        self.assertGreaterEqual(client.navigation_timeout,5.0)
        src=(ROOT/'tc_ai_bridge'/'logos_connector.py').read_text('utf-8')
        self.assertIn('response_queue: queue.Queue = queue.Queue()',src)
        self.assertIn('stderr_lines = deque(maxlen=16)',src)
        self.assertIn('generation = self._generation',src)
        self.assertIn('response_queue.put',src)
        # Old reader closures must not publish into whatever queue a newer helper installed.
        reader=src.split('        def reader():',1)[1].split('        local_stderr_thread =',1)[0]
        self.assertNotIn('self._responses.put',reader)
        self.assertNotIn('self._stderr_lines',reader)

    def test_usage_totals_persist_and_accumulate_without_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'settings.json'; s=AppSettings(p)
            s.record_ai_usage(100,0.0123); s.record_ai_usage(250,0.0400)
            r=AppSettings(p).get_ai_usage_totals()
            self.assertEqual(r['tokens'],350)
            self.assertAlmostEqual(r['estimatedCostUSD'],0.0523,places=6)
            text=p.read_text('utf-8')
            self.assertIn('ai_usage_totals',text); self.assertNotIn('api_key',text.lower())


class V075UITests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.app=BridgeApp(settings_path=Path(self.td.name)/'settings.json')
        self.app.update_idletasks(); self.app.update()

    def tearDown(self):
        try:
            self.app._closing=True
            self.app.destroy()
        except Exception:
            pass
        self.td.cleanup()

    @staticmethod
    def _walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from V075UITests._walk(child)

    def test_workspace_sidebar_removed_and_user_guide_moved_to_help(self):
        self.assertFalse(hasattr(self.app,'sidebar'))
        all_text=[]
        for w in self._walk(self.app):
            try: all_text.append(str(w.cget('text')))
            except Exception: pass
        self.assertNotIn('WORKSPACE',all_text)
        self.assertEqual(self.app.help_btn.cget('text'),'Help')
        labels=[self.app.help_menu.entrycget(i,'label') for i in range(self.app.help_menu.index('end')+1)]
        self.assertIn('User Guide',labels); self.assertIn('Keyboard Shortcuts',labels)

    def test_tab_order_renames_review_and_places_it_before_alignment(self):
        labels=[self.app.notebook.tab(i,'text') for i in range(self.app.notebook.index('end'))]
        self.assertEqual(labels[:3],['Dashboard','tN tW Review','Alignment'])
        self.assertNotIn('AI Final Review',labels)
        self.app.geometry('760x560'); self.app.update(); time.sleep(.03); self.app.update()
        compact=[self.app.notebook.tab(i,'text') for i in range(self.app.notebook.index('end'))]
        self.assertEqual(compact[:3],['Dash','tN/tW','Align'])

    def test_dashboard_exception_queue_and_summary_are_side_by_side_with_vertical_scroll(self):
        panes=list(self.app.dashboard_exception_pane.panes())
        self.assertEqual(len(panes),2)
        self.assertEqual(str(self.app.dashboard_exception_pane.cget('orient')),'horizontal')
        self.assertEqual(str(self.app.exception_detail.cget('wrap')),'word')
        self.assertTrue(str(self.app.exception_detail.cget('yscrollcommand')))
        self.app.geometry('760x560'); self.app.update(); time.sleep(.03); self.app.update()
        self.assertEqual(len(self.app.dashboard_exception_pane.panes()),2)

    def test_alignment_toolbar_is_flow_ordered_and_secondary_actions_are_under_more(self):
        labels=[str(w.cget('text')) for w in self.app.align_toolbar_widgets]
        self.assertEqual(labels,[
            'Connect','Unalign Target','Undo','Redo',
            'Fill Alignment Gaps','Audit Existing Alignment','Apply AI Proposal',
            'Save Alignment','Approve Verse','More…'])
        forbidden=('AI Full Review','Diagnostics…','Groups…','Restore Backup','Save Approved Alignment')
        for item in forbidden:self.assertNotIn(item,labels)
        separators=[str(x.cget('text')) for x in self.app.align_toolbar_separators]
        self.assertTrue(separators); self.assertTrue(all(x=='|' for x in separators))
        self.app.geometry('760x560'); self.app.update(); time.sleep(.03); self.app.update()
        # Small screens stack logical groups instead of randomly clipping buttons.
        rows={int(g.grid_info().get('row',0)) for g in self.app.align_toolbar_groups if g.winfo_manager()=='grid'}
        self.assertGreater(len(rows),1)

    def test_all_normal_action_buttons_have_tooltips(self):
        missing=[]
        for w in self._walk(self.app):
            if w.winfo_class() in ('TButton','TMenubutton'):
                try:
                    if str(w.cget('text')).strip() and not getattr(w,'_tc_tooltip_bound',False):missing.append(str(w.cget('text')))
                except Exception:pass
        self.assertEqual(missing,[])
        self.assertGreater(len(self.app._tooltips),40)

    def test_tooltip_geometry_is_clamped_inside_visible_screen(self):
        self.app.geometry('760x560+0+0'); self.app.update();
        # Use a real bottom/right control and a deliberately long tooltip.
        tip=next(t for t in self.app._tooltips if t.widget is self.app.cost_label)
        tip.text='A very long tooltip used to verify screen-aware placement. '*15
        tip._show(); self.app.update_idletasks(); self.app.update()
        self.assertIsNotNone(tip._tip)
        x=tip._tip.winfo_rootx(); y=tip._tip.winfo_rooty(); w=tip._tip.winfo_width(); h=tip._tip.winfo_height()
        sw=tip._tip.winfo_screenwidth(); sh=tip._tip.winfo_screenheight()
        self.assertGreaterEqual(x,0); self.assertGreaterEqual(y,0)
        self.assertLessEqual(x+w,sw); self.assertLessEqual(y+h,sh)
        tip._hide()

    def test_collapsible_sections_use_left_aligned_fieldset_legends(self):
        prod=[w for w in self._walk(self.app.production_body) if isinstance(w,_CollapsibleSection)]
        settings=[w for w in self._walk(self.app.settings_body) if isinstance(w,_CollapsibleSection)]
        self.assertTrue(prod); self.assertTrue(settings)
        for sec in prod+settings:
            self.assertEqual(str(sec.header.cget('anchor')),'w')
            self.assertEqual(str(sec.header.pack_info().get('side')),'left')
            self.assertTrue(sec.legend_rule.winfo_exists())
            before=sec.expanded; sec.toggle(); self.app.update_idletasks()
            self.assertNotEqual(sec.expanded,before)
            self.assertEqual(bool(sec.body_shell.winfo_manager()),sec.expanded)
            sec.toggle(); self.app.update_idletasks()

    def test_production_and_settings_sections_are_all_collapsible_and_small_screen_scrollable(self):
        prod=[w for w in self._walk(self.app.production_body) if isinstance(w,_CollapsibleSection)]
        settings=[w for w in self._walk(self.app.settings_body) if isinstance(w,_CollapsibleSection)]
        self.assertGreaterEqual(len(prod),7); self.assertGreaterEqual(len(settings),5)
        for sec in prod+settings:
            self.assertIn(str(sec.header.cget('text'))[:1],('▼','▶'))
        self.assertTrue(hasattr(self.app,'production_scroll_canvas')); self.assertTrue(hasattr(self.app,'settings_scroll_canvas'))
        self.app.geometry('760x560'); self.app.update(); time.sleep(.03); self.app.update()
        self.assertEqual(self.app.production_left.grid_info()['column'],0)
        self.assertEqual(self.app.production_right.grid_info()['column'],0)

    def test_api_section_shows_bridge_recorded_lifetime_tokens_and_cost(self):
        self.app.settings.record_ai_usage(1234,0.5678); self.app._refresh_api_usage_totals()
        self.assertEqual(self.app.api_total_tokens_var.get(),'1,234 tokens')
        self.assertEqual(self.app.api_total_cost_var.get(),'$0.5678 estimated')

    def test_any_direction_source_guard_for_paratext_and_logos(self):
        self.app.project=SimpleNamespace(book_id='gen')
        self.app.chapter_var.set('1'); self.app.verse_var.set('5')
        self.app.paratext_nav_sync_var.set(True); self.app.logos_nav_sync_var.set(True)
        p_calls=[]; l_calls=[]
        self.app.paratext_connector=SimpleNamespace(set_reference=lambda ref,origin_id='':p_calls.append((ref,origin_id)))
        self.app.paratext_connector_state=None
        self.app._queue_logos_navigation=lambda ref,oid:l_calls.append((ref,oid))

        self.app._navigation_origin='paratext'
        self.app._sync_current_reference_to_paratext(); self.app._sync_current_reference_to_logos()
        self.assertEqual(p_calls,[]); self.assertEqual(l_calls[-1][0],'GEN 1:5')

        p_calls.clear(); l_calls.clear(); self.app._navigation_origin='logos'
        self.app._sync_current_reference_to_paratext(); self.app._sync_current_reference_to_logos()
        self.assertEqual(l_calls,[]); self.assertEqual(p_calls[-1][0],'GEN 1:5')

        p_calls.clear(); l_calls.clear(); self.app._navigation_origin='bridge'
        self.app._sync_current_reference_to_paratext(); self.app._sync_current_reference_to_logos()
        self.assertEqual(p_calls[-1][0],'GEN 1:5'); self.assertEqual(l_calls[-1][0],'GEN 1:5')

    def test_logos_navigation_never_guesses_between_multiple_same_book_projects(self):
        current=SimpleNamespace(book_id='exo',path=Path('/tmp/exo'))
        gen1=SimpleNamespace(book_id='gen',path=Path('/tmp/gen-a'))
        gen2=SimpleNamespace(book_id='gen',path=Path('/tmp/gen-b'))
        self.app.projects=[current,gen1,gen2]; self.app.project=current; self.app.session=None
        changed=self.app._navigate_from_external('GEN 1:5','logos')
        self.assertFalse(changed)
        self.assertIn('multiple loaded translationCore projects',self.app.status_var.get())
        self.assertIs(self.app.project,current)

    def test_external_unavailable_chapter_is_validated_before_project_switch(self):
        current=SimpleNamespace(book_id='exo',path=Path('/tmp/exo'))
        gen=SimpleNamespace(book_id='gen',path=Path('/tmp/gen'),chapters=lambda:['1'],verses=lambda ch:['1','2'])
        self.app.projects=[current,gen]; self.app.project=current; self.app.session=None
        changed=self.app._navigate_from_external('GEN 2:1','logos')
        self.assertFalse(changed)
        self.assertIs(self.app.project,current)
        self.assertIn('not present',self.app.status_var.get())

    def test_paratext_immediate_reference_mismatch_fails_closed_as_versification_guard(self):
        self.app.project=SimpleNamespace(book_id='gen',path=Path('/tmp/gen'))
        self.app.chapter_var.set('1'); self.app.verse_var.set('5')
        self.app.paratext_nav_sync_var.set(True)
        self.app.paratext_connector_state=None
        self.app.paratext_connector=SimpleNamespace(set_reference=lambda ref,origin_id='':{'reference':'GEN 1:6'})
        self.app._sync_current_reference_to_paratext()
        self.assertFalse(self.app.paratext_nav_sync_var.get())
        self.assertIn('Versification safety stop',self.app.paratext_connector_var.get())

    def test_production_exposes_reference_label_versification_safety_notice(self):
        self.assertIn('reference-label based',self.app.paratext_versification_note.cget('text'))
        self.assertIn('different versifications',self.app.logos_versification_note.cget('text'))

    def test_logos_background_workers_do_not_capture_tk_root_or_grow_worker_tracking(self):
        s=(ROOT/'tc_ai_bridge'/'ui.py').read_text('utf-8')
        poll=s.split('        def poll_worker():',1)[1].split('    def _queue_logos_navigation',1)[0]
        nav=s.split('        def nav_worker():',1)[1].split('    def _drain_logos_async_queue',1)[0]
        self.assertNotIn('self.',poll)
        self.assertNotIn('self.',nav)
        self.assertNotIn('_worker_threads.append',poll)
        self.assertNotIn('_worker_threads.append',nav)

    def test_logos_sync_does_not_auto_enable_on_restart(self):
        # A previous session must not silently let an external application navigate the Bridge.
        self.assertFalse(self.app.logos_nav_sync_var.get())


if __name__=='__main__':
    unittest.main()
