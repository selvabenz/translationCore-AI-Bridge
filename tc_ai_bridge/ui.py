from __future__ import annotations

import copy
import json
import queue
import threading
import traceback
import hashlib
import difflib
import gc
import webbrowser
import sys
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

from .analytics import translation_words_book_analytics, exception_first_queue
from .reporting import ReportService
from .psalms_qa import analyze_psalm_chapter
from .git_service import GitService, GitError
from .model_router import ModelRouter, estimate_cost
from .metrics import MetricsStore
from .team import TeamWorkflow
from .plugins import PluginRegistry
from .security import sanitize_for_log, scan_tree_for_secrets

from .ai_client import AIError, OpenAIResponsesClient
from .alignment_engine import AlignmentError, apply_proposal, make_inventory, realign, token_label, unalign_bottom, validate_proposal
from .local_checks import run_local_qa
from .knowledge_base import TranslationHelpsKnowledgeBase
from .models import AICheckReview, QAIssue, VerseAlignment
from .secret_store import AppSettings
from .session import EditSession
from .tc_project import ProjectError, TranslationCoreProject, TranslationCoreRoot
from .usfm import strip_usfm


class _ToolTip:
    """Small native tooltip with delayed display and safe teardown."""
    def __init__(self, widget, text: str, delay_ms: int = 450):
        self.widget=widget; self.text=text; self.delay_ms=delay_ms; self._after=None; self._tip=None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')
    def _schedule(self, event=None):
        self._cancel()
        try: self._after=self.widget.after(self.delay_ms,self._show)
        except tk.TclError: pass
    def _cancel(self):
        if self._after is not None:
            try: self.widget.after_cancel(self._after)
            except tk.TclError: pass
            self._after=None
    def _show(self):
        self._after=None
        try:
            if not self.widget.winfo_exists() or self._tip is not None: return
            x=self.widget.winfo_rootx()+12; y=self.widget.winfo_rooty()+self.widget.winfo_height()+6
            tip=tk.Toplevel(self.widget); tip.wm_overrideredirect(True); tip.wm_geometry(f'+{x}+{y}')
            try: tip.wm_attributes('-topmost',True)
            except tk.TclError: pass
            ttk.Label(tip,text=self.text,justify='left',padding=(7,4),wraplength=420,relief='solid',borderwidth=1).pack()
            self._tip=tip
        except tk.TclError:
            self._tip=None
    def _hide(self,event=None):
        self._cancel()
        if self._tip is not None:
            try: self._tip.destroy()
            except tk.TclError: pass
            self._tip=None



class BridgeApp(tk.Tk):
    def __init__(self, initial_root: str | None = None, settings_path: Path | None = None):
        super().__init__()
        self.title('translationCore AI Bridge v0.7.0')
        self.geometry('1440x900')
        self.minsize(760, 560)
        self._small_screen = False
        self._compact_screen = False
        self._icon_image = None
        self._header_icon_image = None
        self._apply_app_icon()
        self.settings = AppSettings(settings_path)
        self.tc_root: TranslationCoreRoot | None = None
        self.projects: list[TranslationCoreProject] = []
        self.project: TranslationCoreProject | None = None
        self.session: EditSession | None = None
        self.original_verse_raw: dict | None = None
        self.pending_ai_proposal: dict | None = None
        self.ai_issues: list[QAIssue] = []
        self.ai_check_reviews: list[AICheckReview] = []
        # Alignment whose token inventory was used by the most recent AI check review.
        # This may differ from session.current when AI prepared, but the human has not yet applied,
        # a proposed alignment. Keep it so TN/TW token IDs can be resolved to exact token signatures.
        self.review_alignment_for_checks: VerseAlignment | None = None
        self.review_meta: dict = {}
        self.kb: TranslationHelpsKnowledgeBase | None = None
        self._busy = False
        self._api_state = 'unknown'
        self._active_job_label = ''
        self._ui_queue: queue.Queue = queue.Queue()
        self._bg_success_handler = None
        self._bg_is_ai = False
        self._cancel_event = threading.Event()
        self._worker_threads: list[threading.Thread] = []
        self._closing = False
        self._tooltips: list[_ToolTip] = []
        self.project_scan_data: dict = {}
        self.scripture_undo_stack: list[tuple[str,str]] = []
        self.scripture_redo_stack: list[tuple[str,str]] = []
        self.plugin_registry = PluginRegistry()
        self.language_context = None
        self.fast_review_var = tk.BooleanVar(value=bool(self.settings.get_setting('auto_advance_review', False)))
        self._build_ui()
        self._install_reviewer_shortcuts()
        self.bind('<Configure>', self._on_responsive_resize, add='+')
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        if initial_root:
            self.after(50, lambda: self.load_root(initial_root))
        if self.settings.get_api_key():
            self.after(450, self._auto_test_api)

    def _tip(self, widget, text: str):
        if widget is not None and text:
            self._tooltips.append(_ToolTip(widget,text))
        return widget

    def _asset_path(self, name: str) -> Path:
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
        p = base / 'assets' / name
        if p.exists(): return p
        return Path(__file__).resolve().parent.parent / 'assets' / name

    def _apply_app_icon(self):
        try:
            p=self._asset_path('app_icon_48.png')
            if p.exists():
                self._icon_image=tk.PhotoImage(file=str(p)); self._app_icon_image=self._icon_image; self.iconphoto(True,self._icon_image)
        except Exception:
            pass

    def _on_responsive_resize(self, event=None):
        if event is not None and event.widget is not self: return
        try: width=max(1,self.winfo_width())
        except Exception: return
        small=width < 1080; compact=width < 860
        if small==self._small_screen and compact==self._compact_screen: return
        self._small_screen=small; self._compact_screen=compact
        try:
            # ttk.Panedwindow orientation is read-only after creation. On compact screens
            # keep Hebrew/Tamil side-by-side and move a mirrored Current Alignment Groups viewer
            # below them. Groups must remain visible rather than disappearing on small screens.
            if hasattr(self,'align_group_frame') and hasattr(self,'align_token_pane'):
                panes=list(self.align_token_pane.panes())
                gp=str(self.align_group_frame)
                if compact:
                    if gp in panes: self.align_token_pane.forget(self.align_group_frame)
                    if hasattr(self,'align_compact_group_frame'): self.align_compact_group_frame.grid()
                else:
                    if hasattr(self,'align_compact_group_frame'): self.align_compact_group_frame.grid_remove()
                    if gp not in panes: self.align_token_pane.add(self.align_group_frame,weight=4)
            # Header sheds explanatory labels, not controls/status, at narrow widths.
            if hasattr(self,'root_label'):
                (self.root_label.grid_remove() if small else self.root_label.grid())
            if hasattr(self,'project_label'):
                (self.project_label.grid_remove() if small else self.project_label.grid())
            if hasattr(self,'project_info_label'):
                (self.project_info_label.grid_remove() if small else self.project_info_label.grid())
            if hasattr(self,'browse_btn'):
                (self.browse_btn.grid_remove() if compact else self.browse_btn.grid())
            if hasattr(self,'api_test_btn'):
                (self.api_test_btn.grid_remove() if compact else self.api_test_btn.grid())
            if hasattr(self,'project_combo'):
                self.project_combo.configure(width=18 if compact else (24 if small else 30))
            if hasattr(self,'qa_detail'):
                self.qa_detail.configure(height=6 if compact else 9)
            if hasattr(self,'dashboard_scan'):
                self.dashboard_scan.configure(height=6 if compact else (8 if small else 10))
            self._reflow_toolbar(getattr(self,'dashboard_actions',None),getattr(self,'dashboard_action_widgets',[]),3 if small else 5)
            full_wrap=max(360,width-90)
            half_wrap=max(240,(width-120)//2)
            for name in ('dashboard_summary_label','review_summary_label','qa_summary_label','kb_intro_label','psalms_info_label','safety_label'):
                label=getattr(self,name,None)
                if label is not None: label.configure(wraplength=full_wrap)
            for name in ('tx_status_label','git_status_label','team_status_label','plugins_label','paratext_notes_label'):
                label=getattr(self,name,None)
                if label is not None: label.configure(wraplength=half_wrap)
            if hasattr(self,'_tab_defs') and hasattr(self,'notebook'):
                labels=self._compact_tab_labels if small else [x[0] for x in self._tab_defs]
                for i,label in enumerate(labels):
                    self.notebook.tab(i,text=label)
            self._reflow_toolbar(getattr(self,'align_toolbar',None),getattr(self,'align_toolbar_widgets',[]),3 if compact else (5 if small else 9))
            self._reflow_toolbar(getattr(self,'review_header_toolbar',None),getattr(self,'review_header_widgets',[]),2 if compact else (3 if small else 5))
            self._reflow_toolbar(getattr(self,'review_actions',None),getattr(self,'review_action_widgets',[]),2 if compact else (3 if small else 5))
            self._reflow_toolbar(getattr(self,'qa_toolbar',None),getattr(self,'qa_toolbar_widgets',[]),2 if compact else (3 if small else 5))
            self._resize_tree_columns()
        except tk.TclError:
            pass

    @staticmethod
    def _reflow_toolbar(frame, widgets, columns):
        if not frame or not widgets: return
        columns=max(1,int(columns))
        for w in widgets: w.grid_forget()
        for i,w in enumerate(widgets):
            w.grid(row=i//columns,column=i%columns,sticky='ew',padx=2,pady=2)
        for c in range(columns): frame.columnconfigure(c,weight=1)

    def _resize_tree_columns(self):
        width=max(760,self.winfo_width())
        try:
            if hasattr(self,'review_tree'):
                if width<1080:
                    sizes={'severity':72,'tool':98,'group':145,'verdict':82,'selection':190,'confidence':82}
                else:
                    sizes={'severity':82,'tool':120,'group':210,'verdict':95,'selection':280,'confidence':90}
                for c,w in sizes.items(): self.review_tree.column(c,width=w,minwidth=55,stretch=True)
            if hasattr(self,'exception_tree'):
                self.exception_tree.column('summary',width=380 if width<1080 else 650,stretch=True)
        except tk.TclError: pass

    def _install_reviewer_shortcuts(self):
        """Keyboard-first reviewer workflow. Shortcuts never approve Scripture automatically."""
        bindings={
            '<F5>': lambda e:self._run_full_review(),
            '<F8>': lambda e:self._review_next_priority(),
            '<Control-Return>': lambda e:self._record_review_decision('accepted'),
            '<Control-Shift-D>': lambda e:self._record_review_decision('needs_discussion'),
            '<Control-Shift-R>': lambda e:self._record_review_decision('rejected'),
            '<Control-Shift-Right>': lambda e:self._next_verse(),
        }
        for seq,fn in bindings.items():
            try: self.bind_all(seq,fn,add='+')
            except tk.TclError: pass

    def _next_verse(self):
        if not self.project:return
        values=list(self.verse_combo.cget('values') or ())
        cur=self.verse_var.get()
        try: idx=values.index(cur)
        except ValueError: return
        if idx+1<len(values):
            self.verse_var.set(values[idx+1]); self._load_verse(); return
        chapters=list(self.chapter_combo.cget('values') or ())
        ch=self.chapter_var.get()
        try: ci=chapters.index(ch)
        except ValueError: return
        if ci+1<len(chapters): self.chapter_var.set(chapters[ci+1]); self._chapter_changed(force=True)

    def _review_next_priority(self):
        """Fast-path to the next exception, falling back to next verse when the queue is empty."""
        try: self._refresh_exception_queue()
        except Exception: pass
        children=self.exception_tree.get_children() if hasattr(self,'exception_tree') else ()
        if children:
            self.exception_tree.selection_set(children[0]); self._dashboard_open_selected(); return
        self._next_verse()

    def _apply_language_context(self):
        if not self.language_context:return
        c=self.language_context
        try:
            self.align_verse_frame.configure(text=f'{c.target_name} verse · project text')
            self.align_top_frame.configure(text=f'{c.source_name} topWords')
            self.align_bottom_frame.configure(text=f'{c.target_name} bottomWords')
            self.align_group_frame.configure(text=f'Current {c.source_name} ↔ {c.target_name} alignment groups')
            if hasattr(self,'align_compact_group_frame'): self.align_compact_group_frame.configure(text=f'Current {c.source_name} ↔ {c.target_name} alignment groups')
            self.top_list.configure(font=(c.source_font,11))
            self.bottom_list.configure(font=(c.target_font,11))
            self.group_list.configure(font=(c.target_font,10))
            self.verse_text.configure(font=(c.target_font,12))
            self.ai_preview.configure(font=(c.target_font,10))
            self._tip(self.top_list,f'{c.source_name} source tokens. Source language detected from project/source token evidence.')
            self._tip(self.bottom_list,f'{c.target_name} target tokens. Target-language plugin: {c.target_id}; QA: {", ".join(c.qa_categories)}.')
            self.project_info_var.set(f'{self.project.summary.tc_version} / {self.project.summary.edit_version} · {c.source_name}→{c.target_name}')
        except tk.TclError: pass

    @staticmethod
    def _confidence_class(value: float) -> str:
        return 'conf_high' if value >= .85 else ('conf_mid' if value >= .65 else 'conf_low')

    def _render_ai_proposal(self, current: VerseAlignment, proposal: dict, prefix: str = ''):
        """Render source/target/reason/confidence as visually distinct evidence roles."""
        if not hasattr(self,'ai_preview'): return
        inv=make_inventory(current)
        try: groups=validate_proposal(current,proposal)
        except Exception:
            groups=proposal.get('groups',[]) if isinstance(proposal,dict) else []
        c=self.language_context
        source_name=c.source_name if c else 'Source'
        target_name=c.target_name if c else 'Target'
        w=self.ai_preview; w.configure(state='normal'); w.delete('1.0','end')
        w.tag_configure('source_lang',foreground='#6D28D9',font=(c.source_font if c else 'Segoe UI',10,'bold'))
        w.tag_configure('target_lang',foreground='#047857',font=(c.target_font if c else 'Segoe UI',10,'bold'))
        w.tag_configure('english',foreground='#475569')
        w.tag_configure('conf_high',foreground='#15803D',font=('Segoe UI',10,'bold'))
        w.tag_configure('conf_mid',foreground='#B45309',font=('Segoe UI',10,'bold'))
        w.tag_configure('conf_low',foreground='#B91C1C',font=('Segoe UI',10,'bold'))
        w.tag_configure('label',foreground='#111827',font=('Segoe UI',9,'bold'))
        if prefix:
            w.insert('end',prefix.rstrip()+'\n\n','english')
        w.insert('end',f'Legend · {source_name} ','label'); w.insert('end','■ ','source_lang')
        w.insert('end',f' {target_name} ','label'); w.insert('end','■ ','target_lang')
        w.insert('end',' English rationale ','label'); w.insert('end','■','english'); w.insert('end',' · Confidence: ')
        w.insert('end','HIGH ','conf_high'); w.insert('end','MEDIUM ','conf_mid'); w.insert('end','LOW\n\n','conf_low')
        for i,g in enumerate(groups,1):
            h=' '.join(inv.top_ids[x].word for x in g.get('top_ids',[]) if x in inv.top_ids) or '∅'
            t=' '.join(inv.bottom_ids[x].word for x in g.get('bottom_ids',[]) if x in inv.bottom_ids) or '∅'
            conf=float(g.get('confidence',0) or 0)
            w.insert('end',f'{i}. {source_name}: ','label'); w.insert('end',h+'\n','source_lang')
            w.insert('end',f'   {target_name}: ','label'); w.insert('end',t+'\n','target_lang')
            w.insert('end','   Confidence: ','label'); w.insert('end',f'{conf:.0%}\n',self._confidence_class(conf))
            reason=str(g.get('reason','')).strip()
            if reason:
                w.insert('end','   English rationale: ','label'); w.insert('end',reason+'\n','english')
            w.insert('end','\n')
        notes=proposal.get('review_notes',[]) if isinstance(proposal,dict) else []
        if notes:
            w.insert('end','Review notes\n','label')
            for n in notes: w.insert('end',f'• {n}\n','english')
        w.configure(state='disabled')

    def _install_overflow_navigation(self):
        """Ensure every long-form display has keyboard/mouse overflow navigation even if it wraps."""
        def walk(widget):
            try: children=widget.winfo_children()
            except tk.TclError: return
            for child in children:
                if isinstance(child,(tk.Text,tk.Listbox,ttk.Treeview)):
                    def hx(event, w=child):
                        try: w.xview_scroll(-1 if event.delta>0 else 1,'units')
                        except tk.TclError: pass
                        return 'break'
                    child.bind('<Shift-MouseWheel>',hx,add='+')
                    child.bind('<Alt-Left>',lambda e,w=child:(w.xview_scroll(-3,'units'),'break')[1],add='+')
                    child.bind('<Alt-Right>',lambda e,w=child:(w.xview_scroll(3,'units'),'break')[1],add='+')
                walk(child)
        walk(self)

    @staticmethod
    def _rounded_tab_image(w: int, h: int, radius: int, fill: str, cut: str) -> tk.PhotoImage:
        """Procedurally draw a tab background with rounded top corners (no PIL dependency).

        Corner pixels are filled with `cut` (the ambient window background), which fakes
        transparency since Tk's PhotoImage has no cheap per-pixel alpha compositing here.
        """
        img = tk.PhotoImage(width=w, height=h)
        img.put(cut, to=(0, 0, w, h))
        for y in range(h):
            if y < radius:
                dy = radius - y
                dx = radius - int(round((radius * radius - dy * dy) ** 0.5))
            else:
                dx = 0
            x0, x1 = dx, w - dx
            if x1 > x0:
                img.put(fill, to=(x0, y, x1, y + 1))
        return img

    def _style_chrome_tabs(self, style: ttk.Style) -> None:
        """Chrome-style tab strip: rounded top corners, gray/receding unselected tabs, a
        white bold selected tab so the active workspace is unmistakable at a glance.
        """
        ambient_bg = '#f0f0f0'  # SystemButtonFace on Windows; matches the notebook's own background
        w, h, radius = 28, 22, 6
        self._tab_img_normal = self._rounded_tab_image(w, h, radius, '#e8eaed', ambient_bg)
        self._tab_img_hover = self._rounded_tab_image(w, h, radius, '#f1f3f4', ambient_bg)
        self._tab_img_selected = self._rounded_tab_image(w, h, radius, '#ffffff', ambient_bg)

        style.configure('TNotebook', tabmargins=[2, 4, 2, 0], background=ambient_bg)
        style.configure('TNotebook.Tab', padding=[10, 4], font=('Segoe UI', 10), foreground='#5f6368')
        style.map('TNotebook.Tab',
                  foreground=[('selected', '#000000'), ('active', '#202124')],
                  font=[('selected', ('Segoe UI', 10, 'bold'))])

        style.element_create('Chrome.tab', 'image', self._tab_img_normal,
                              ('selected', self._tab_img_selected),
                              ('active', self._tab_img_hover),
                              border=(7, 6, 7, 2), sticky='nsew')

        def substitute(layout):
            out = []
            for name, opts in layout:
                opts = dict(opts)
                if name == 'Notebook.tab':
                    name = 'Chrome.tab'
                if 'children' in opts:
                    opts['children'] = substitute(opts['children'])
                out.append((name, opts))
            return out

        style.layout('TNotebook.Tab', substitute(style.layout('TNotebook.Tab')))

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use('vista')
        except tk.TclError:
            try: style.theme_use('clam')
            except tk.TclError: pass
        style.configure('Section.TLabel', font=('Segoe UI', 9, 'bold'))
        style.configure('Accent.TButton', font=('Segoe UI', 9, 'bold'))
        style.configure('Status.TLabel', font=('Segoe UI', 9))
        style.configure('Metric.TLabel', font=('Segoe UI', 9, 'bold'))
        self._style_chrome_tabs(style)

        # Compact responsive header. The old screenshot-like product title is intentionally
        # removed from the client area; Windows still shows the real window title + app icon.
        self.header = ttk.Frame(self, padding=(8, 6)); self.header.pack(fill='x')
        try:
            p=self._asset_path('app_icon_48.png')
            if p.exists():
                self._header_icon_image=tk.PhotoImage(file=str(p))
                ttk.Label(self.header,image=self._header_icon_image).grid(row=0,column=0,rowspan=2,sticky='nw',padx=(0,6))
        except Exception: pass
        self.root_var=tk.StringVar()
        self.root_label=ttk.Label(self.header,text='translationCore folder'); self.root_label.grid(row=0,column=1,sticky='w')
        self.root_entry=ttk.Entry(self.header,textvariable=self.root_var); self.root_entry.grid(row=0,column=2,sticky='ew',padx=5)
        self.browse_btn=ttk.Button(self.header,text='Browse…',command=self._browse_root); self.browse_btn.grid(row=0,column=3,padx=2)
        self.load_btn=ttk.Button(self.header,text='Load',command=lambda:self.load_root(self.root_var.get())); self.load_btn.grid(row=0,column=4,padx=2)
        self.api_box=ttk.Frame(self.header); self.api_box.grid(row=0,column=5,rowspan=2,sticky='e',padx=(10,0))
        self.api_dot=tk.Canvas(self.api_box,width=22,height=22,highlightthickness=0)
        self.api_dot.grid(row=0,column=0,rowspan=2,padx=(0,4))
        self.api_status_var=tk.StringVar(value='API not tested')
        self.api_status_label=ttk.Label(self.api_box,textvariable=self.api_status_var); self.api_status_label.grid(row=0,column=1,sticky='e')
        self.api_test_btn=ttk.Button(self.api_box,text='Test API',command=self._test_api_connection); self.api_test_btn.grid(row=1,column=1,sticky='e',pady=(2,0))
        ttk.Button(self.api_box,text='User Guide',command=self._open_user_guide).grid(row=0,column=2,rowspan=2,sticky='e',padx=(8,0))
        self._set_api_indicator('unknown','API not tested')

        self.project_var=tk.StringVar(); self.chapter_var=tk.StringVar(); self.verse_var=tk.StringVar()
        self.project_label=ttk.Label(self.header,text='Project'); self.project_label.grid(row=1,column=1,sticky='w')
        self.project_combo=ttk.Combobox(self.header,textvariable=self.project_var,state='readonly',width=30)
        self.project_combo.grid(row=1,column=2,sticky='ew',padx=5); self.project_combo.bind('<<ComboboxSelected>>',self._project_changed)
        self.header_nav=nav=ttk.Frame(self.header); nav.grid(row=1,column=3,columnspan=2,sticky='ew')
        ttk.Label(nav,text='Ch').grid(row=0,column=0); self.chapter_combo=ttk.Combobox(nav,textvariable=self.chapter_var,state='readonly',width=6); self.chapter_combo.grid(row=0,column=1,padx=(2,6)); self.chapter_combo.bind('<<ComboboxSelected>>',self._chapter_changed)
        ttk.Label(nav,text='V').grid(row=0,column=2); self.verse_combo=ttk.Combobox(nav,textvariable=self.verse_var,state='readonly',width=7); self.verse_combo.grid(row=0,column=3,padx=2); self.verse_combo.bind('<<ComboboxSelected>>',self._verse_changed)
        self.project_info_var=tk.StringVar(value='No project loaded')
        self.project_info_label=ttk.Label(nav,textvariable=self.project_info_var); self.project_info_label.grid(row=0,column=4,padx=(8,0),sticky='w')
        self.header.columnconfigure(2,weight=1)

        self.body=ttk.Frame(self,padding=(8,0,8,4)); self.body.pack(fill='both',expand=True)
        self.content=ttk.Frame(self.body); self.content.pack(side='left',fill='both',expand=True)
        self.notebook=ttk.Notebook(self.content); self.notebook.pack(fill='both',expand=True)
        self.dashboard_tab=ttk.Frame(self.notebook); self.align_tab=ttk.Frame(self.notebook); self.review_tab=ttk.Frame(self.notebook); self.qa_tab=ttk.Frame(self.notebook); self.tc_tab=ttk.Frame(self.notebook); self.kb_tab=ttk.Frame(self.notebook); self.term_tab=ttk.Frame(self.notebook); self.psalms_tab=ttk.Frame(self.notebook); self.production_tab=ttk.Frame(self.notebook); self.settings_tab=ttk.Frame(self.notebook)
        tabs=[('Dashboard',self.dashboard_tab),('tN tW',self.review_tab),('Alignment',self.align_tab),('Quality Queue',self.qa_tab),('tC Check State',self.tc_tab),('Knowledge Base',self.kb_tab),('Terminology',self.term_tab),('Psalms QA',self.psalms_tab),('Production',self.production_tab),('Settings & Log',self.settings_tab)]
        self._tab_defs=tabs
        self._compact_tab_labels=['Dash','tN tW','Align','QA','tC','KB','Terms','Psalms','Prod','Settings']
        for label,tab in tabs: self.notebook.add(tab,text=label)

        self._build_dashboard_tab(); self._build_alignment_tab(); self._build_review_tab(); self._build_qa_tab(); self._build_tc_tab(); self._build_kb_tab(); self._build_terminology_tab(); self._build_psalms_tab(); self._build_production_tab(); self._build_settings_tab()

        # Status area uses a grid so progress, status, token count and cost remain visible at
        # smaller widths instead of being pushed off-screen by pack order.
        self.status_bar=ttk.Frame(self,padding=(8,4,8,6)); self.status_bar.pack(side='bottom',fill='x',before=self.body)
        self.status_var=tk.StringVar(value='Ready'); self.status_label=ttk.Label(self.status_bar,textvariable=self.status_var,style='Status.TLabel'); self.status_label.grid(row=0,column=0,sticky='w')
        self.job_progress=ttk.Progressbar(self.status_bar,mode='determinate',maximum=100); self.job_progress.grid(row=0,column=1,sticky='ew',padx=8); self.job_progress['value']=0
        self.usage_var=tk.StringVar(value='Tokens —'); self.usage_label=ttk.Label(self.status_bar,textvariable=self.usage_var,style='Metric.TLabel'); self.usage_label.grid(row=0,column=2,sticky='e',padx=(4,8))
        self.cost_var=tk.StringVar(value='Cost —'); self.cost_label=ttk.Label(self.status_bar,textvariable=self.cost_var,style='Metric.TLabel'); self.cost_label.grid(row=0,column=3,sticky='e')
        self.status_bar.columnconfigure(0,weight=2,minsize=160); self.status_bar.columnconfigure(1,weight=3,minsize=120)
        self._tip(self.root_entry,'Folder containing translationCore projects and resources.')
        self._tip(self.browse_btn,'Browse for the translationCore data folder.')
        self._tip(self.load_btn,'Load or reload projects from the selected translationCore folder.')
        self._tip(self.project_combo,'Switch the active translation project. Existing unsaved work is protected before switching.')
        self._tip(self.chapter_combo,'Choose the chapter in the active project.')
        self._tip(self.verse_combo,'Choose the verse in the active chapter.')
        self._tip(self.api_dot,'AI connection health: green means a successful authenticated API probe or AI request.')
        self._tip(self.api_status_label,'Current OpenAI API connection state.')
        self._tip(self.api_test_btn,'Verify the configured OpenAI API key/model without performing a translation review.')
        self._tip(self.status_label,'Current application job or navigation status.')
        self._tip(self.job_progress,'Progress for the current AI/batch/background operation.')
        self._tip(self.usage_label,'Observed OpenAI input/output token usage for the current/recent AI operation.')
        self._tip(self.cost_label,'Estimated API cost based on observed token usage and the selected model policy.')
        self._install_overflow_navigation()
        self.after(50,self._on_responsive_resize)

    def _build_dashboard_tab(self):
        outer = ttk.Frame(self.dashboard_tab, padding=10); outer.pack(fill='both', expand=True)
        title = ttk.Frame(outer); title.pack(fill='x')
        ttk.Label(title, text='Project Analysis & Exception-First Review', font=('Segoe UI', 10, 'bold')).pack(side='left')
        ttk.Button(title, text='Refresh Project Scan', command=self._refresh_dashboard_background).pack(side='right')
        self.dashboard_summary_var = tk.StringVar(value='Load a project to scan existing translationCore work.')
        self.dashboard_summary_label=ttk.Label(outer, textvariable=self.dashboard_summary_var, wraplength=1250); self.dashboard_summary_label.pack(fill='x', anchor='w', pady=(5,8))

        self.dashboard_actions = actions = ttk.Frame(outer); actions.pack(fill='x', pady=(0,8))
        self.dashboard_action_widgets=[
            ttk.Button(actions, text='Prepare Changed / Untouched Chapter', command=lambda:self._run_chapter_review(force=False), style='Accent.TButton'),
            ttk.Button(actions, text='Force Full Chapter Audit', command=lambda:self._run_chapter_review(force=True)),
            ttk.Button(actions, text='Prepare Changed Book', command=self._run_book_review),
        ]
        self.cancel_batch_btn = ttk.Button(actions, text='Cancel Batch', command=self._cancel_batch, state='disabled'); self.dashboard_action_widgets.append(self.cancel_batch_btn)
        self.dashboard_action_widgets.append(ttk.Button(actions, text='Review Highest Priority', command=self._open_highest_priority))
        self._reflow_toolbar(actions,self.dashboard_action_widgets,5)

        scan = ttk.LabelFrame(outer, text='Detected project state', padding=8); scan.pack(fill='x')
        scan.rowconfigure(0,weight=1); scan.columnconfigure(0,weight=1)
        self.dashboard_scan = tk.Text(scan, height=10, wrap='none', font=('Consolas', 10)); dsy=ttk.Scrollbar(scan,orient='vertical',command=self.dashboard_scan.yview); dsx=ttk.Scrollbar(scan,orient='horizontal',command=self.dashboard_scan.xview); self.dashboard_scan.configure(yscrollcommand=dsy.set,xscrollcommand=dsx.set)
        self.dashboard_scan.grid(row=0,column=0,sticky='nsew'); dsy.grid(row=0,column=1,sticky='ns'); dsx.grid(row=1,column=0,sticky='ew'); self.dashboard_scan.configure(state='disabled')

        q = ttk.LabelFrame(outer, text='Exception queue — Critical / High / Review / Stale first', padding=6); q.pack(fill='both', expand=True, pady=(8,0))
        cols=('ref','cache','critical','high','medium','checks','summary')
        q.rowconfigure(0,weight=1); q.columnconfigure(0,weight=1)
        self.exception_tree = ttk.Treeview(q, columns=cols, show='headings', selectmode='browse')
        for c,w in [('ref',90),('cache',90),('critical',70),('high',70),('medium',75),('checks',80),('summary',650)]:
            self.exception_tree.heading(c,text=c.title()); self.exception_tree.column(c,width=w,anchor='w')
        exy=ttk.Scrollbar(q,orient='vertical',command=self.exception_tree.yview); exx=ttk.Scrollbar(q,orient='horizontal',command=self.exception_tree.xview); self.exception_tree.configure(yscrollcommand=exy.set,xscrollcommand=exx.set)
        self.exception_tree.grid(row=0,column=0,sticky='nsew'); exy.grid(row=0,column=1,sticky='ns'); exx.grid(row=1,column=0,sticky='ew'); self.exception_tree.bind('<Double-1>', self._dashboard_open_selected)
        self._exception_rows: list[dict] = []

    def _build_alignment_tab(self):
        outer=ttk.Frame(self.align_tab,padding=6); outer.pack(fill='both',expand=True)
        outer.rowconfigure(2,weight=1); outer.columnconfigure(0,weight=1)
        self.align_verse_frame=textbox=ttk.LabelFrame(outer,text='Target verse · project text',padding=5); textbox.grid(row=0,column=0,sticky='ew')
        textbox.rowconfigure(0,weight=1); textbox.columnconfigure(0,weight=1)
        self.verse_text=tk.Text(textbox,height=2,wrap='word',font=('Nirmala UI',12),relief='flat'); vsy=ttk.Scrollbar(textbox,orient='vertical',command=self.verse_text.yview); self.verse_text.configure(yscrollcommand=vsy.set)
        self.verse_text.grid(row=0,column=0,sticky='nsew'); vsy.grid(row=0,column=1,sticky='ns'); self.verse_text.configure(state='disabled')

        # Controls are outside the draggable proposal pane: moving the sash can never hide them.
        self.align_toolbar=ttk.Frame(outer); self.align_toolbar.grid(row=1,column=0,sticky='ew',pady=5)
        specs=[
            ('Connect',self._connect_selected,''),('Unalign Target',self._unalign_selected,''),('Undo',self._undo,''),('Redo',self._redo,''),
            ('AI Suggest',self._ai_suggest,'Accent.TButton'),('AI Full Review',self._run_full_review,'Accent.TButton'),
            ('Apply AI Proposal',self._apply_ai,''),('Save Approved Alignment',self._save,''),('Approve Verse',self._approve,''),('Groups…',self._show_alignment_groups_popup,''),('Restore Backup',self._restore_latest,'')]
        self.align_toolbar_widgets=[]
        for text,cmd,sty in specs:
            kw={'text':text,'command':cmd}
            if sty: kw['style']=sty
            b=ttk.Button(self.align_toolbar,**kw); self.align_toolbar_widgets.append(b)
            if text=='Apply AI Proposal': self.apply_ai_btn=b; b.configure(state='disabled')
        self._reflow_toolbar(self.align_toolbar,self.align_toolbar_widgets,9)
        alignment_tips={
            'Connect':'Connect the selected existing source- and target-language tokens into one alignment group.',
            'Unalign Target':'Remove the selected target-language token(s) from their current alignment and return them to wordBank.',
            'Undo':'Undo the most recent in-memory alignment edit.',
            'Redo':'Redo the most recently undone alignment edit.',
            'AI Suggest':'Ask AI to prepare an alignment proposal using only the current verse tokens.',
            'AI Full Review':'Run alignment plus Translation Notes/Words and full verse QA with evidence.',
            'Apply AI Proposal':'Apply the prepared AI alignment to the editable in-memory alignment. This does not save yet.',
            'Save Approved Alignment':'Write the human-approved alignment safely to translationCore with backup/validation.',
            'Approve Verse':'Record final human verse approval after unresolved high-priority findings are cleared.',
            'Groups…':'Open a larger scrollable viewer of all current alignment groups.',
            'Restore Backup':'Restore the latest alignment backup using the reversible safety workflow.'}
        for widget,(text,_,_) in zip(self.align_toolbar_widgets,specs): self._tip(widget,alignment_tips.get(text,''))

        self.align_vertical_pane=ttk.Panedwindow(outer,orient='vertical'); self.align_vertical_pane.grid(row=2,column=0,sticky='nsew')
        work=ttk.Frame(self.align_vertical_pane); preview=ttk.LabelFrame(self.align_vertical_pane,text='AI Proposal · drag divider to resize',padding=4)
        self.align_vertical_pane.add(work,weight=5); self.align_vertical_pane.add(preview,weight=2)
        work.rowconfigure(0,weight=1); work.columnconfigure(0,weight=1)
        self.align_token_pane=ttk.Panedwindow(work,orient='horizontal'); self.align_token_pane.grid(row=0,column=0,sticky='nsew')
        self.align_top_frame=lf=ttk.LabelFrame(self.align_token_pane,text='Hebrew topWords',padding=4); self.align_bottom_frame=rf=ttk.LabelFrame(self.align_token_pane,text='Tamil bottomWords',padding=4); self.align_group_frame=gf=ttk.LabelFrame(self.align_token_pane,text='Current alignment groups',padding=4)
        self.align_token_pane.add(lf,weight=3); self.align_token_pane.add(rf,weight=3); self.align_token_pane.add(gf,weight=4)

        def _list_with_scroll(parent, **kwargs):
            holder=ttk.Frame(parent); holder.pack(fill='both',expand=True); holder.rowconfigure(0,weight=1); holder.columnconfigure(0,weight=1)
            lb=tk.Listbox(holder,**kwargs); y=ttk.Scrollbar(holder,orient='vertical',command=lb.yview); x=ttk.Scrollbar(holder,orient='horizontal',command=lb.xview)
            lb.configure(yscrollcommand=y.set,xscrollcommand=x.set); lb.grid(row=0,column=0,sticky='nsew'); y.grid(row=0,column=1,sticky='ns'); x.grid(row=1,column=0,sticky='ew')
            return lb
        self.top_list=_list_with_scroll(lf,selectmode='extended',exportselection=False,font=('Ezra SIL',11))
        self.bottom_list=_list_with_scroll(rf,selectmode='extended',exportselection=False,font=('Nirmala UI',10))
        self.group_list=_list_with_scroll(gf,selectmode='browse',exportselection=False,font=('Nirmala UI',9))
        self._tip(self.top_list,'Source-language tokens. Ctrl-click or Shift-click to select multiple tokens for manual alignment.')
        self._tip(self.bottom_list,'Target-language project tokens. Select one or more existing tokens; the Bridge never invents selection text.')
        self._tip(self.group_list,'Current source ↔ target alignment groups. Use the horizontal scrollbar for long phrases.')

        # Compact screens mirror alignment groups below Hebrew/Tamil instead of hiding them.
        self.align_compact_group_frame=ttk.LabelFrame(work,text='Current alignment groups',padding=4)
        self.align_compact_group_frame.grid(row=1,column=0,sticky='ew',pady=(5,0)); self.align_compact_group_frame.grid_remove()
        self.compact_group_list=_list_with_scroll(self.align_compact_group_frame,selectmode='browse',exportselection=False,font=('Nirmala UI',9),height=5)
        self._tip(self.compact_group_list,'Current alignment groups remain visible on small screens. Drag/scroll horizontally to inspect long phrases.')

        pv=ttk.Frame(preview); pv.pack(fill='both',expand=True); pv.rowconfigure(0,weight=1); pv.columnconfigure(0,weight=1)
        self.ai_preview=tk.Text(pv,height=5,wrap='none',font=('Nirmala UI',10)); sb=ttk.Scrollbar(pv,orient='vertical',command=self.ai_preview.yview); xb=ttk.Scrollbar(pv,orient='horizontal',command=self.ai_preview.xview)
        self.ai_preview.configure(yscrollcommand=sb.set,xscrollcommand=xb.set)
        self.ai_preview.grid(row=0,column=0,sticky='nsew'); sb.grid(row=0,column=1,sticky='ns'); xb.grid(row=1,column=0,sticky='ew'); self.ai_preview.configure(state='disabled')
        self._tip(self.ai_preview,'AI alignment proposal. This panel has both vertical and horizontal scrolling and a draggable divider.')

    def _show_alignment_groups_popup(self):
        win=tk.Toplevel(self); win.title(f'Alignment groups · {self.project.book_id.upper() if self.project else ""} {self.chapter_var.get()}:{self.verse_var.get()}')
        win.geometry('780x520'); frame=ttk.Frame(win,padding=8); frame.pack(fill='both',expand=True); frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        lb=tk.Listbox(frame,font=('Nirmala UI',10)); sb=ttk.Scrollbar(frame,orient='vertical',command=lb.yview); xb=ttk.Scrollbar(frame,orient='horizontal',command=lb.xview); lb.configure(yscrollcommand=sb.set,xscrollcommand=xb.set)
        lb.grid(row=0,column=0,sticky='nsew'); sb.grid(row=0,column=1,sticky='ns'); xb.grid(row=1,column=0,sticky='ew')
        for i in range(self.group_list.size() if hasattr(self,'group_list') else 0): lb.insert('end',self.group_list.get(i))

    def _build_review_tab(self):
        outer=ttk.Frame(self.review_tab,padding=6); outer.pack(fill='both',expand=True)
        outer.rowconfigure(3,weight=1); outer.columnconfigure(0,weight=1)
        self.review_header_toolbar=hdr=ttk.Frame(outer); hdr.grid(row=0,column=0,sticky='ew')
        self.review_header_widgets=[
            ttk.Button(hdr,text='AI Full Verse Review (F5)',command=self._run_full_review,style='Accent.TButton'),
            ttk.Button(hdr,text='Review Changed Chapter',command=lambda:self._run_chapter_review(force=False),style='Accent.TButton'),
            ttk.Button(hdr,text='Force Chapter Audit',command=lambda:self._run_chapter_review(force=True)),
            ttk.Button(hdr,text='Next Priority (F8)',command=self._review_next_priority),
            ttk.Button(hdr,text='Low-confidence Audit',command=self._show_suppressed_findings),
            ttk.Checkbutton(hdr,text='Auto-advance',variable=self.fast_review_var,command=lambda:self.settings.set_setting('auto_advance_review',bool(self.fast_review_var.get()))),
        ]
        self._reflow_toolbar(hdr,self.review_header_widgets,5)
        self.review_summary_var=tk.StringVar(value='Load a verse, then run AI Full Verse Review.')
        self.review_summary_label=ttk.Label(outer,textvariable=self.review_summary_var,wraplength=1250); self.review_summary_label.grid(row=1,column=0,sticky='ew',pady=(5,3))

        # Severity summary and tool/result viewer share one aligned grid.
        sev=ttk.Frame(outer); sev.grid(row=2,column=0,sticky='ew',pady=(0,4))
        self.review_severity_vars={}
        for i,(key,label) in enumerate([('critical','Critical'),('high','High'),('medium','Medium'),('editorial','Editorial'),('info','Info')]):
            v=tk.StringVar(value=f'{label}: 0'); self.review_severity_vars[key]=v
            ttk.Label(sev,textvariable=v,style='Metric.TLabel',anchor='center').grid(row=0,column=i,sticky='ew',padx=2)
            sev.columnconfigure(i,weight=1)

        self.review_split=ttk.Panedwindow(outer,orient='horizontal'); self.review_split.grid(row=3,column=0,sticky='nsew')
        self.review_left_frame=left=ttk.LabelFrame(self.review_split,text='Severity + Tool Viewer',padding=4); self.review_right_frame=right=ttk.LabelFrame(self.review_split,text='Result + Evidence',padding=4)
        self.review_split.add(left,weight=6); self.review_split.add(right,weight=5)
        left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1); right.rowconfigure(0,weight=1); right.columnconfigure(0,weight=1)
        cols=('severity','tool','group','verdict','selection','confidence')
        self.review_tree=ttk.Treeview(left,columns=cols,show='headings',selectmode='browse')
        for c in cols: self.review_tree.heading(c,text=c.title())
        self.review_tree.grid(row=0,column=0,sticky='nsew'); y=ttk.Scrollbar(left,orient='vertical',command=self.review_tree.yview); y.grid(row=0,column=1,sticky='ns'); rx=ttk.Scrollbar(left,orient='horizontal',command=self.review_tree.xview); rx.grid(row=1,column=0,sticky='ew'); self.review_tree.configure(yscrollcommand=y.set,xscrollcommand=rx.set)
        self.review_tree.bind('<<TreeviewSelect>>',self._review_selected)
        self.review_detail=tk.Text(right,wrap='none',font=('Nirmala UI',10)); ds=ttk.Scrollbar(right,orient='vertical',command=self.review_detail.yview); dx=ttk.Scrollbar(right,orient='horizontal',command=self.review_detail.xview); self.review_detail.configure(yscrollcommand=ds.set,xscrollcommand=dx.set)
        self.review_detail.grid(row=0,column=0,sticky='nsew'); ds.grid(row=0,column=1,sticky='ns'); dx.grid(row=1,column=0,sticky='ew'); self.review_detail.configure(state='disabled')
        self._tip(self.review_tree,'AI/tC findings. Use the horizontal scrollbar when long selections or group names exceed the available width.')
        self._tip(self.review_detail,'Selected result and evidence. Both vertical and horizontal scrolling are available for long evidence lines.')

        self.review_actions=decisions=ttk.Frame(outer); decisions.grid(row=4,column=0,sticky='ew',pady=(5,0))
        self.review_action_widgets=[]
        review_specs=[('Accept · Ctrl+Enter',lambda:self._record_review_decision('accepted')),('Edit Selection',self._edit_review_selection),('Needs Discussion · Ctrl+Shift+D',lambda:self._record_review_decision('needs_discussion')),('Reject AI · Ctrl+Shift+R',lambda:self._record_review_decision('rejected')),('Edit Scripture…',self._edit_scripture_from_review)]
        for text,cmd in review_specs:
            b=ttk.Button(decisions,text=text,command=cmd); self.review_action_widgets.append(b)
        self._reflow_toolbar(decisions,self.review_action_widgets,5)
        review_tips={
            'Accept · Ctrl+Enter':'Human-accept the selected AI TN/TW result and synchronize the approved selection where applicable.',
            'Edit Selection':'Correct the AI target-language token selection using only tokens that actually exist in the current verse.',
            'Needs Discussion · Ctrl+Shift+D':'Keep this item unresolved and record it for team/consultant discussion.',
            'Reject AI · Ctrl+Shift+R':'Reject the selected AI conclusion without marking the underlying check complete.',
            'Edit Scripture…':'Open the human Scripture correction workspace with before/after diff and stale propagation.'}
        for widget,(text,_) in zip(self.review_action_widgets,review_specs): self._tip(widget,review_tips[text])

    def _build_kb_tab(self):
        outer=ttk.Frame(self.kb_tab,padding=8); outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Project-aware Knowledge Base Resolver',font=('Segoe UI',12,'bold')).pack(anchor='w')
        self.kb_intro_label=ttk.Label(outer,text='Project-pinned Translation Helps versions win. If a project has no pin, the latest compatible installed resource is selected. Legacy aliases/fallbacks are explicit and evidence provenance is retained.',wraplength=1180); self.kb_intro_label.pack(anchor='w',pady=(2,8))
        kbt=ttk.Frame(outer); kbt.pack(fill='x'); kbt.rowconfigure(0,weight=1); kbt.columnconfigure(0,weight=1)
        self.kb_tree=ttk.Treeview(kbt,columns=('resource','version','provider','pinned','reason'),show='headings',height=8)
        for c,w in [('resource',190),('version',100),('provider',170),('pinned',90),('reason',600)]:
            self.kb_tree.heading(c,text=c.title()); self.kb_tree.column(c,width=w,anchor='w')
        kby=ttk.Scrollbar(kbt,orient='vertical',command=self.kb_tree.yview); kbx=ttk.Scrollbar(kbt,orient='horizontal',command=self.kb_tree.xview); self.kb_tree.configure(yscrollcommand=kby.set,xscrollcommand=kbx.set)
        self.kb_tree.grid(row=0,column=0,sticky='nsew'); kby.grid(row=0,column=1,sticky='ns'); kbx.grid(row=1,column=0,sticky='ew')
        frame=ttk.LabelFrame(outer,text='Current verse evidence package',padding=6); frame.pack(fill='both',expand=True,pady=(8,0))
        frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        self.kb_detail=tk.Text(frame,wrap='none'); kdy=ttk.Scrollbar(frame,orient='vertical',command=self.kb_detail.yview); kdx=ttk.Scrollbar(frame,orient='horizontal',command=self.kb_detail.xview); self.kb_detail.configure(yscrollcommand=kdy.set,xscrollcommand=kdx.set)
        self.kb_detail.grid(row=0,column=0,sticky='nsew'); kdy.grid(row=0,column=1,sticky='ns'); kdx.grid(row=1,column=0,sticky='ew'); self.kb_detail.configure(state='disabled')

    def _build_qa_tab(self):
        outer = ttk.Frame(self.qa_tab, padding=8); outer.pack(fill='both', expand=True)
        self.qa_toolbar=row = ttk.Frame(outer); row.pack(fill='x')
        self.qa_toolbar_widgets=[
            ttk.Button(row, text='Run Local QA', command=self._run_local_qa),
            ttk.Button(row, text='AI Full Review (F5)', command=self._run_full_review, style='Accent.TButton'),
            ttk.Button(row, text='Edit Scripture…', command=self._edit_scripture_from_qa),
            ttk.Button(row, text='Undo Scripture', command=self._undo_scripture),
            ttk.Button(row, text='Redo Scripture', command=self._redo_scripture),
        ]
        self._reflow_toolbar(row,self.qa_toolbar_widgets,5)
        self.qa_summary_var = tk.StringVar(value='Load a verse, then run QA.')
        self.qa_summary_label=ttk.Label(outer, textvariable=self.qa_summary_var,wraplength=1200); self.qa_summary_label.pack(fill='x',pady=(4,0))
        cols=('severity','source','status','title')
        qah=ttk.Frame(outer); qah.pack(fill='both',expand=True,pady=8); qah.rowconfigure(0,weight=1); qah.columnconfigure(0,weight=1)
        self.qa_tree=ttk.Treeview(qah, columns=cols, show='headings', selectmode='browse')
        for c,w in [('severity',90),('source',120),('status',125),('title',650)]: self.qa_tree.heading(c,text=c.title()); self.qa_tree.column(c,width=w,anchor='w')
        qay=ttk.Scrollbar(qah,orient='vertical',command=self.qa_tree.yview); qax=ttk.Scrollbar(qah,orient='horizontal',command=self.qa_tree.xview); self.qa_tree.configure(yscrollcommand=qay.set,xscrollcommand=qax.set)
        self.qa_tree.grid(row=0,column=0,sticky='nsew'); qay.grid(row=0,column=1,sticky='ns'); qax.grid(row=1,column=0,sticky='ew'); self.qa_tree.bind('<<TreeviewSelect>>', self._qa_selected)
        actions=ttk.Frame(outer); actions.pack(fill='x', pady=(0,6))
        ttk.Label(actions,text='Human decision:').pack(side='left')
        ttk.Button(actions,text='Accept Finding',command=lambda:self._record_qa_decision('accepted')).pack(side='left',padx=4)
        ttk.Button(actions,text='Needs Discussion',command=lambda:self._record_qa_decision('needs_discussion')).pack(side='left',padx=4)
        ttk.Button(actions,text='Reject AI Finding',command=lambda:self._record_qa_decision('rejected')).pack(side='left',padx=4)
        detail=ttk.LabelFrame(outer,text='Issue detail',padding=5); detail.pack(fill='x')
        detail.rowconfigure(0,weight=1); detail.columnconfigure(0,weight=1)
        self.qa_detail=tk.Text(detail,height=9,wrap='none'); qay2=ttk.Scrollbar(detail,orient='vertical',command=self.qa_detail.yview); qax2=ttk.Scrollbar(detail,orient='horizontal',command=self.qa_detail.xview); self.qa_detail.configure(yscrollcommand=qay2.set,xscrollcommand=qax2.set)
        self.qa_detail.grid(row=0,column=0,sticky='nsew'); qay2.grid(row=0,column=1,sticky='ns'); qax2.grid(row=1,column=0,sticky='ew'); self.qa_detail.configure(state='disabled')
        self._qa_items: list[QAIssue]=[]

    def _build_tc_tab(self):
        outer=ttk.Frame(self.tc_tab,padding=8); outer.pack(fill='both',expand=True)
        self.tc_summary_var=tk.StringVar(value='translationCore checks will appear here.')
        ttk.Label(outer,textvariable=self.tc_summary_var).pack(anchor='w')
        cols=('tool','group','check','status','selection')
        tch=ttk.Frame(outer); tch.pack(fill='both',expand=True,pady=8); tch.rowconfigure(0,weight=1); tch.columnconfigure(0,weight=1)
        self.tc_tree=ttk.Treeview(tch,columns=cols,show='headings',selectmode='browse')
        for c,w in [('tool',140),('group',220),('check',100),('status',100),('selection',480)]: self.tc_tree.heading(c,text=c.title()); self.tc_tree.column(c,width=w,anchor='w')
        tcy=ttk.Scrollbar(tch,orient='vertical',command=self.tc_tree.yview); tcx=ttk.Scrollbar(tch,orient='horizontal',command=self.tc_tree.xview); self.tc_tree.configure(yscrollcommand=tcy.set,xscrollcommand=tcx.set)
        self.tc_tree.grid(row=0,column=0,sticky='nsew'); tcy.grid(row=0,column=1,sticky='ns'); tcx.grid(row=1,column=0,sticky='ew'); self.tc_tree.bind('<<TreeviewSelect>>', self._tc_selected)
        tcd=ttk.Frame(outer); tcd.pack(fill='x'); tcd.rowconfigure(0,weight=1); tcd.columnconfigure(0,weight=1)
        self.tc_detail=tk.Text(tcd,height=10,wrap='none'); tcdy=ttk.Scrollbar(tcd,orient='vertical',command=self.tc_detail.yview); tcdx=ttk.Scrollbar(tcd,orient='horizontal',command=self.tc_detail.xview); self.tc_detail.configure(yscrollcommand=tcdy.set,xscrollcommand=tcdx.set)
        self.tc_detail.grid(row=0,column=0,sticky='nsew'); tcdy.grid(row=0,column=1,sticky='ns'); tcdx.grid(row=1,column=0,sticky='ew'); self.tc_detail.configure(state='disabled')
        self._tc_entries=[]

    def _build_terminology_tab(self):
        outer=ttk.Frame(self.term_tab,padding=6); outer.pack(fill='both',expand=True)
        hdr=ttk.Frame(outer); hdr.pack(fill='x')
        ttk.Label(hdr,text='Human-approved terminology + book analytics',style='Section.TLabel').pack(side='left')
        ttk.Button(hdr,text='Refresh Analytics',command=self._refresh_term_analytics).pack(side='right')
        ttk.Button(hdr,text='New Rule…',command=self._new_terminology_rule).pack(side='right',padx=4)
        split=ttk.Panedwindow(outer,orient='vertical'); split.pack(fill='both',expand=True,pady=(5,0))
        rules=ttk.LabelFrame(split,text='Trusted terminology rules',padding=4); analytics=ttk.LabelFrame(split,text='Translation Words book analytics · exceptions first',padding=4)
        split.add(rules,weight=2); split.add(analytics,weight=3)
        cols=('concept','lemma','approved','allowed','rejected','reviewer')
        trh=ttk.Frame(rules); trh.pack(fill='both',expand=True); trh.rowconfigure(0,weight=1); trh.columnconfigure(0,weight=1)
        self.term_tree=ttk.Treeview(trh,columns=cols,show='headings',selectmode='browse')
        for c,w in [('concept',160),('lemma',120),('approved',220),('allowed',200),('rejected',180),('reviewer',130)]: self.term_tree.heading(c,text=c.title()); self.term_tree.column(c,width=w,anchor='w',stretch=True)
        try_=ttk.Scrollbar(trh,orient='vertical',command=self.term_tree.yview); trx=ttk.Scrollbar(trh,orient='horizontal',command=self.term_tree.xview); self.term_tree.configure(yscrollcommand=try_.set,xscrollcommand=trx.set)
        self.term_tree.grid(row=0,column=0,sticky='nsew'); try_.grid(row=0,column=1,sticky='ns'); trx.grid(row=1,column=0,sticky='ew'); self.term_tree.bind('<<TreeviewSelect>>',self._terminology_selected)
        trd=ttk.Frame(rules); trd.pack(fill='x',pady=(4,0)); trd.rowconfigure(0,weight=1); trd.columnconfigure(0,weight=1)
        self.term_detail=tk.Text(trd,height=5,wrap='none'); trdy=ttk.Scrollbar(trd,orient='vertical',command=self.term_detail.yview); trdx=ttk.Scrollbar(trd,orient='horizontal',command=self.term_detail.xview); self.term_detail.configure(yscrollcommand=trdy.set,xscrollcommand=trdx.set)
        self.term_detail.grid(row=0,column=0,sticky='nsew'); trdy.grid(row=0,column=1,sticky='ns'); trdx.grid(row=1,column=0,sticky='ew'); self.term_detail.configure(state='disabled')
        acols=('concept','total','checked','distinct','unexplained','renderings')
        tah=ttk.Frame(analytics); tah.pack(fill='both',expand=True); tah.rowconfigure(0,weight=1); tah.columnconfigure(0,weight=1)
        self.term_analytics_tree=ttk.Treeview(tah,columns=acols,show='headings',selectmode='browse')
        for c,w in [('concept',180),('total',70),('checked',70),('distinct',70),('unexplained',90),('renderings',580)]: self.term_analytics_tree.heading(c,text=c.title()); self.term_analytics_tree.column(c,width=w,anchor='w',stretch=True)
        tay=ttk.Scrollbar(tah,orient='vertical',command=self.term_analytics_tree.yview); tax=ttk.Scrollbar(tah,orient='horizontal',command=self.term_analytics_tree.xview); self.term_analytics_tree.configure(yscrollcommand=tay.set,xscrollcommand=tax.set)
        self.term_analytics_tree.grid(row=0,column=0,sticky='nsew'); tay.grid(row=0,column=1,sticky='ns'); tax.grid(row=1,column=0,sticky='ew'); self._term_analytics=[]

    def _refresh_terminology(self):
        if not hasattr(self,'term_tree'): return
        self.term_tree.delete(*self.term_tree.get_children()); self._term_rules=[]
        if not self.project: return
        self._term_rules=self.project.terminology_rules()
        for i,r in enumerate(self._term_rules):
            self.term_tree.insert('', 'end', iid=str(i), values=(r.get('conceptId',''),r.get('sourceLemma',''),', '.join(r.get('approvedRenderings',[])),', '.join(r.get('allowedAlternatives',[])),', '.join(r.get('rejectedRenderings',[])),r.get('username','')))

    def _terminology_selected(self,event=None):
        sel=self.term_tree.selection()
        if not sel:return
        r=self._term_rules[int(sel[0])]; self._set_text(self.term_detail,json.dumps(r,ensure_ascii=False,indent=2))

    def _new_terminology_rule(self):
        if not self.project:return
        preset=''; lemma=''; strong=''; approved=''
        rs=self.review_tree.selection() if hasattr(self,'review_tree') else ()
        if rs:
            rr=self.ai_check_reviews[int(rs[0])]
            if rr.tool=='translationWords': preset=rr.group_id; approved='\n'.join(rr.proposed_selection_text)
        if not preset and hasattr(self,'tc_tree'):
            ts=self.tc_tree.selection()
            if ts:
                e=self._tc_entries[int(ts[0])]; c=e.get('contextId',{})
                if c.get('tool')=='translationWords': preset=str(c.get('groupId','')); approved='\n'.join(str(x.get('text','')) for x in e.get('selections',[]) if isinstance(x,dict)) if isinstance(e.get('selections'),list) else ''
        if self.session and preset:
            for g in self.session.current.alignments:
                if g.top_words:
                    lemma=lemma or g.top_words[0].lemma; strong=strong or g.top_words[0].strong
        win=tk.Toplevel(self); win.title('Human Terminology Rule'); win.transient(self); win.grab_set(); win.geometry('720x680')
        frm=ttk.Frame(win,padding=12); frm.pack(fill='both',expand=True)
        vars={k:tk.StringVar(value=v) for k,v in [('concept',preset),('lemma',lemma),('strong',strong),('scope','book')]}
        for row,(label,key) in enumerate([('Translation Word / concept ID','concept'),('Source lemma','lemma'),("Strong's",'strong'),('Scope','scope')]):
            ttk.Label(frm,text=label).grid(row=row,column=0,sticky='nw',pady=4); ttk.Entry(frm,textvariable=vars[key],width=55).grid(row=row,column=1,sticky='ew',pady=4)
        fields=[]; target_name=self.language_context.target_name if self.language_context else 'target-language'
        for row,(label,initial) in enumerate([(f'Approved {target_name} renderings (one per line)',approved),('Allowed contextual alternatives (one per line)',''),('Rejected renderings (one per line)',''),('Reviewer rationale / terminology note','')],start=4):
            ttk.Label(frm,text=label).grid(row=row,column=0,sticky='nw',pady=4); holder=ttk.Frame(frm); holder.grid(row=row,column=1,sticky='nsew',pady=4); holder.rowconfigure(0,weight=1); holder.columnconfigure(0,weight=1); t=tk.Text(holder,height=5 if row<7 else 7,wrap='word',font=(self.language_context.target_font if self.language_context else 'Nirmala UI',10)); ty=ttk.Scrollbar(holder,orient='vertical',command=t.yview); t.configure(yscrollcommand=ty.set); t.grid(row=0,column=0,sticky='nsew'); ty.grid(row=0,column=1,sticky='ns'); t.insert('1.0',initial); fields.append(t); frm.rowconfigure(row,weight=1 if row==7 else 0)
        frm.columnconfigure(1,weight=1)
        row=ttk.Frame(frm); row.grid(row=8,column=0,columnspan=2,sticky='ew',pady=(8,0))
        def lines(t): return [x.strip() for x in t.get('1.0','end-1c').splitlines() if x.strip()]
        def save():
            try:
                path=self.project.record_terminology_rule(vars['concept'].get(),lines(fields[0]),lines(fields[1]),lines(fields[2]),vars['lemma'].get(),vars['strong'].get(),fields[3].get('1.0','end-1c').strip(),self.settings.reviewer_name,vars['scope'].get())
                self.log(f'Terminology rule saved: {path}'); win.destroy(); self._refresh_terminology(); self.set_status('Human-approved terminology rule added to AI knowledge')
            except Exception as e: messagebox.showerror('Terminology rule',str(e),parent=win)
        ttk.Button(row,text='Save Human-Approved Rule',command=save,style='Accent.TButton').pack(side='left'); ttk.Button(row,text='Cancel',command=win.destroy).pack(side='right')

    def _build_psalms_tab(self):
        outer=ttk.Frame(self.psalms_tab,padding=6); outer.pack(fill='both',expand=True)
        hdr=ttk.Frame(outer); hdr.pack(fill='x')
        ttk.Button(hdr,text='Analyze Current Psalm',command=self._run_psalms_qa,style='Accent.TButton').pack(side='left')
        self.psalms_info_label=ttk.Label(hdr,text='Candidate structure/parallelism QA; scholarly/human structural judgment remains authoritative.',wraplength=900); self.psalms_info_label.pack(side='left',padx=10)
        self.psalms_summary_var=tk.StringVar(value='Available when a Psalms project is loaded.'); ttk.Label(outer,textvariable=self.psalms_summary_var).pack(fill='x',pady=5)
        cols=('severity','verse','code','title')
        psh=ttk.Frame(outer); psh.pack(fill='both',expand=True); psh.rowconfigure(0,weight=1); psh.columnconfigure(0,weight=1)
        self.psalms_tree=ttk.Treeview(psh,columns=cols,show='headings',selectmode='browse')
        for c,w in [('severity',90),('verse',70),('code',190),('title',750)]: self.psalms_tree.heading(c,text=c.title()); self.psalms_tree.column(c,width=w,anchor='w',stretch=True)
        psy=ttk.Scrollbar(psh,orient='vertical',command=self.psalms_tree.yview); psx=ttk.Scrollbar(psh,orient='horizontal',command=self.psalms_tree.xview); self.psalms_tree.configure(yscrollcommand=psy.set,xscrollcommand=psx.set)
        self.psalms_tree.grid(row=0,column=0,sticky='nsew'); psy.grid(row=0,column=1,sticky='ns'); psx.grid(row=1,column=0,sticky='ew')
        psd=ttk.Frame(outer); psd.pack(fill='x',pady=(5,0)); psd.rowconfigure(0,weight=1); psd.columnconfigure(0,weight=1)
        self.psalms_detail=tk.Text(psd,height=8,wrap='none'); psdy=ttk.Scrollbar(psd,orient='vertical',command=self.psalms_detail.yview); psdx=ttk.Scrollbar(psd,orient='horizontal',command=self.psalms_detail.xview); self.psalms_detail.configure(yscrollcommand=psdy.set,xscrollcommand=psdx.set)
        self.psalms_detail.grid(row=0,column=0,sticky='nsew'); psdy.grid(row=0,column=1,sticky='ns'); psdx.grid(row=1,column=0,sticky='ew'); self.psalms_detail.configure(state='disabled')
        self.psalms_tree.bind('<<TreeviewSelect>>',lambda e:self._psalms_selected())
        self._psalms_findings=[]

    def _build_production_tab(self):
        outer=ttk.Frame(self.production_tab,padding=6); outer.pack(fill='both',expand=True)
        top=ttk.Frame(outer); top.pack(fill='x')
        ttk.Button(top,text='Refresh Production Status',command=self._refresh_production).pack(side='left')
        ttk.Button(top,text='Export QA Report…',command=self._export_report,style='Accent.TButton').pack(side='left',padx=4)
        ttk.Button(top,text='Security Scan',command=self._security_scan).pack(side='left',padx=4)
        ttk.Button(top,text='Performance Benchmark',command=self._run_performance_benchmark).pack(side='left',padx=4)
        ttk.Button(top,text='Export Paratext Notes…',command=self._export_paratext_notes).pack(side='left',padx=4)
        panes=ttk.Panedwindow(outer,orient='horizontal'); panes.pack(fill='both',expand=True,pady=(6,0))
        left=ttk.Frame(panes); right=ttk.Frame(panes); panes.add(left,weight=1); panes.add(right,weight=1)
        recovery=ttk.LabelFrame(left,text='Crash recovery / transaction journal',padding=6); recovery.pack(fill='x')
        self.tx_status_var=tk.StringVar(value='No project loaded'); self.tx_status_label=ttk.Label(recovery,textvariable=self.tx_status_var,wraplength=560); self.tx_status_label.pack(anchor='w')
        ttk.Button(recovery,text='Recover Incomplete Transactions',command=self._recover_transactions).pack(anchor='w',pady=(5,0))
        git=ttk.LabelFrame(left,text='Project Git checkpoints',padding=6); git.pack(fill='x',pady=6)
        self.git_status_var=tk.StringVar(value='No project loaded'); self.git_status_label=ttk.Label(git,textvariable=self.git_status_var,wraplength=560); self.git_status_label.pack(anchor='w')
        ttk.Button(git,text='Create Human Checkpoint',command=self._git_checkpoint).pack(side='left',pady=(5,0)); ttk.Button(git,text='View Git Diff',command=self._show_git_diff).pack(side='left',padx=4,pady=(5,0))
        team=ttk.LabelFrame(left,text='Team / reviewer workflow',padding=6); team.pack(fill='x')
        self.team_role_var=tk.StringVar(value='reviewer'); ttk.Label(team,text='Current reviewer role').grid(row=0,column=0,sticky='w'); ttk.Combobox(team,textvariable=self.team_role_var,state='readonly',values=('translator','reviewer','consultant','administrator'),width=18).grid(row=0,column=1,padx=5); ttk.Button(team,text='Save Role',command=self._save_team_role).grid(row=0,column=2)
        self.team_status_var=tk.StringVar(value=''); self.team_status_label=ttk.Label(team,textvariable=self.team_status_var,wraplength=550); self.team_status_label.grid(row=1,column=0,columnspan=3,sticky='w',pady=(5,0))
        ttk.Label(team,text='Current verse assignee').grid(row=2,column=0,sticky='w',pady=(6,0))
        self.assignee_var=tk.StringVar(value=self.settings.reviewer_name); ttk.Entry(team,textvariable=self.assignee_var,width=24).grid(row=2,column=1,sticky='w',padx=5,pady=(6,0))
        ttk.Button(team,text='Assign',command=self._assign_current_verse).grid(row=2,column=2,pady=(6,0))
        ptn=ttk.LabelFrame(left,text='Paratext-compatible reviewer notes',padding=6); ptn.pack(fill='x',pady=(6,0))
        self.paratext_notes_var=tk.StringVar(value='Reviewer discussion comments are stored as Paratext Notes 1.1-compatible XML.')
        self.paratext_notes_label=ttk.Label(ptn,textvariable=self.paratext_notes_var,wraplength=550); self.paratext_notes_label.pack(anchor='w')
        ttk.Button(ptn,text='Export Notes XML…',command=self._export_paratext_notes).pack(anchor='w',pady=(5,0))
        metrics=ttk.LabelFrame(right,text='Quality / speed / cost metrics',padding=6); metrics.pack(fill='both',expand=True)
        metrics.rowconfigure(0,weight=1); metrics.columnconfigure(0,weight=1)
        self.metrics_text=tk.Text(metrics,height=15,wrap='none',font=('Consolas',9)); mty=ttk.Scrollbar(metrics,orient='vertical',command=self.metrics_text.yview); mtx=ttk.Scrollbar(metrics,orient='horizontal',command=self.metrics_text.xview); self.metrics_text.configure(yscrollcommand=mty.set,xscrollcommand=mtx.set)
        self.metrics_text.grid(row=0,column=0,sticky='nsew'); mty.grid(row=0,column=1,sticky='ns'); mtx.grid(row=1,column=0,sticky='ew'); self.metrics_text.configure(state='disabled')
        plugins=ttk.LabelFrame(right,text='Language/plugin architecture',padding=6); plugins.pack(fill='x',pady=(6,0))
        self.plugins_var=tk.StringVar(value=''); self.plugins_label=ttk.Label(plugins,textvariable=self.plugins_var,wraplength=560); self.plugins_label.pack(anchor='w')

    def _refresh_term_analytics(self):
        if not self.project or not hasattr(self,'term_analytics_tree'): return
        try: data=translation_words_book_analytics(self.project)
        except Exception as e: self.set_status(f'Terminology analytics failed: {e}'); return
        self._term_analytics=data.get('concepts',[]); self.term_analytics_tree.delete(*self.term_analytics_tree.get_children())
        for i,r in enumerate(self._term_analytics):
            render=', '.join(f"{x['text']} ({x['count']}, {x['status']})" for x in r.get('renderings',[])[:8])
            self.term_analytics_tree.insert('', 'end',iid=str(i),values=(r.get('conceptId'),r.get('total'),r.get('checked'),r.get('distinctRenderings'),r.get('unexplainedOccurrences'),render))
        self.set_status(f"Terminology analytics: {data.get('conceptCount',0)} concepts")

    def _run_psalms_qa(self):
        if not self.project: return
        if self.project.book_id!='psa':
            messagebox.showinfo('Psalms QA','Load the Psalms project to use this specialized module.'); return
        try: data=analyze_psalm_chapter(self.project,self.chapter_var.get())
        except Exception as e: messagebox.showerror('Psalms QA',str(e)); return
        self._psalms_findings=data.get('findings',[]); self.psalms_tree.delete(*self.psalms_tree.get_children())
        for i,f in enumerate(self._psalms_findings): self.psalms_tree.insert('', 'end',iid=str(i),values=(f.get('severity'),f.get('verse'),f.get('code'),f.get('title')))
        self.psalms_summary_var.set(f"Psalm {self.chapter_var.get()}: {len(self._psalms_findings)} structural QA candidate(s) · {len(data.get('repeatedHebrewLemmas',[]))} repeated Hebrew lemmas tracked")
        self._set_text(self.psalms_detail,json.dumps({'repeatedHebrewLemmas':data.get('repeatedHebrewLemmas',[])[:40],'method':data.get('method')},ensure_ascii=False,indent=2))

    def _psalms_selected(self):
        sel=self.psalms_tree.selection()
        if sel: self._set_text(self.psalms_detail,json.dumps(self._psalms_findings[int(sel[0])],ensure_ascii=False,indent=2))

    def _refresh_production(self):
        if not self.project: return
        pending=self.project.pending_transactions(); self.tx_status_var.set(f'{len(pending)} incomplete transaction(s) require recovery.' if pending else 'Transaction journal clean · no incomplete writes detected.')
        gs=GitService(self.project.path).status(); self.git_status_var.set(gs.summary if not gs.repository else f"Git branch {gs.branch} · {'uncommitted changes' if gs.dirty else 'clean'}")
        team=TeamWorkflow(self.project.companion_dir(),self.project.book_id); role=team.role_for(self.settings.reviewer_name); self.team_role_var.set(role)
        assignment=team.assignment(self.chapter_var.get(),self.verse_var.get()) if self.chapter_var.get() and self.verse_var.get() else None
        assign_text=f" · assigned to {assignment.get('assignee')} ({assignment.get('status')})" if assignment else ''
        self.team_status_var.set(f'{self.settings.reviewer_name}: {role} · final verse approval allowed: {team.can_final_approve(self.settings.reviewer_name,"verse")}{assign_text}')
        m=MetricsStore(self.project.companion_dir(),self.project.book_id).summary(); self._set_text(self.metrics_text,json.dumps(m,ensure_ascii=False,indent=2))
        ctx=self.plugin_registry.detect_project(self.project,self.session.current if self.session else None,self.project.target_verse_text(self.chapter_var.get(),self.verse_var.get()) if self.chapter_var.get() and self.verse_var.get() else '')
        self.language_context=ctx
        self.plugins_var.set(f"ACTIVE: {ctx.source_name} → {ctx.target_name} · target plugin {ctx.target_id} · script {ctx.target_script} · QA: {', '.join(ctx.qa_categories)} · detection: {ctx.detection_basis}")
        if hasattr(self,'paratext_notes_var'):
            pp=self.project.paratext_notes_path(); self.paratext_notes_var.set(f"Paratext Notes 1.1 companion: {pp} · {'available' if pp.exists() else 'no reviewer discussion notes yet'}")

    def _export_paratext_notes(self):
        if not self.project:return
        src=self.project.paratext_notes_path()
        if not src.exists():
            messagebox.showinfo('Paratext notes','No Paratext-compatible reviewer discussion notes have been recorded for this project yet.'); return
        dest=filedialog.asksaveasfilename(title='Export Paratext Notes 1.1 XML',defaultextension='.xml',filetypes=[('Paratext notes XML','*.xml'),('XML','*.xml'),('All files','*.*')],initialfile=f'{self.project.book_id}_AI_Bridge_Notes.xml')
        if not dest:return
        try:
            shutil.copy2(src,dest); self.set_status(f'Paratext notes exported: {dest}'); messagebox.showinfo('Paratext notes',f'Paratext Notes 1.1-compatible XML exported to:\n{dest}')
        except Exception as e: messagebox.showerror('Paratext notes',str(e))

    def _recover_transactions(self):
        if not self.project:return
        pending=self.project.pending_transactions()
        if not pending: messagebox.showinfo('Crash recovery','No incomplete transactions were found.'); return
        if not messagebox.askyesno('Crash recovery',f'{len(pending)} incomplete transaction(s) were found. Roll them back to their pre-write backups now?'): return
        try: out=self.project.recover_incomplete_transactions(); self._refresh_production(); self._load_verse(); messagebox.showinfo('Crash recovery',f'Recovery processed {len(out)} transaction(s).')
        except Exception as e: messagebox.showerror('Crash recovery',str(e))

    def _git_checkpoint(self):
        if not self.project:return
        msg=simpledialog.askstring('Git checkpoint','Commit message',initialvalue=f'translationCore AI Bridge human checkpoint {self.project.book_id.upper()} {self.chapter_var.get()}:{self.verse_var.get()}')
        if not msg:return
        try:
            commit=GitService(self.project.path).checkpoint(msg,author_name=self.settings.reviewer_name)
            self._refresh_production(); messagebox.showinfo('Git checkpoint',f'Created {commit[:12]}' if commit else 'No staged/project changes to commit.')
        except Exception as e: messagebox.showerror('Git checkpoint',str(e))

    def _show_git_diff(self):
        if not self.project:return
        try: text=GitService(self.project.path).diff() or 'No unstaged Git diff.'
        except Exception as e: text=str(e)
        win=tk.Toplevel(self); win.title('Project Git Diff'); win.geometry('1000x700'); holder=ttk.Frame(win); holder.pack(fill='both',expand=True); holder.rowconfigure(0,weight=1); holder.columnconfigure(0,weight=1); t=tk.Text(holder,wrap='none',font=('Consolas',9)); gy=ttk.Scrollbar(holder,orient='vertical',command=t.yview); gx=ttk.Scrollbar(holder,orient='horizontal',command=t.xview); t.configure(yscrollcommand=gy.set,xscrollcommand=gx.set); t.grid(row=0,column=0,sticky='nsew'); gy.grid(row=0,column=1,sticky='ns'); gx.grid(row=1,column=0,sticky='ew'); t.insert('1.0',text); t.configure(state='disabled')

    def _save_team_role(self):
        if not self.project:return
        try:
            tw=TeamWorkflow(self.project.companion_dir(),self.project.book_id); tw.add_member(self.settings.reviewer_name,self.team_role_var.get()); self._refresh_production(); self.set_status('Reviewer role saved')
        except Exception as e: messagebox.showerror('Team workflow',str(e))

    def _assign_current_verse(self):
        if not self.project:return
        assignee=self.assignee_var.get().strip()
        if not assignee:
            messagebox.showwarning('Team workflow','Enter an assignee name.'); return
        try:
            tw=TeamWorkflow(self.project.companion_dir(),self.project.book_id); tw.assign(self.chapter_var.get(),self.verse_var.get(),assignee,'assigned'); self._refresh_production(); self.set_status(f'Assigned {self.project.book_id.upper()} {self.chapter_var.get()}:{self.verse_var.get()} to {assignee}')
        except Exception as e: messagebox.showerror('Team workflow',str(e))

    def _export_report(self):
        if not self.project:return
        folder=filedialog.askdirectory(title='Choose folder for QA report')
        if not folder:return
        try:
            out=ReportService(self.project).export(Path(folder)); messagebox.showinfo('QA report','Created\n'+'\n'.join(out.values())); self.set_status('Publication QA report exported')
        except Exception as e: messagebox.showerror('QA report',str(e))

    def _security_scan(self):
        findings=scan_tree_for_secrets(Path(__file__).resolve().parent.parent)
        if findings: messagebox.showwarning('Security scan','Potential secret pattern(s) found\n'+'\n'.join(findings[:20]))
        else: messagebox.showinfo('Security scan','No API-key/Bearer-token patterns were found in the application source/package tree.')

    def _run_performance_benchmark(self):
        if not self.project:return
        project=self.project
        def work():
            import time
            t=time.perf_counter(); verses=groups=checks=0
            for ch in project.chapters():
                data=project.load_alignment_chapter(ch)
                for vs,raw in data.items():
                    if str(vs)=='front':continue
                    verses+=1; groups+=len(raw.get('alignments',[])) if isinstance(raw,dict) else 0
                checks+=len([e for e in project._load_index_tool('translationNotes') if str(e.get('contextId',{}).get('reference',{}).get('chapter'))==str(ch)])
                checks+=len([e for e in project._load_index_tool('translationWords') if str(e.get('contextId',{}).get('reference',{}).get('chapter'))==str(ch)])
            return {'seconds':time.perf_counter()-t,'verses':verses,'groups':groups,'checks':checks}
        def done(r): self._end_job('Performance benchmark complete'); messagebox.showinfo('Performance',f"Scanned {r['verses']:,} verses, {r['groups']:,} alignment groups and {r['checks']:,} indexed checks in {r['seconds']:.2f}s.")
        self._background('Benchmarking full project',work,done,determinate=False,ai_operation=False)

    def _build_settings_tab(self):
        outer=ttk.Frame(self.settings_tab,padding=8); outer.pack(fill='both',expand=True)
        api=ttk.LabelFrame(outer,text='OpenAI API · security · model routing',padding=8); api.pack(fill='x')
        ttk.Label(api,text='API key').grid(row=0,column=0,sticky='w')
        self.api_key_var=tk.StringVar(value=self.settings.get_api_key()); ttk.Entry(api,textvariable=self.api_key_var,show='•').grid(row=0,column=1,sticky='ew',padx=6)
        self.persist_key_var=tk.BooleanVar(value=True); ttk.Checkbutton(api,text='Protect with Windows DPAPI and remember on this PC',variable=self.persist_key_var).grid(row=1,column=1,sticky='w')
        ttk.Label(api,text='Routing profile').grid(row=2,column=0,sticky='w',pady=(6,0))
        self.routing_profile_var=tk.StringVar(value=str(self.settings.get_setting('routing_profile','balanced'))); ttk.Combobox(api,textvariable=self.routing_profile_var,state='readonly',values=('economy','balanced','quality','fixed'),width=16).grid(row=2,column=1,sticky='w',padx=6,pady=(6,0))
        ttk.Label(api,text='Fixed/test model').grid(row=3,column=0,sticky='w',pady=(6,0))
        self.model_var=tk.StringVar(value=self.settings.model); ttk.Entry(api,textvariable=self.model_var,width=28).grid(row=3,column=1,sticky='w',padx=6,pady=(6,0))
        ttk.Label(api,text='Reviewer name').grid(row=4,column=0,sticky='w',pady=(6,0))
        self.reviewer_name_var=tk.StringVar(value=self.settings.reviewer_name); ttk.Entry(api,textvariable=self.reviewer_name_var,width=32).grid(row=4,column=1,sticky='w',padx=6,pady=(6,0))
        ttk.Label(api,text='Session cost warning (USD)').grid(row=5,column=0,sticky='w',pady=(6,0))
        self.cost_warning_var=tk.StringVar(value=str(self.settings.get_setting('cost_warning_usd','5.00'))); ttk.Entry(api,textvariable=self.cost_warning_var,width=12).grid(row=5,column=1,sticky='w',padx=6,pady=(6,0))
        buttons=ttk.Frame(api); buttons.grid(row=0,column=2,rowspan=6,padx=8,sticky='n')
        ttk.Button(buttons,text='Save Settings',command=self._save_settings).pack(fill='x'); ttk.Button(buttons,text='Test API Connection',command=self._test_api_connection).pack(fill='x',pady=(6,0)); ttk.Button(buttons,text='What Was Sent to AI?',command=self._show_privacy_manifest).pack(fill='x',pady=(6,0))
        api.columnconfigure(1,weight=1)
        safety=ttk.LabelFrame(outer,text='Production safety boundary',padding=8); safety.pack(fill='x',pady=8)
        self.safety_label=ttk.Label(safety,text='AI never silently modifies Scripture or marks checks human-complete. Human-approved Scripture/alignment/TN/TW writes use backups, atomic JSON, durable transaction journals, rollback and audit history. Translation Helps and source-language resources remain read-only. API credentials are never written into project files.',wraplength=1180); self.safety_label.pack(anchor='w')
        logs=ttk.LabelFrame(outer,text='Session log / API diagnostics',padding=4); logs.pack(fill='both',expand=True)
        logs.rowconfigure(0,weight=1); logs.columnconfigure(0,weight=1)
        self.log_text=tk.Text(logs,height=16,wrap='none'); lgy=ttk.Scrollbar(logs,orient='vertical',command=self.log_text.yview); lgx=ttk.Scrollbar(logs,orient='horizontal',command=self.log_text.xview); self.log_text.configure(yscrollcommand=lgy.set,xscrollcommand=lgx.set)
        self.log_text.grid(row=0,column=0,sticky='nsew'); lgy.grid(row=0,column=1,sticky='ns'); lgx.grid(row=1,column=0,sticky='ew'); self.log_text.configure(state='disabled')

    def log(self, msg: str):
        safe = sanitize_for_log(msg)
        self.log_text.configure(state='normal'); self.log_text.insert('end', safe.rstrip()+'\n'); self.log_text.see('end'); self.log_text.configure(state='disabled')

    def set_status(self,msg):
        self.status_var.set(msg); self.update_idletasks()

    def _set_api_indicator(self, state, text=None):
        self._api_state = state
        if not hasattr(self, 'api_dot'): return
        colors = {'connected':('#b7f7c6','#19a84a'), 'error':('#ffd0d0','#d93025'), 'testing':('#fff0b3','#e5a000'), 'unknown':('#e5e7eb','#8a8f98')}
        outer, inner = colors.get(state, colors['unknown'])
        self.api_dot.delete('all')
        self.api_dot.create_oval(2,2,20,20,fill=outer,outline='')
        self.api_dot.create_oval(6,6,16,16,fill=inner,outline='')
        if text is not None and hasattr(self,'api_status_var'):
            self.api_status_var.set(text)

    def _begin_job(self, label, determinate=False):
        self._active_job_label = label
        self.set_status(label + '…')
        self.job_progress.stop()
        self.job_progress.configure(mode='determinate' if determinate else 'indeterminate')
        if determinate:
            self.job_progress['value'] = 1
        else:
            self.job_progress['value'] = 0; self.job_progress.start(12)

    def _job_progress(self, value, message=None):
        if threading.current_thread() is threading.main_thread():
            self._apply_job_progress(value,message)
        else:
            self._ui_queue.put(('progress',value,message))

    def _apply_job_progress(self,value,message=None):
        try:
            self.job_progress.stop(); self.job_progress.configure(mode='determinate'); self.job_progress['value'] = max(0,min(100,float(value)))
            if message: self.set_status(message)
        except tk.TclError: pass

    def _end_job(self, message='Ready'):
        self.job_progress.stop(); self.job_progress.configure(mode='determinate'); self.job_progress['value'] = 0
        self._active_job_label = ''; self.set_status(message)

    def _auto_test_api(self):
        if self._busy or not self.settings.get_api_key(): return
        self._test_api_connection(silent=True)

    def _test_api_connection(self, silent=False):
        try:
            self._save_settings(silent=True); client=OpenAIResponsesClient(self.settings.get_api_key(), self.settings.model)
        except Exception as e:
            self._set_api_indicator('error','API configuration error'); self.set_status(str(e))
            if not silent: messagebox.showerror('API configuration',str(e))
            return
        self._set_api_indicator('testing','Testing API…')
        def success(info):
            model=str(info.get('id',client.model)); self._set_api_indicator('connected',f'API Connected · {model}'); self.log(f'OpenAI API authenticated for model {model}'); self._end_job('OpenAI API connected')
            if not silent: messagebox.showinfo('OpenAI API',f'Connected successfully.\nModel: {model}')
        self._background('Testing OpenAI API access',client.test_connection,success,determinate=False,ai_operation=True)

    def _clear_transient_ai_panels(self, keep_summary=True):
        self.pending_ai_proposal=None
        if hasattr(self,'apply_ai_btn'): self.apply_ai_btn.configure(state='disabled')
        if hasattr(self,'ai_preview'): self._set_text(self.ai_preview,'')
        if hasattr(self,'review_detail'): self._set_text(self.review_detail,'')
        if hasattr(self,'review_tree'):
            for iid in self.review_tree.selection(): self.review_tree.selection_remove(iid)
        if not keep_summary and hasattr(self,'review_summary_var'):
            self.review_summary_var.set('Ready for the next AI review.')

    def _open_user_guide(self):
        base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
        path=base/'userguide'/'index.html'
        if not path.exists():
            # Source-tree fallback when __file__ is nested under tc_ai_bridge/.
            path=Path(__file__).resolve().parent.parent/'userguide'/'index.html'
        if not path.exists():
            messagebox.showerror('User Guide',f'User guide not found:\n{path}'); return
        try:
            webbrowser.open(path.as_uri()); self.set_status('Opened local user guide')
        except Exception as e:
            messagebox.showerror('User Guide',str(e))

    def _cancel_batch(self):
        if self._busy:
            self._cancel_event.set(); self.set_status('Cancellation requested — current API call will finish, then batch will stop')

    def _scan_summary_text(self, scan: dict) -> str:
        a=scan.get('alignment',{}); tn=scan.get('translationNotes',{}); tw=scan.get('translationWords',{}); ar=scan.get('aiReview',{}); hd=scan.get('humanDecisions',{})
        return (f"{scan.get('bookId','').upper()} · {scan.get('verses',0)} verses | Alignment complete {a.get('complete',0)}, partial {a.get('partial',0)}, untouched {a.get('untouched',0)} | "
                f"TN checked {tn.get('checked',0)}/{tn.get('total',0)} (invalidated {tn.get('invalidated',0)}) | TW checked {tw.get('checked',0)}/{tw.get('total',0)} (invalidated {tw.get('invalidated',0)}) | "
                f"AI review current {ar.get('current',0)}, stale {ar.get('stale',0)}, missing {ar.get('missing',0)} | Human decisions accepted {hd.get('accepted',0)}, discussion {hd.get('needs_discussion',0)}, rejected {hd.get('rejected',0)}")

    def _render_dashboard_scan(self, scan: dict):
        self.project_scan_data=scan
        self.dashboard_summary_var.set(self._scan_summary_text(scan))
        a=scan.get('alignment',{}); tn=scan.get('translationNotes',{}); tw=scan.get('translationWords',{}); ar=scan.get('aiReview',{}); ws=scan.get('workState',{}); hd=scan.get('humanDecisions',{})
        lines=[f"PROJECT ANALYSIS — {scan.get('bookId','').upper()}", '', f"Verses: {scan.get('verses',0)}", '', 'WORD ALIGNMENT', f"  Complete:  {a.get('complete',0)}", f"  Partial:   {a.get('partial',0)}", f"  Untouched: {a.get('untouched',0)}", '', 'TRANSLATION NOTES', f"  Checked:     {tn.get('checked',0)}", f"  Pending:     {tn.get('pending',0)}", f"  Invalidated: {tn.get('invalidated',0)}", '', 'TRANSLATION WORDS', f"  Checked:     {tw.get('checked',0)}", f"  Pending:     {tw.get('pending',0)}", f"  Invalidated: {tw.get('invalidated',0)}", '', 'AI REVIEW CACHE', f"  Current: {ar.get('current',0)}", f"  Stale:   {ar.get('stale',0)}", f"  Missing: {ar.get('missing',0)}", '', 'WORK STATES']
        for k,v in sorted(ws.items()): lines.append(f"  {k}: {v}")
        lines += ['', 'HUMAN DECISIONS', f"  Accepted: {hd.get('accepted',0)}", f"  Needs discussion: {hd.get('needs_discussion',0)}", f"  Rejected AI: {hd.get('rejected',0)}", '', f"Verse edit records: {scan.get('verseEdits',0)} · Comments: {scan.get('comments',0)}"]
        self._set_text(self.dashboard_scan,'\n'.join(lines))
        self._refresh_exception_queue()

    def _refresh_dashboard_background(self):
        if not self.project or self._busy: return
        project=self.project
        def success(scan):
            if self.project is project:
                self._render_dashboard_scan(scan); self._end_job('Project scan complete')
        self._background('Scanning project state', project.project_scan, success, determinate=False, ai_operation=False)

    @staticmethod
    def _severity_counts(saved: dict) -> dict[str,int]:
        counts={s:0 for s in ('critical','high','medium','editorial','info')}
        for d in saved.get('qaIssues',[]) if isinstance(saved.get('qaIssues'),list) else []:
            sev=str(d.get('severity','medium')).lower(); counts[sev]=counts.get(sev,0)+1
        for d in saved.get('checkReviews',[]) if isinstance(saved.get('checkReviews'),list) else []:
            verdict=str(d.get('verdict','review')).lower()
            if verdict in ('problem','review') or float(d.get('confidence',0) or 0)<0.7:
                sev=str(d.get('severity','medium')).lower(); counts[sev]=counts.get(sev,0)+1
        return counts

    def _refresh_exception_queue(self):
        if not self.project or not hasattr(self,'exception_tree'): return
        try: raw=exception_first_queue(self.project)
        except Exception as e:
            self.log(f'Exception queue failed: {e}'); return
        rows=[]
        for r in raw:
            counts={'critical':r.get('critical',0),'high':r.get('high',0),'medium':r.get('medium',0)}
            reason_bits=[]
            if r.get('wordAlignment')=='invalid': reason_bits.append('WA invalid')
            if r.get('invalidChecks'): reason_bits.append(f"{r['invalidChecks']} stale/invalid tC")
            if r.get('discussions'): reason_bits.append(f"{r['discussions']} discussion")
            summary='; '.join(reason_bits+[str(r.get('summary',''))]).strip('; ')
            rows.append({'chapter':r['chapter'],'verse':r['verse'],'cache':r.get('cache',''),'counts':counts,'checks':int(r.get('invalidChecks',0))+int(r.get('discussions',0)),'summary':summary})
        self._exception_rows=rows; self.exception_tree.delete(*self.exception_tree.get_children())
        for i,r in enumerate(rows):
            c=r['counts']; self.exception_tree.insert('', 'end', iid=str(i), values=(f"{r['chapter']}:{r['verse']}",str(r['cache']).upper(),c.get('critical',0),c.get('high',0),c.get('medium',0),r['checks'],r['summary'][:260]))
        self._resize_tree_columns()

    def _dashboard_open_selected(self,event=None):
        sel=self.exception_tree.selection()
        if not sel:return
        r=self._exception_rows[int(sel[0])]
        self.chapter_var.set(r['chapter']); self._chapter_changed(force=True); self.verse_var.set(r['verse']); self._load_verse(); self.notebook.select(self.review_tab)

    def _open_highest_priority(self):
        children=self.exception_tree.get_children()
        if not children:
            messagebox.showinfo('Exception queue','No Critical/High/stale cached findings are currently available. Run changed/untouched preparation first.'); return
        self.exception_tree.selection_set(children[0]); self._dashboard_open_selected()

    def _browse_root(self):
        p=filedialog.askdirectory(title='Choose translationCore data folder')
        if p: self.root_var.set(p); self.load_root(p)

    def load_root(self,path):
        self._begin_job('Loading translationCore backend',determinate=True); self._job_progress(10,'Scanning translationCore projects and resources…')
        try:
            root=TranslationCoreRoot(path); projects=root.projects()
            if not projects: raise ProjectError('No compatible translationCore projects were found.')
            self.tc_root=root; self.projects=projects; self.root_var.set(str(root.path))
            self.project_combo['values']=[p.summary.display_name for p in projects]
            self.project_combo.current(0); self._project_changed()
            self.log(f'Loaded translationCore root: {root.path} ({len(projects)} projects)'); self._job_progress(100,'translationCore backend loaded'); self._end_job(f'Loaded {len(projects)} projects')
            try:
                if self.state() != 'withdrawn': self.after(120,self._refresh_dashboard_background)
            except tk.TclError: pass
        except Exception as e: self._end_job('Load failed'); messagebox.showerror('Load failed',str(e)); self.log(f'ERROR loading root: {e}')

    def _confirm_discard(self):
        if not self.session or not self.session.dirty: return True
        ans=messagebox.askyesnocancel('Unsaved alignment','Save the current alignment before navigating away?')
        if ans is None: return False
        if ans: return self._save()
        return True

    def _project_changed(self,event=None):
        if self.session and self.session.dirty and not self._confirm_discard(): return
        i=self.project_combo.current()
        if i<0: return
        self.project=self.projects[i]
        pending=self.project.pending_transactions()
        if pending:
            recover=False
            try:
                if self.state()!='withdrawn': recover=messagebox.askyesno('Crash recovery required',f'{len(pending)} incomplete project transaction(s) were found from a prior interrupted session. Roll them back to their safe pre-write backups now?')
            except tk.TclError: pass
            if recover:
                try: self.project.recover_incomplete_transactions(); self.log(f'Recovered {len(pending)} interrupted transaction(s).')
                except Exception as e: messagebox.showerror('Crash recovery',str(e))
        try:
            self.kb=TranslationHelpsKnowledgeBase(self.project)
        except Exception as e:
            self.kb=None; self.log(f'Knowledge Base unavailable: {e}')
        s=self.project.summary; self.project_info_var.set(f'tC {s.tc_version} / {s.edit_version}')
        ch=self.project.chapters(); self.chapter_combo['values']=ch
        if ch: self.chapter_combo.set(ch[0]); self._chapter_changed(force=True)
        self.dashboard_summary_var.set(f'{s.display_name}: project scan pending…')
        self._set_text(self.dashboard_scan,'Project selected. Refreshing scan will classify alignment, tC checks, cached AI reviews, stale work and human decisions.')
        self.exception_tree.delete(*self.exception_tree.get_children()); self._exception_rows=[]
        self.log(f'Project: {s.display_name}; checkData={self.project.check_types()}; index={self.project.index_tools()}')
        self._refresh_production(); self._refresh_term_analytics()

    def _chapter_changed(self,event=None,force=False):
        if not force and self.session and self.session.dirty and not self._confirm_discard(): return
        if not self.project:return
        verses=self.project.verses(self.chapter_var.get()); self.verse_combo['values']=verses
        if verses:
            # Front matter is valid tC data but usually has no alignment tokens. Open the
            # first numbered verse by default so the application never appears blank.
            first = next((v for v in verses if v != 'front'), verses[0])
            self.verse_combo.set(first); self._load_verse()

    def _verse_changed(self,event=None):
        if self.session and self.session.dirty and not self._confirm_discard(): return
        self._load_verse()

    def _load_verse(self):
        if not self.project:return
        ch=self.chapter_var.get(); vs=self.verse_var.get()
        if not ch or not vs:return
        try:
            raw=self.project.load_alignment_chapter(ch)[vs]
            alignment=self.project.load_verse_alignment(ch,vs)
            self.original_verse_raw=copy.deepcopy(raw); self.session=EditSession(alignment); self.pending_ai_proposal=None; self.apply_ai_btn.configure(state='disabled'); self.ai_issues=[]; self.ai_check_reviews=[]; self.review_alignment_for_checks=None; self.review_meta={}
            self.language_context=self.plugin_registry.detect_project(self.project, alignment, self.project.target_verse_text(ch,vs)); self._apply_language_context()
            self._set_text(self.verse_text,self.project.target_verse_text(ch,vs))
            self._set_text(self.ai_preview,'')
            self._refresh_alignment(); self._refresh_tc_checks(); self._refresh_kb(); self._refresh_terminology(); self._load_saved_review(); self._run_local_qa()
            self.set_status(f'Loaded {self.project.book_id.upper()} {ch}:{vs}')
        except Exception as e: messagebox.showerror('Verse load failed',str(e)); self.log(traceback.format_exc())

    @staticmethod
    def _set_text(widget: tk.Text,text: str):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('1.0',text); widget.configure(state='disabled')

    def _refresh_alignment(self):
        if not self.session:return
        inv=make_inventory(self.session.current)
        aligned_t={t.signature for t in self.session.current.aligned_bottom()}; bank={t.signature for t in self.session.current.word_bank}
        self.top_list.delete(0,'end'); self.bottom_list.delete(0,'end'); self.group_list.delete(0,'end')
        if hasattr(self,'compact_group_list'): self.compact_group_list.delete(0,'end')
        self._top_tokens=inv.top; self._bottom_tokens=inv.bottom
        for t in inv.top:self.top_list.insert('end',token_label(t,True))
        for t in inv.bottom:
            state='UNALIGNED' if t.signature in bank else 'aligned'
            self.bottom_list.insert('end',f'{token_label(t)}  — {state}')
        for n,g in enumerate(self.session.current.alignments,1):
            h=' '.join(x.word for x in g.top_words) or '∅'; t=' '.join(x.word for x in g.bottom_words) or '∅'
            row=f'{n:03d}  {h}  ⇄  {t}'; self.group_list.insert('end',row)
            if hasattr(self,'compact_group_list'): self.compact_group_list.insert('end',row)
        dirty=' *unsaved*' if self.session.dirty else ''
        self.set_status(f'{len(inv.top)} {self.language_context.source_name if self.language_context else "source"}; {len(inv.bottom)} {self.language_context.target_name if self.language_context else "target"}; {len(self.session.current.word_bank)} target unaligned{dirty}')

    def _selected_tokens(self):
        tops=[self._top_tokens[i] for i in self.top_list.curselection()]
        bottoms=[self._bottom_tokens[i] for i in self.bottom_list.curselection()]
        return tops,bottoms

    def _connect_selected(self):
        if not self.session:return
        try:
            tops,bottoms=self._selected_tokens(); self.session.replace(realign(self.session.current,tops,bottoms)); self._refresh_alignment(); self._run_local_qa()
        except AlignmentError as e: messagebox.showwarning('Selection',str(e))

    def _unalign_selected(self):
        if not self.session:return
        try:
            _,bottoms=self._selected_tokens(); self.session.replace(unalign_bottom(self.session.current,bottoms)); self._refresh_alignment(); self._run_local_qa()
        except AlignmentError as e: messagebox.showwarning('Selection',str(e))

    def _undo(self):
        if self.session and self.session.undo(): self._refresh_alignment(); self._run_local_qa()
    def _redo(self):
        if self.session and self.session.redo(): self._refresh_alignment(); self._run_local_qa()

    def _get_client(self, task='final_review', severity='medium', ambiguous=False):
        self._save_settings(silent=True)
        profile=str(self.settings.get_setting('routing_profile','balanced'))
        router=ModelRouter(profile,self.settings.model)
        choice=router.choose(task,severity,ambiguous)
        client=OpenAIResponsesClient(self.settings.get_api_key(),choice.model,reasoning_effort=choice.reasoning_effort)
        client.routing_choice=choice
        return client

    def _update_ai_usage(self, client, label='Tokens', total_override=None, cost_override=None):
        usage=getattr(client,'last_usage',None)
        total=int(total_override if total_override is not None else (getattr(usage,'total_tokens',0) or 0)) if usage or total_override is not None else 0
        self.usage_var.set(f'{label} {total:,}')
        cost=float(cost_override if cost_override is not None else (getattr(client,'last_cost_usd',0.0) or 0.0)); self.cost_var.set(f'Cost ${cost:.4f}')
        if self.project:
            try:
                MetricsStore(self.project.companion_dir(),self.project.book_id).event('ai_call',model=getattr(client,'model',''),reasoning=getattr(client,'reasoning_effort',''),input_tokens=int(getattr(usage,'input_tokens',0) or 0) if usage else 0,output_tokens=int(getattr(usage,'output_tokens',0) or 0) if usage else 0,total_tokens=total,estimated_cost_usd=cost)
            except Exception: pass
        try:
            warn=float(self.settings.get_setting('cost_warning_usd','5.00') or 5.0)
            if self.project and MetricsStore(self.project.companion_dir(),self.project.book_id).summary().get('estimatedCostUSD',0)>=warn:
                self.status_var.set(self.status_var.get()+f' · Cost warning ≥ ${warn:.2f}')
        except Exception: pass

    def _background(self,label,fn,on_success,determinate=False,ai_operation=False):
        if self._busy:
            self.set_status(f'Busy: {self._active_job_label or "another operation"}')
            return False
        self._busy=True; self._bg_success_handler=on_success; self._bg_is_ai=bool(ai_operation); self._begin_job(label,determinate=determinate)
        # Polling is scheduled from the UI thread; workers never call tkinter directly.
        self.after(20,self._poll_ui_queue)
        # Do not let the worker closure retain the Tk root merely to reach its queue.
        # This is especially important during shutdown: a late-finishing worker must not
        # become the thread that releases the final reference to a Tk interpreter.
        ui_queue=self._ui_queue
        work_fn=fn
        def worker():
            try:
                result=work_fn(); ui_queue.put(('done',result))
            except Exception as e:
                ui_queue.put(('error',e,traceback.format_exc()))
        thread=threading.Thread(target=worker,daemon=True)
        self._worker_threads.append(thread)
        thread.start()
        return True

    def _poll_ui_queue(self):
        if self._closing:
            return
        try:
            while True:
                item=self._ui_queue.get_nowait(); kind=item[0]
                if kind=='progress':
                    self._apply_job_progress(item[1],item[2])
                elif kind=='done':
                    handler=self._bg_success_handler; self._bg_success_handler=None
                    self._finish_bg(None,item[1],handler)
                elif kind=='log':
                    self.log(item[1])
                elif kind=='error':
                    self.log(item[2]); handler=self._bg_success_handler; self._bg_success_handler=None
                    self._finish_bg(item[1],None,handler)
        except queue.Empty:
            pass
        if self._busy and not self._closing:
            self.after(30,self._poll_ui_queue)

    def _finish_bg(self,error,result,on_success):
        self._busy=False; self.job_progress.stop(); is_ai=self._bg_is_ai; self._bg_is_ai=False
        # The worker has already queued its terminal message; wait briefly for its stack to
        # unwind on the main thread side so Tk-owned application objects are never finalized
        # by a just-ending worker thread.
        for thread in list(self._worker_threads):
            if thread is not threading.current_thread():
                thread.join(timeout=0.25)
        self._worker_threads=[t for t in self._worker_threads if t.is_alive()]
        if hasattr(self,'cancel_batch_btn'):
            try:self.cancel_batch_btn.configure(state='disabled')
            except tk.TclError:pass
        if error:
            if is_ai:
                self._set_api_indicator('error','API error / disconnected')
            self._end_job(('AI operation failed' if is_ai else 'Operation failed') + ' — see error/log')
            self.log(f'{"AI " if is_ai else ""}ERROR: {error}')
            messagebox.showerror('AI operation failed' if is_ai else 'Operation failed',str(error)); return
        try:
            if on_success: on_success(result)
        except Exception as e:
            self._end_job('Operation result handling failed')
            self.log('RESULT HANDLER ERROR: '+traceback.format_exc())
            messagebox.showerror('Operation result failed',str(e)); return
        if is_ai and self._api_state in ('testing','unknown','error'):
            self._set_api_indicator('connected',f'API Connected · {self.settings.model}')
        if self._active_job_label:
            self._end_job('Ready')

    def _ai_suggest(self):
        if not self.project or not self.session:return
        try: client=self._get_client('alignment')
        except Exception as e: messagebox.showerror('API configuration',str(e)); return
        ch=self.chapter_var.get();vs=self.verse_var.get(); current=copy.deepcopy(self.session.current)
        def success(proposal):
            try: groups=validate_proposal(current,proposal)
            except Exception as e: messagebox.showerror('Unsafe AI proposal rejected',str(e)); self.log(f'Proposal rejected: {e}'); return
            self.pending_ai_proposal=proposal; self.apply_ai_btn.configure(state='normal')
            self._render_ai_proposal(current,proposal); self._update_ai_usage(client); self.set_status('AI proposal validated; not yet applied')
            self.log(f'AI alignment proposal validated for {self.project.book_id} {ch}:{vs}: {len(groups)} groups')
        self._background('Requesting AI alignment',lambda:client.propose_alignment(self.project,ch,vs,current),success,ai_operation=True)

    def _apply_ai(self):
        if not self.session or not self.pending_ai_proposal:return
        try:
            value=apply_proposal(self.session.current,self.pending_ai_proposal); self.session.replace(value); self.pending_ai_proposal=None; self.apply_ai_btn.configure(state='disabled'); self._set_text(self.ai_preview,''); self._refresh_alignment(); self._run_local_qa(); self.set_status('AI proposal applied in memory — review before saving')
        except Exception as e: messagebox.showerror('Proposal rejected',str(e))

    def _save(self):
        if not self.project or not self.session:return False
        ch=self.chapter_var.get();vs=self.verse_var.get()
        try:
            backup=self.project.save_verse_alignment(ch,vs,self.session.current,self.original_verse_raw)
            completed=self.project.mark_word_alignment_completed(ch,vs,self.settings.reviewer_name)
            self.original_verse_raw=copy.deepcopy(self.session.current.to_dict()); self.session.mark_saved(); self._refresh_alignment(); self._run_local_qa(); self._refresh_tc_checks(); self.log(f'Saved {self.project.book_id} {ch}:{vs}; backup: {backup}; tC completed: {completed}'); messagebox.showinfo('Saved',f'Approved alignment saved and translationCore Word Alignment marked completed.\nBackup created at:\n{backup}'); return True
        except Exception as e: messagebox.showerror('Save blocked',str(e)); self.log(f'SAVE BLOCKED: {e}'); return False

    def _approve(self):
        if not self.project or not self.session:return
        ch=self.chapter_var.get(); vs=self.verse_var.get()
        team = TeamWorkflow(self.project.companion_dir(), self.project.book_id)
        if not team.can_final_approve(self.settings.reviewer_name, 'verse'):
            messagebox.showwarning('Final verse approval', f'{self.settings.reviewer_name} is assigned role {team.role_for(self.settings.reviewer_name).upper()}, which is not permitted to give final verse approval under the current team policy.')
            self.set_status('Verse approval blocked by team workflow policy')
            return
        if self.session.dirty and not self._save():return
        cache=self.project.ai_review_cache_status(ch,vs)
        decisions=self.project.qa_decisions_for_verse(ch,vs)
        blockers=[]
        for i,x in enumerate(self.ai_issues):
            if x.severity not in ('critical','high'): continue
            key=self._qa_issue_key(x)
            d=decisions.get(key,{})
            if str(d.get('decision','')).lower()=='rejected': continue
            blockers.append(x)
        if cache!='current':
            if not messagebox.askyesno('Final verse approval',f'This verse does not have a CURRENT AI evidence review (status: {cache.upper()}).\n\nApprove anyway as a human override?'):
                self.set_status('Verse approval cancelled — run AI Full Verse Review first'); return
        elif blockers:
            if not messagebox.askyesno('Final verse approval',f'{len(blockers)} Critical/High AI QA finding(s) are still visible for this verse.\n\nApprove anyway as an explicit human override?'):
                self.set_status('Verse approval cancelled — review high-priority findings first'); return
        p=self.project.record_review_state(ch,vs,'approved',note='Human final approval')
        self.log(f'Approved review state: {p}'); self.set_status('Verse approved by human reviewer'); self._refresh_exception_queue()

    def _restore_latest(self):
        if not self.project:return
        ch=self.chapter_var.get(); backups=self.project.list_alignment_backups(ch)
        if not backups:
            messagebox.showinfo('Restore','No translationCore AI Bridge backups exist for this chapter yet.'); return
        if self.session and self.session.dirty:
            messagebox.showwarning('Restore blocked','Save or discard the current unsaved alignment before restoring a backup.'); return
        b=backups[0]
        if not messagebox.askyesno('Restore backup',f'Restore the latest chapter {ch} alignment backup?\n\n{b}\n\nThe current chapter will also be backed up first.'):
            return
        try:
            safety=self.project.restore_alignment_backup(ch,b); self.log(f'Restored {b}; pre-restore safety backup: {safety}'); self._load_verse(); messagebox.showinfo('Restored','Backup restored and verified. The pre-restore state was also backed up.')
        except Exception as e:
            messagebox.showerror('Restore failed',str(e)); self.log(f'RESTORE FAILED: {e}')

    def _run_local_qa(self):
        if not self.project or not self.session:return
        local=run_local_qa(self.project,self.chapter_var.get(),self.verse_var.get(),self.session.current)
        self._qa_items=local+self.ai_issues; self._refresh_qa_tree()
        counts={s:sum(1 for x in self._qa_items if x.severity==s) for s in ('critical','high','medium','editorial','info')}
        self.qa_summary_var.set(' | '.join(f'{k}: {v}' for k,v in counts.items()))

    def _qa_issue_key(self, issue: QAIssue) -> str:
        payload=json.dumps(issue.to_dict(),ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return f"{issue.source}:{issue.code}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"

    def _refresh_qa_tree(self):
        self.qa_tree.delete(*self.qa_tree.get_children())
        decisions=self.project.qa_decisions_for_verse(self.chapter_var.get(),self.verse_var.get()) if self.project else {}
        for i,x in enumerate(self._qa_items):
            d=decisions.get(self._qa_issue_key(x),{})
            status=str(d.get('decision','')).replace('_',' ').upper() or 'UNREVIEWED'
            self.qa_tree.insert('', 'end', iid=str(i), values=(x.severity.upper(),x.source,status,x.title))

    def _qa_selected(self,event=None):
        sel=self.qa_tree.selection()
        if not sel:return
        x=self._qa_items[int(sel[0])]; conf=f'\nConfidence: {x.confidence:.0%}' if x.confidence is not None else ''
        d=self.project.qa_decisions_for_verse(self.chapter_var.get(),self.verse_var.get()).get(self._qa_issue_key(x),{}) if self.project else {}
        human=f"\n\nHuman decision: {str(d.get('decision','UNREVIEWED')).upper()}"
        if d.get('note'): human += f"\nReviewer note: {d.get('note')}"
        self._set_text(self.qa_detail,f'{x.title}\n\n{x.detail}\n\nSource: {x.source}\nCode: {x.code}{conf}{human}')

    def _record_qa_decision(self, decision: str):
        if not self.project:return
        sel=self.qa_tree.selection()
        if not sel:
            messagebox.showinfo('QA decision','Select a QA finding first.'); return
        x=self._qa_items[int(sel[0])]; note=''
        if decision in ('accepted','needs_discussion','rejected'):
            try:
                if self.state() != 'withdrawn': note=simpledialog.askstring('QA reviewer note','Optional reviewer note:',parent=self) or ''
            except tk.TclError: pass
        if decision=='needs_discussion' and not note:
            note='Marked Needs Discussion in translationCore AI Bridge.'
        key=self._qa_issue_key(x)
        try:
            ch=self.chapter_var.get(); vs=self.verse_var.get()
            p=self.project.record_qa_decision(ch,vs,key,decision,note,x.to_dict())
            try: MetricsStore(self.project.companion_dir(),self.project.book_id).event('qa_decision',decision=decision,severity=x.severity,code=x.code,chapter=str(ch),verse=str(vs))
            except Exception: pass
            if note and x.check_id:
                matches=[e for e in self.project.checks_for_verse(ch,vs) if str(e.get('contextId',{}).get('checkId',''))==str(x.check_id)]
                if matches:
                    self.project.sync_comment(ch,vs,matches[0].get('contextId',{}),note,self.settings.reviewer_name,gateway_language_quote=str(matches[0].get('contextId',{}).get('occurrenceNote','')))
            paratext_note=None
            if note:
                paratext_note=self.project.record_paratext_note(ch,vs,note,self.settings.reviewer_name,note_type='AI Bridge QA Discussion',metadata={'decision':decision,'severity':x.severity,'checkId':x.check_id})
            try:
                metric_name='human_accept' if decision=='accepted' else 'human_reject' if decision=='rejected' else 'human_discussion'
                MetricsStore(self.project.companion_dir(),self.project.book_id).event(metric_name,chapter=str(ch),verse=str(vs),source=x.source,code=x.code)
            except Exception: pass
            self.log(f'QA decision {decision}: {key} -> {p}')
            self._refresh_qa_tree(); self._qa_selected(); self._refresh_exception_queue(); self.set_status(f'QA finding: {decision}')
            if self.fast_review_var.get(): self.after(180,self._review_next_priority)
        except Exception as e: messagebox.showerror('QA decision',str(e))

    def _scripture_editor(self, proposed_text: str = '', context_id: dict | None = None):
        if not self.project:return
        ch=self.chapter_var.get(); vs=self.verse_var.get(); current=self.project.target_verse_text(ch,vs)
        win=tk.Toplevel(self); win.title(f'Human Scripture Editor — {self.project.book_id.upper()} {ch}:{vs}'); win.transient(self); win.grab_set(); win.geometry('900x720')
        ttk.Label(win,text='Human-only Scripture edit. AI suggestions are never applied automatically. Saving creates a backup, verseEdit record, alignment invalidation, and stale/recheck propagation.',wraplength=850).pack(anchor='w',padx=12,pady=(12,6))
        panes=ttk.Panedwindow(win,orient='vertical'); panes.pack(fill='both',expand=True,padx=12,pady=6)
        target_name=self.language_context.target_name if self.language_context else 'Target language'
        a=ttk.LabelFrame(panes,text=f'Current {target_name}',padding=5); b=ttk.LabelFrame(panes,text=f'Proposed / edited {target_name}',padding=5); c=ttk.LabelFrame(panes,text='Before / after diff',padding=5)
        panes.add(a,weight=2); panes.add(b,weight=3); panes.add(c,weight=2)
        for pane in (a,b,c): pane.rowconfigure(0,weight=1); pane.columnconfigure(0,weight=1)
        cur=tk.Text(a,wrap='word',font=(self.language_context.target_font if self.language_context else 'Nirmala UI',11),height=6); cy=ttk.Scrollbar(a,orient='vertical',command=cur.yview); cur.configure(yscrollcommand=cy.set); cur.grid(row=0,column=0,sticky='nsew'); cy.grid(row=0,column=1,sticky='ns'); cur.insert('1.0',current); cur.configure(state='disabled')
        edit=tk.Text(b,wrap='word',font=(self.language_context.target_font if self.language_context else 'Nirmala UI',11),height=8); ey=ttk.Scrollbar(b,orient='vertical',command=edit.yview); edit.configure(yscrollcommand=ey.set); edit.grid(row=0,column=0,sticky='nsew'); ey.grid(row=0,column=1,sticky='ns'); edit.insert('1.0',proposed_text.strip() or current)
        diff=tk.Text(c,wrap='none',font=('Consolas',9),height=7); dy=ttk.Scrollbar(c,orient='vertical',command=diff.yview); dx=ttk.Scrollbar(c,orient='horizontal',command=diff.xview); diff.configure(yscrollcommand=dy.set,xscrollcommand=dx.set); diff.grid(row=0,column=0,sticky='nsew'); dy.grid(row=0,column=1,sticky='ns'); dx.grid(row=1,column=0,sticky='ew'); diff.configure(state='disabled')
        def update_diff(*_):
            new=edit.get('1.0','end-1c').strip(); lines=list(difflib.unified_diff(current.splitlines(),new.splitlines(),fromfile='CURRENT',tofile='PROPOSED',lineterm=''))
            self._set_text(diff,'\n'.join(lines) if lines else 'No change.')
        edit.bind('<KeyRelease>',update_diff); update_diff()
        opts=ttk.Frame(win); opts.pack(fill='x',padx=12,pady=(2,4))
        ttk.Label(opts,text='Edit tag:').pack(side='left'); tag=tk.StringVar(value='meaning'); ttk.Combobox(opts,textvariable=tag,state='readonly',values=('meaning','word_choice','grammar','spelling','punctuation','sandhi','other'),width=18).pack(side='left',padx=6)
        row=ttk.Frame(win); row.pack(fill='x',padx=12,pady=(4,12))
        def apply():
            new=edit.get('1.0','end-1c').strip()
            if new==current:
                messagebox.showinfo('Scripture edit','No change detected.',parent=win); return
            if not messagebox.askyesno('Apply human Scripture edit',f'Apply this human-edited {self.language_context.target_name if self.language_context else "target-language"} verse?\n\nDependent Alignment, TN/TW, AI review and final approval will require rechecking.',parent=win): return
            try:
                result=self.project.apply_scripture_edit(ch,vs,new,self.settings.reviewer_name,[tag.get()],context_id=context_id)
                self.scripture_undo_stack.append((current,new)); self.scripture_redo_stack.clear(); self.log(f'Scripture edit {self.project.book_id} {ch}:{vs}: {result}')
                try: MetricsStore(self.project.companion_dir(),self.project.book_id).event('human_edit',chapter=str(ch),verse=str(vs),tag=tag.get())
                except Exception: pass
                win.destroy(); self._clear_transient_ai_panels(keep_summary=False); self._load_verse(); self._run_local_qa(); self._refresh_tc_checks(); self._refresh_exception_queue(); self.set_status('Scripture edited by human — dependent checks marked for recheck')
            except Exception as e: messagebox.showerror('Scripture edit blocked',str(e),parent=win)
        ttk.Button(row,text='Apply Human Edit',command=apply,style='Accent.TButton').pack(side='left')
        ttk.Button(row,text='Cancel',command=win.destroy).pack(side='right')

    def _edit_scripture_from_review(self):
        sel=self.review_tree.selection(); proposed=''; ctx=None
        if sel:
            r=self.ai_check_reviews[int(sel[0])]; proposed=r.suggested_correction
            if self.project:
                for e in self.project.checks_for_verse(self.chapter_var.get(),self.verse_var.get()):
                    c=e.get('contextId',{})
                    if str(c.get('checkId',''))==r.check_id: ctx=copy.deepcopy(c); break
        self._scripture_editor(proposed,ctx)

    def _edit_scripture_from_qa(self):
        self._scripture_editor('')

    def _undo_scripture(self):
        if not self.project or not self.scripture_undo_stack:
            self.set_status('No Scripture edit to undo'); return
        old,new=self.scripture_undo_stack.pop(); current=self.project.target_verse_text(self.chapter_var.get(),self.verse_var.get())
        if current!=new:
            self.scripture_undo_stack.append((old,new)); messagebox.showwarning('Undo Scripture','Current verse no longer matches the last edit; undo is blocked to avoid overwriting another change.'); return
        try:
            self.project.apply_scripture_edit(self.chapter_var.get(),self.verse_var.get(),old,self.settings.reviewer_name,['undo'])
            self.scripture_redo_stack.append((old,new)); self._clear_transient_ai_panels(keep_summary=False); self._load_verse(); self._run_local_qa(); self.set_status('Scripture edit undone — recheck still required')
        except Exception as e: self.scripture_undo_stack.append((old,new)); messagebox.showerror('Undo Scripture',str(e))

    def _redo_scripture(self):
        if not self.project or not self.scripture_redo_stack:
            self.set_status('No Scripture edit to redo'); return
        old,new=self.scripture_redo_stack.pop(); current=self.project.target_verse_text(self.chapter_var.get(),self.verse_var.get())
        if current!=old:
            self.scripture_redo_stack.append((old,new)); messagebox.showwarning('Redo Scripture','Current verse no longer matches the undo state; redo is blocked.'); return
        try:
            self.project.apply_scripture_edit(self.chapter_var.get(),self.verse_var.get(),new,self.settings.reviewer_name,['redo'])
            self.scripture_undo_stack.append((old,new)); self._clear_transient_ai_panels(keep_summary=False); self._load_verse(); self._run_local_qa(); self.set_status('Scripture edit redone — recheck required')
        except Exception as e: self.scripture_redo_stack.append((old,new)); messagebox.showerror('Redo Scripture',str(e))

    def _run_ai_qa(self):
        if not self.project or not self.session:return
        try: client=self._get_client()
        except Exception as e: messagebox.showerror('API configuration',str(e)); return
        ch=self.chapter_var.get();vs=self.verse_var.get(); current=copy.deepcopy(self.session.current)
        def success(result):
            issues,summary=result; self.ai_issues=issues; self._run_local_qa(); self.qa_summary_var.set(summary+' — '+self.qa_summary_var.get()); self._update_ai_usage(client); self.notebook.select(self.qa_tab); self.log(f'AI QA {self.project.book_id} {ch}:{vs}: {len(issues)} issues')
        self._background('Running AI quality review',lambda:client.run_quality_review(self.project,ch,vs,current),success,ai_operation=True)

    def _refresh_tc_checks(self):
        if not self.project:return
        entries=self.project.checks_for_verse(self.chapter_var.get(),self.verse_var.get()); self._tc_entries=entries; self.tc_tree.delete(*self.tc_tree.get_children())
        for i,e in enumerate(entries):
            c=e.get('contextId',{}); sel=e.get('selections',False); nothing=e.get('nothingToSelect',False); invalid=e.get('invalidated',False)
            stale=self.project.check_staleness(self.chapter_var.get(),self.verse_var.get(),str(c.get('checkId','')))=='stale'
            status='invalidated' if invalid else ('stale' if stale else ('nothing' if nothing else ('selected' if isinstance(sel,list) else 'pending')))
            if isinstance(sel,list): st=' '.join(str(x.get('text','')) for x in sel)
            else: st=''
            self.tc_tree.insert('', 'end',iid=str(i),values=(c.get('tool',''),c.get('groupId',''),c.get('checkId',''),status,st))
        states=self.project.check_state_for_verse(self.chapter_var.get(),self.verse_var.get()); self.tc_summary_var.set(f'{len(entries)} indexed checks | comments {len(states["comments"])} | invalidated records {len(states["invalidated"])} | verse edits {len(states["verseEdits"])}')

    def _tc_selected(self,event=None):
        sel=self.tc_tree.selection()
        if not sel:return
        e=self._tc_entries[int(sel[0])]; c=e.get('contextId',{})
        text=f'{c.get("tool","")} / {c.get("groupId","")} / {c.get("checkId","")}\n\nSource quote: {c.get("quoteString","")}\n\nNote:\n{c.get("occurrenceNote","")}\n\nExisting selection:\n{json.dumps(e.get("selections"),ensure_ascii=False,indent=2)}'
        self._set_text(self.tc_detail,text)

    def _refresh_kb(self):
        if not hasattr(self,'kb_tree') or not self.project:
            return
        self.kb_tree.delete(*self.kb_tree.get_children())
        if not self.kb:
            self._set_text(self.kb_detail,'Knowledge Base unavailable for this project.')
            return
        try:
            inv=self.kb.inventory()
            for name,ref in inv.get('resources',{}).items():
                if 'error' in ref:
                    self.kb_tree.insert('', 'end', values=(name,'ERROR','','',ref['error']))
                else:
                    self.kb_tree.insert('', 'end', values=(name,ref.get('version',''),ref.get('provider',''),'yes' if ref.get('project_pinned') else 'fallback',ref.get('reason','')))
            pack=self.kb.evidence_pack_for_verse(self.chapter_var.get(),self.verse_var.get(),max_chars=18000)
            lines=[]
            if pack.get('global_checking_evidence'):
                lines.append('GLOBAL CHECKING METHOD (Translation Academy)')
                lines.append(', '.join(str(x.get('identifier','')) for x in pack.get('global_checking_evidence',[])))
                lines.append('')
            for c in pack.get('checks',[]):
                lines.append(f"{c.get('tool')} · {c.get('groupId')} · {c.get('checkId')}\nSource: {c.get('source_quote','')}")
                for ev in c.get('evidence',[]):
                    lines.append(f"  [{ev.get('kind')}] {ev.get('title')}\n  {str(ev.get('content',''))[:1200].replace(chr(10), chr(10)+'  ')}")
                lines.append('')
            for rb in pack.get('reference_bibles',[]):
                lines.append(f"[Secondary reference] {rb.get('title')}\n{rb.get('content','')}\n")
            self._set_text(self.kb_detail,'\n'.join(lines) if lines else 'No Translation Notes/Words evidence is indexed for this verse. Alignment and whole-verse QA can still run.')
        except Exception as e:
            self._set_text(self.kb_detail,f'Knowledge Base error: {e}')

    def _load_saved_review(self):
        if not self.project:return
        saved=self.project.load_ai_review_result(self.chapter_var.get(),self.verse_var.get())
        if not saved:
            self.ai_check_reviews=[]; self.review_alignment_for_checks=copy.deepcopy(self.session.current) if self.session else None; self._refresh_review_tree()
            return
        try:
            reviews=[]
            for d in saved.get('checkReviews',[]) if isinstance(saved.get('checkReviews'),list) else []:
                if not isinstance(d,dict): continue
                reviews.append(AICheckReview(
                    tool=str(d.get('tool','')),group_id=str(d.get('group_id','')),check_id=str(d.get('check_id','')),
                    source_quote=str(d.get('source_quote','')),proposed_selection_ids=list(d.get('proposed_selection_ids') or []),
                    proposed_selection_text=list(d.get('proposed_selection_text') or []),nothing_to_select=bool(d.get('nothing_to_select',False)),
                    verdict=str(d.get('verdict','review')),severity=d.get('severity','medium'),rationale=str(d.get('rationale','')),
                    suggested_correction=str(d.get('suggested_correction','')),confidence=float(d.get('confidence',0) or 0),
                    evidence_used=list(d.get('evidence_used') or [])))
            self.ai_check_reviews=reviews
            reviewed_alignment = saved.get('reviewedAlignment')
            if isinstance(reviewed_alignment, dict):
                try:
                    self.review_alignment_for_checks = VerseAlignment.from_dict(reviewed_alignment)
                except Exception:
                    self.review_alignment_for_checks = copy.deepcopy(self.session.current) if self.session else None
            else:
                self.review_alignment_for_checks = copy.deepcopy(self.session.current) if self.session else None
            self._refresh_review_tree()
            loaded_issues=[]
            for d in saved.get('qaIssues',[]) if isinstance(saved.get('qaIssues'),list) else []:
                if not isinstance(d,dict):continue
                loaded_issues.append(QAIssue(code=str(d.get('code','AI_SAVED')),severity=d.get('severity','medium'),title=str(d.get('title','AI review item')),detail=str(d.get('detail','')),source=str(d.get('source','OpenAI+KnowledgeBase')),check_id=str(d.get('check_id','')),group_id=str(d.get('group_id','')),confidence=d.get('confidence')))
            if loaded_issues:self.ai_issues=loaded_issues
            cache=self.project.ai_review_cache_status(self.chapter_var.get(),self.verse_var.get())
            marker='CURRENT' if cache=='current' else 'STALE — rerun recommended'
            self.review_summary_var.set(f'Saved AI review [{marker}]: '+str(saved.get('summary','')))
            self.review_meta={'cache_status':cache,'model':saved.get('model',''),'generatedTimestamp':saved.get('generatedTimestamp',''),'privacy_manifest':saved.get('privacyManifest',{}),'resource_provenance':saved.get('resourceProvenance',{}),'estimated_cost_usd':saved.get('estimatedCostUSD',0)}
        except Exception as e:
            self.log(f'Could not load saved AI review: {e}')

    def _refresh_review_tree(self):
        if not hasattr(self,'review_tree'):return
        self.review_tree.delete(*self.review_tree.get_children())
        counts={k:0 for k in ('critical','high','medium','editorial','info')}
        for i,r in enumerate(self.ai_check_reviews):
            selection=' '.join(r.proposed_selection_text) if r.proposed_selection_text else ('Nothing to select' if r.nothing_to_select else '—')
            sev=str(r.severity).lower(); counts[sev]=counts.get(sev,0)+1
            self.review_tree.insert('', 'end', iid=str(i), values=(sev.upper(),r.tool,r.group_id,r.verdict.upper(),selection,f'{r.confidence:.0%}'))
        for issue in self.ai_issues:
            sev=str(issue.severity).lower(); counts[sev]=counts.get(sev,0)+1
        if hasattr(self,'review_severity_vars'):
            for k,label in [('critical','Critical'),('high','High'),('medium','Medium'),('editorial','Editorial'),('info','Info')]: self.review_severity_vars[k].set(f'{label}: {counts.get(k,0)}')
        self._resize_tree_columns()

    def _review_selected(self,event=None):
        sel=self.review_tree.selection()
        if not sel:return
        r=self.ai_check_reviews[int(sel[0])]
        lines=[f'{r.tool} / {r.group_id} / {r.check_id}',f'Source quote: {r.source_quote}',f'AI target selection: {" ".join(r.proposed_selection_text) if r.proposed_selection_text else "Nothing to select" if r.nothing_to_select else "No target expression located"}',f'Verdict: {r.verdict.upper()} · {r.severity.upper()} · confidence {r.confidence:.0%}','',r.rationale]
        if r.suggested_correction:
            lines += ['', 'Suggested correction (review only):', r.suggested_correction]
        if r.evidence_used:
            lines += ['', 'EVIDENCE USED']
            for n,ev in enumerate(r.evidence_used,1):
                lines += ['',f'{n}. {ev.get("title","Evidence")}',f'Kind: {ev.get("kind","")} | Version: {ev.get("version","")} {ev.get("provider","")}',str(ev.get('content',''))]
        self._set_text(self.review_detail,'\n'.join(lines))

    def _edit_review_selection(self):
        if not self.session:return
        sel=self.review_tree.selection()
        if not sel:
            messagebox.showinfo('Edit selection','Select a Translation Note/Word result first.'); return
        idx=int(sel[0]); r=self.ai_check_reviews[idx]; inv=make_inventory(self.session.current)
        ordered=list(inv.bottom_ids.items())
        win=tk.Toplevel(self); win.title(f'Edit {self.language_context.target_name if self.language_context else "Target"} Selection — {r.check_id}'); win.transient(self); win.grab_set(); win.geometry('620x520')
        ttk.Label(win,text=f'Select the existing {self.language_context.target_name if self.language_context else "target-language"} bottomWords that represent this check. No text can be invented here.',wraplength=580).pack(anchor='w',padx=12,pady=(12,6))
        lbf=ttk.Frame(win); lbf.pack(fill='both',expand=True,padx=12,pady=6); lbf.rowconfigure(0,weight=1); lbf.columnconfigure(0,weight=1)
        lb=tk.Listbox(lbf,selectmode='extended',exportselection=False,font=(self.language_context.target_font if self.language_context else 'Nirmala UI',11)); lby=ttk.Scrollbar(lbf,orient='vertical',command=lb.yview); lbx=ttk.Scrollbar(lbf,orient='horizontal',command=lb.xview); lb.configure(yscrollcommand=lby.set,xscrollcommand=lbx.set); lb.grid(row=0,column=0,sticky='nsew'); lby.grid(row=0,column=1,sticky='ns'); lbx.grid(row=1,column=0,sticky='ew')
        id_to_index={}
        for i,(tid,tok) in enumerate(ordered):
            id_to_index[tid]=i; lb.insert('end',f'{tid}   {tok.word}   occurrence {tok.occurrence}/{tok.occurrences}')
        # AI selection IDs may have been generated against an AI-prepared alignment whose
        # inventory ordering differs from session.current. Resolve those IDs to token signatures
        # first, then preselect the equivalent current Tamil tokens.
        source_inv=make_inventory(self.review_alignment_for_checks or self.session.current)
        for tid in r.proposed_selection_ids:
            source_tok=source_inv.bottom_ids.get(tid)
            if not source_tok:
                continue
            current_tid=inv.bottom_sig_to_id.get(source_tok.signature)
            if current_tid in id_to_index:
                lb.selection_set(id_to_index[current_tid])
        row=ttk.Frame(win); row.pack(fill='x',padx=12,pady=(4,12))
        def use_selected():
            ids=[ordered[i][0] for i in lb.curselection()]
            if not ids:
                messagebox.showinfo('Edit selection',f'Select one or more {self.language_context.target_name if self.language_context else "target-language"} tokens, or choose Nothing to Select.',parent=win); return
            r.proposed_selection_ids=ids; r.proposed_selection_text=[inv.bottom_ids[x].word for x in ids]; r.nothing_to_select=False
            r._human_selection_records=[{'text':inv.bottom_ids[x].word,'occurrence':inv.bottom_ids[x].occurrence,'occurrences':inv.bottom_ids[x].occurrences} for x in ids]
            r.rationale=(r.rationale+'\n\nHuman edited target selection before final decision.').strip(); self._refresh_review_tree(); self.review_tree.selection_set(str(idx)); self._review_selected(); win.destroy(); self.set_status(f'Human-edited {self.language_context.target_name if self.language_context else "target-language"} selection prepared — Accept to make it authoritative')
        def nothing():
            r.proposed_selection_ids=[]; r.proposed_selection_text=[]; r.nothing_to_select=True
            r._human_selection_records=[]
            r.rationale=(r.rationale+'\n\nHuman marked Nothing to Select before final decision.').strip(); self._refresh_review_tree(); self.review_tree.selection_set(str(idx)); self._review_selected(); win.destroy(); self.set_status('Nothing to Select prepared — Accept to make it authoritative')
        ttk.Button(row,text='Use Selected',command=use_selected,style='Accent.TButton').pack(side='left')
        ttk.Button(row,text='Nothing to Select',command=nothing).pack(side='left',padx=6)
        ttk.Button(row,text='Cancel',command=win.destroy).pack(side='right')

    def _selection_records_for_review(self, r: AICheckReview) -> list[dict]:
        """Resolve a TN/TW review selection to exact current Tamil token records.

        AI token IDs are scoped to the alignment inventory used during that AI review.
        Resolve through token signatures so group reordering cannot cause a different Tamil
        word to be synchronized into translationCore checkData.
        """
        if not self.session:
            raise ProjectError('Verse alignment/token inventory is not loaded.')
        human_records=getattr(r,'_human_selection_records',None)
        if human_records is not None:
            records=[dict(x) for x in human_records]
            current_inv=make_inventory(self.session.current)
            current_sigs=set(current_inv.bottom_sig_to_id)
            for rec in records:
                sig=f"{rec.get('text','')}\u241f{int(rec.get('occurrence',1) or 1)}\u241f{int(rec.get('occurrences',1) or 1)}"
                if sig not in current_sigs:
                    raise ProjectError(f"Tamil token {rec.get('text','')!r} changed after the human selection. Rerun/review before syncing.")
            return records
        source_inv=make_inventory(self.review_alignment_for_checks or self.session.current)
        current_inv=make_inventory(self.session.current)
        records=[]
        for tid in r.proposed_selection_ids:
            if tid not in source_inv.bottom_ids:
                raise ProjectError(f'Accepted selection references unknown Tamil token {tid}. Reload/review before syncing.')
            tok=source_inv.bottom_ids[tid]
            if tok.signature not in current_inv.bottom_sig_to_id:
                raise ProjectError(f'Tamil token {tok.word!r} changed after AI preparation. Rerun/review before syncing.')
            records.append({'text':tok.word,'occurrence':tok.occurrence,'occurrences':tok.occurrences})
        return records

    def _record_review_decision(self,decision):
        if not self.project:return
        sel=self.review_tree.selection()
        if not sel:
            messagebox.showinfo('Final review','Select a check result first.'); return
        note=''
        if decision in ('needs_discussion','rejected'):
            try:
                if self.state() != 'withdrawn': note=simpledialog.askstring('Reviewer note','Optional reason / discussion note:',parent=self) or ''
            except tk.TclError: pass
        if decision=='needs_discussion' and not note:
            note='Marked Needs Discussion in translationCore AI Bridge.'
        self._begin_job(f'Recording {decision}',determinate=True); self._job_progress(25,'Recording human review decision…')
        r=self.ai_check_reviews[int(sel[0])]; ch=self.chapter_var.get(); vs=self.verse_var.get()
        try:
            sync_result=None
            if decision=='accepted' and r.tool in ('translationNotes','translationWords'):
                if not self.session: raise ProjectError('Verse alignment/token inventory is not loaded.')
                selections=self._selection_records_for_review(r)
                if not selections and not r.nothing_to_select:
                    raise ProjectError('Accepted TN/TW check must contain a target selection or explicitly be Nothing to Select.')
                self._job_progress(50,'Synchronizing approved TN/TW result to translationCore checkData…')
                sync_result=self.project.sync_check_approval(ch,vs,r.tool,r.group_id,r.check_id,selections,r.nothing_to_select,self.settings.reviewer_name)
                self.project.rebase_ai_review_fingerprint(ch,vs)
            native_comment=None
            if note and r.tool in ('translationNotes','translationWords'):
                matches=[e for e in self.project.checks_for_verse(ch,vs) if str(e.get('contextId',{}).get('checkId',''))==str(r.check_id)]
                if matches:
                    native_comment=self.project.sync_comment(ch,vs,matches[0].get('contextId',{}),note,self.settings.reviewer_name,gateway_language_quote=str(matches[0].get('contextId',{}).get('occurrenceNote','')))
            paratext_note=None
            if note:
                paratext_note=self.project.record_paratext_note(ch,vs,note,self.settings.reviewer_name,selected_text=' '.join(r.proposed_selection_text),note_type=f'AI Bridge {r.tool} Discussion',metadata={'decision':decision,'tool':r.tool,'checkId':r.check_id,'model':str(self.review_meta.get('model') or self.settings.model)})
            p=self.project.record_human_decision(ch,vs,r.check_id,decision,note=note,selection_text=r.proposed_selection_text,selection_ids=r.proposed_selection_ids,tool=r.tool,group_id=r.group_id,model=str(self.review_meta.get('model') or self.settings.model),evidence=r.evidence_used)
            try:
                metric_name='human_accept' if decision=='accepted' else 'human_reject' if decision=='rejected' else 'human_discussion'
                MetricsStore(self.project.companion_dir(),self.project.book_id).event(metric_name,chapter=str(ch),verse=str(vs),tool=r.tool,check_id=r.check_id)
            except Exception: pass
            self.log(f'Human decision {decision}: {r.check_id} -> {p}' + (f'; tC sync: {sync_result}' if sync_result else '') + (f'; tC comment: {native_comment}' if native_comment else '') + (f'; Paratext note: {paratext_note}' if paratext_note else ''))
            self._refresh_tc_checks(); self._run_local_qa(); self._refresh_exception_queue()
            self._clear_transient_ai_panels(keep_summary=True)
            suffix=' · synchronized to translationCore checkData' if sync_result else ''
            self.review_summary_var.set(f'{r.check_id}: {decision}{suffix}. Select another result or run the next review.')
            self._job_progress(100,f'{r.check_id}: {decision}')
            self._end_job(f'{r.check_id}: {decision}{suffix}')
            if self.fast_review_var.get(): self.after(180,self._review_next_priority)
        except Exception as e:
            self._end_job('Could not record review decision'); messagebox.showerror('Final review',str(e))

    def _run_book_review(self):
        if not self.project:return
        refs=[(ch,vs) for ch in self.project.chapters() for vs in self.project.verses(ch) if vs!='front']
        if not refs:return
        prompt = (f'Prepare changed/untouched work across the whole book ({len(refs):,} verses)?\n\n'
                  'Current cached reviews will be skipped. This can take substantial API time; '
                  'you can cancel after the current request.')
        if not messagebox.askyesno('Book AI preparation', prompt):
            return
        if not self.kb:
            try:self.kb=TranslationHelpsKnowledgeBase(self.project)
            except Exception as e:messagebox.showerror('Knowledge Base',str(e));return
        try: client=self._get_client()
        except Exception as e:messagebox.showerror('API configuration',str(e));return
        project=self.project; kb=self.kb; total=len(refs); self._cancel_event.clear(); self.cancel_batch_btn.configure(state='normal')
        def work():
            done=[]; tokens=0; cost=0.0; failed=[]; skipped=0
            for n,(ch,vs) in enumerate(refs,1):
                if self._cancel_event.is_set(): break
                if project.ai_review_cache_status(ch,vs)=='current':
                    skipped+=1; self._job_progress(n/total*100,f'Book: skipped unchanged {ch}:{vs} ({n}/{total})'); continue
                try:
                    a=project.load_verse_alignment(ch,vs)
                    def prog(pct,msg,n=n,ch=ch,vs=vs): self._job_progress(((n-1)+pct/100)/total*100,f'{ch}:{vs} · {msg} ({n}/{total})')
                    proposal,reviewed,reviews,issues,summary,meta=client.prepare_verse_review(project,ch,vs,a,kb,progress_callback=prog)
                    tokens+=int(meta.get('total_tokens_for_prepare',client.last_usage.total_tokens)); cost+=float(meta.get('estimated_cost_usd',getattr(client,'last_cost_usd',0.0)) or 0.0); done.append((ch,vs,len(reviews),len(issues)))
                except Exception as e:
                    failed.append((ch,vs,str(e))); self._ui_queue.put(('log',f'Book batch {ch}:{vs} failed: {e}'))
            return {'reviewed':done,'failed':failed,'skipped':skipped,'tokens':tokens,'cost':cost,'cancelled':self._cancel_event.is_set()}
        def success(r):
            self.cancel_batch_btn.configure(state='disabled'); self.usage_var.set(f"Tokens {r['tokens']:,}"); self.cost_var.set(f"Cost ${r.get('cost',0.0):.4f}"); self._refresh_exception_queue(); self._refresh_dashboard_background(); self.notebook.select(self.dashboard_tab)
            self.review_summary_var.set(f"Book preparation: {len(r['reviewed'])} reviewed · {r['skipped']} unchanged skipped · {len(r['failed'])} failed"+(' · CANCELLED' if r['cancelled'] else ''))
            try: MetricsStore(self.project.companion_dir(),self.project.book_id).event('ai_prepared_batch',checks=sum(x[2] for x in r['reviewed']),issues=sum(x[3] for x in r['reviewed']),skipped=r['skipped'],scope='book',verses=len(r['reviewed']))
            except Exception: pass
            self._end_job('Book AI preparation complete')
        self._background('Preparing changed book',work,success,determinate=True,ai_operation=True)

    def _run_chapter_review(self, force=False):
        if not self.project:return
        ch=self.chapter_var.get(); verses=[v for v in self.project.verses(ch) if v!='front']
        if not verses:return
        mode='FULL AUDIT' if force else 'CHANGED / UNTOUCHED ONLY'
        if not messagebox.askyesno('Batch AI review',f'Run {mode} for chapter {ch} ({len(verses)} verses)?\n\nCurrent cached reviews are skipped unless Full Audit is selected. AI preparation results are saved under .apps/translationCoreAI/aiReview. Batch preparation itself does not write Scripture or mark tC checks complete; only later explicit human approval actions can do that.'):
            self.set_status('Batch review cancelled'); return
        if not self.kb:
            try:self.kb=TranslationHelpsKnowledgeBase(self.project)
            except Exception as e:messagebox.showerror('Knowledge Base',str(e));return
        try:client=self._get_client()
        except Exception as e:messagebox.showerror('API configuration',str(e));return
        project=self.project; kb=self.kb; total_verses=len(verses); self._cancel_event.clear(); self.cancel_batch_btn.configure(state='normal')
        def work():
            done=[]; total_tokens=0; total_cost=0.0
            for n,vs in enumerate(verses,1):
                if self._cancel_event.is_set():
                    done.append({'verse':vs,'checks':0,'issues':0,'summary':'cancelled','alignmentProposed':False,'error':'CANCELLED','skipped':False}); break
                cache=project.ai_review_cache_status(ch,vs)
                if not force and cache=='current':
                    done.append({'verse':vs,'checks':0,'issues':0,'summary':'cached current review','alignmentProposed':False,'error':'','skipped':True})
                    self._job_progress((n/total_verses)*100,f'Chapter {ch}: skipped unchanged verse {vs} ({n}/{total_verses})')
                    continue
                base=(n-1)/total_verses*100
                self._job_progress(base,f'Chapter {ch}: preparing verse {vs} ({n}/{total_verses})')
                try:
                    a=project.load_verse_alignment(ch,vs)
                    def verse_progress(pct,msg, n=n, vs=vs):
                        overall=((n-1)+(pct/100))/total_verses*100
                        self._job_progress(overall,f'Chapter {ch} verse {vs}: {msg} ({n}/{total_verses})')
                    proposal,reviewed,reviews,issues,summary,meta=client.prepare_verse_review(project,ch,vs,a,kb,progress_callback=verse_progress)
                    total_tokens += int(meta.get('total_tokens_for_prepare',client.last_usage.total_tokens)); total_cost += float(meta.get('estimated_cost_usd',getattr(client,'last_cost_usd',0.0)) or 0.0)
                    done.append({'verse':vs,'checks':len(reviews),'issues':len(issues),'summary':summary,'alignmentProposed':proposal is not None,'error':'','skipped':False})
                except Exception as e:
                    done.append({'verse':vs,'checks':0,'issues':0,'summary':'','alignmentProposed':False,'error':str(e),'skipped':False})
                    self._ui_queue.put(('log',f'Batch verse {ch}:{vs} failed: {e}'))
            self._job_progress(100,f'Chapter {ch}: batch review complete')
            return done,total_tokens,total_cost
        def success(result):
            done,total,total_cost=result; self.cancel_batch_btn.configure(state='disabled'); self.usage_var.set(f'Tokens {total:,}'); self.cost_var.set(f'Cost ${total_cost:.4f}')
            problems=sum(x['issues'] for x in done); checks=sum(x['checks'] for x in done); failed=[x['verse'] for x in done if x.get('error') and x.get('error')!='CANCELLED']; skipped=[x['verse'] for x in done if x.get('skipped')]; cancelled=any(x.get('error')=='CANCELLED' for x in done)
            try: MetricsStore(self.project.companion_dir(),self.project.book_id).event('ai_prepared_batch',checks=checks,issues=problems,skipped=len(skipped),scope='chapter',chapter=str(ch),verses=len(done))
            except Exception: pass
            failure_text=f' · {len(failed)} failed: {", ".join(failed[:12])}' if failed else ''
            suffix=(f' · {len(skipped)} unchanged skipped' if skipped else '') + (' · CANCELLED' if cancelled else '')
            batch_summary=f'Chapter {ch} batch complete: {len(done)-len(failed)-len(skipped)}/{len(done)} newly reviewed · {checks} tC checks · {problems} QA issues{failure_text}{suffix}. Navigate verses to review evidence.'
            self.log(batch_summary)
            # Refresh the current verse evidence first: _load_saved_review() sets a per-verse
            # summary, so the batch result must be restored afterwards and remain visible.
            self._load_saved_review(); self._refresh_exception_queue(); self.notebook.select(self.review_tab)
            self.review_summary_var.set(batch_summary)
            self._end_job(f'Chapter {ch} AI review complete' + (f' · {len(failed)} failed' if failed else ''))
        self._background(f'Batch reviewing chapter {ch}',work,success,determinate=True,ai_operation=True)

    def _run_full_review(self):
        if not self.project or not self.session:
            self.set_status('Load a project and verse first'); return
        if not self.kb:
            try:self.kb=TranslationHelpsKnowledgeBase(self.project)
            except Exception as e:messagebox.showerror('Knowledge Base',str(e));return
        try: client=self._get_client()
        except Exception as e: messagebox.showerror('API configuration',str(e)); return
        ch=self.chapter_var.get();vs=self.verse_var.get();current=copy.deepcopy(self.session.current); kb=self.kb
        # New run always clears stale prepared/evidence panels first.
        self._clear_transient_ai_panels(keep_summary=False)
        def progress(pct,msg): self._job_progress(pct,f'{self.project.book_id.upper()} {ch}:{vs} · {msg}')
        def success(result):
            proposal,reviewed_alignment,reviews,issues,summary,meta=result
            self.review_alignment_for_checks=copy.deepcopy(reviewed_alignment)
            self.ai_check_reviews=reviews; self.ai_issues=issues; self.review_meta=meta
            if proposal is not None:
                self.pending_ai_proposal=proposal; self.apply_ai_btn.configure(state='normal')
                try:
                    validate_proposal(current,proposal)
                    self._render_ai_proposal(current,proposal,'AI alignment prepared automatically for final review (NOT SAVED).')
                except Exception as e:self.log(f'Could not render prepared alignment: {e}')
            self._refresh_review_tree(); self._run_local_qa(); self.review_summary_var.set(summary or f'{len(reviews)} tC checks reviewed; {len(issues)} QA issues')
            if proposal is not None:self.review_summary_var.set('AI alignment prepared (not saved) · '+self.review_summary_var.get())
            self._update_ai_usage(client,total_override=meta.get('total_tokens_for_prepare'),cost_override=meta.get('estimated_cost_usd'))
            try: MetricsStore(self.project.companion_dir(),self.project.book_id).event('ai_prepared_verse',checks=len(reviews),issues=len(issues),chapter=str(ch),verse=str(vs))
            except Exception: pass
            self.notebook.select(self.review_tab)
            self.log(f'AI full preparation {self.project.book_id} {ch}:{vs}: alignment={proposal is not None}; {len(reviews)} tC checks, {len(issues)} QA issues; {meta.get("saved_to","")}')
            self._refresh_exception_queue()
            self._end_job(f'AI Full Verse Review complete · {len(reviews)} checks · {len(issues)} QA issues')
        self._background('AI Full Verse Review started',lambda:client.prepare_verse_review(self.project,ch,vs,current,kb,progress_callback=progress),success,determinate=True,ai_operation=True)


    def _show_suppressed_findings(self):
        """Show AI findings hidden from the priority queue by the false-positive gate."""
        saved={}
        if self.project:
            try: saved=self.project.load_ai_review_result(self.chapter_var.get(),self.verse_var.get()) or {}
            except Exception: saved={}
        items=list(saved.get('suppressedQaIssues',[]) or [])
        win=tk.Toplevel(self); win.title('Low-confidence / duplicate AI findings audit'); win.geometry('900x620')
        outer=ttk.Frame(win,padding=8); outer.pack(fill='both',expand=True); outer.rowconfigure(1,weight=1); outer.columnconfigure(0,weight=1)
        ttk.Label(outer,text=f'{len(items)} finding(s) were removed from the main reviewer queue because they were low-confidence, duplicate, or lacked sufficient evidence. They remain visible here for audit.',wraplength=850).grid(row=0,column=0,sticky='ew',pady=(0,6))
        holder=ttk.Frame(outer); holder.grid(row=1,column=0,sticky='nsew'); holder.rowconfigure(0,weight=1); holder.columnconfigure(0,weight=1)
        t=tk.Text(holder,wrap='none',font=('Consolas',9)); sy=ttk.Scrollbar(holder,orient='vertical',command=t.yview); sx=ttk.Scrollbar(holder,orient='horizontal',command=t.xview); t.configure(yscrollcommand=sy.set,xscrollcommand=sx.set); t.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew')
        if items:
            t.insert('1.0',json.dumps(items,ensure_ascii=False,indent=2))
        else:
            t.insert('1.0','No suppressed AI findings are recorded for the current verse.')
        t.configure(state='disabled')

    def _show_privacy_manifest(self):
        manifest=self.review_meta.get('privacy_manifest',{}) if isinstance(self.review_meta,dict) else {}
        if not manifest and self.project:
            saved=self.project.load_ai_review_result(self.chapter_var.get(),self.verse_var.get()) or {}; manifest=saved.get('privacyManifest',{})
        text=json.dumps(manifest or {'message':'No AI request manifest is available for the current verse yet.'},ensure_ascii=False,indent=2)
        win=tk.Toplevel(self); win.title('AI request privacy manifest'); win.geometry('760x540'); h=ttk.Frame(win,padding=8); h.pack(fill='both',expand=True); h.rowconfigure(0,weight=1); h.columnconfigure(0,weight=1); t=tk.Text(h,wrap='none',font=('Consolas',9)); py=ttk.Scrollbar(h,orient='vertical',command=t.yview); px=ttk.Scrollbar(h,orient='horizontal',command=t.xview); t.configure(yscrollcommand=py.set,xscrollcommand=px.set); t.grid(row=0,column=0,sticky='nsew'); py.grid(row=0,column=1,sticky='ns'); px.grid(row=1,column=0,sticky='ew'); t.insert('1.0',text); t.configure(state='disabled')

    def _save_settings(self,silent=False):
        try:
            self.settings.model=self.model_var.get(); self.settings.reviewer_name=self.reviewer_name_var.get(); self.settings.set_api_key(self.api_key_var.get(),self.persist_key_var.get())
            self.settings.set_setting('routing_profile',self.routing_profile_var.get())
            try: float(self.cost_warning_var.get())
            except Exception: raise ValueError('Session cost warning must be a number.')
            self.settings.set_setting('cost_warning_usd',self.cost_warning_var.get())
            self._set_api_indicator('unknown','API settings saved · not tested')
            if not silent: messagebox.showinfo('Settings','Settings saved. Remembered API keys use Windows DPAPI on Windows. Smart routing selects Luna/Terra/Sol by task unless Fixed is selected.')
        except Exception as e:
            if silent: raise
            messagebox.showerror('Settings',str(e))

    def _release_tk_python_refs(self):
        """Release Python wrappers around Tcl variables/images while Tcl is alive.

        Tk widgets are destroyed by Tcl, but Python Variable/Image wrappers can otherwise
        survive in nested containers and be finalized later (occasionally on a worker
        thread during test/process shutdown). That produces noisy RuntimeError messages
        and, on Windows, can escalate to Tcl_AsyncDelete.
        """
        image_names=set()

        def purge(value, seen):
            oid=id(value)
            if oid in seen:
                return value
            # Tcl-backed wrappers are the only values we actively remove.
            if isinstance(value, tk.Variable):
                return None
            if isinstance(value, tk.Image):
                try:
                    name=str(value)
                    if name and name not in image_names:
                        self.tk.call('image','delete',name); image_names.add(name)
                except (tk.TclError, RuntimeError, AttributeError):
                    pass
                return None
            if isinstance(value, dict):
                seen.add(oid)
                for key in list(value):
                    child=value.get(key)
                    cleaned=purge(child,seen)
                    if cleaned is None and isinstance(child,(tk.Variable,tk.Image)):
                        value.pop(key,None)
                    else:
                        value[key]=cleaned
                return value
            if isinstance(value, list):
                seen.add(oid)
                for i,child in enumerate(list(value)):
                    value[i]=purge(child,seen)
                return value
            if isinstance(value, set):
                seen.add(oid)
                cleaned={purge(x,seen) for x in value}
                value.clear(); value.update(x for x in cleaned if x is not None)
                return value
            if isinstance(value, tuple):
                seen.add(oid)
                return tuple(purge(x,seen) for x in value)
            return value

        seen=set()
        for name,value in list(self.__dict__.items()):
            if isinstance(value,(tk.Variable,tk.Image)):
                try:setattr(self,name,purge(value,seen))
                except Exception:pass
            elif isinstance(value,(dict,list,set,tuple)):
                try:setattr(self,name,purge(value,seen))
                except Exception:pass
        # These aliases can reference the same PhotoImage; make the intent explicit.
        self._icon_image=None
        self._header_icon_image=None
        self._app_icon_image=None

    def destroy(self):
        # Destroy may be called by both a test/action and later cleanup. Make it idempotent.
        if getattr(self,'_destroy_complete',False):
            return
        self._closing=True
        self._cancel_event.set()
        try:
            if hasattr(self,'job_progress'):
                self.job_progress.stop()
                self.job_progress.configure(mode='determinate')
                self.job_progress['value']=0
        except (tk.TclError, AttributeError):
            pass

        # Give normal short-lived workers a chance to finish, but never allow a worker
        # merely holding a queue reference to own/finalize this Tk root.
        for thread in list(self._worker_threads):
            if thread is not threading.current_thread():
                thread.join(timeout=1.25)
        self._worker_threads=[]

        # Cancel every Tcl/Python after callback while the interpreter is still alive.
        try:
            info=self.tk.call('after','info')
            if not info:
                ids=[]
            elif isinstance(info,(tuple,list)):
                ids=[]
                for item in info:
                    if isinstance(item,(tuple,list)):
                        if item: ids.append(str(item[0]))
                    else:
                        ids.append(str(item))
            else:
                ids=[str(info)]
            for aid in ids:
                if aid:
                    try:self.after_cancel(aid)
                    except (tk.TclError, ValueError, TypeError):pass
        except (tk.TclError, TypeError):
            pass

        # Flush pending idle cleanup while Tcl is valid; do not start new application work.
        try:self.update_idletasks()
        except tk.TclError:pass

        try:self._release_tk_python_refs()
        except Exception:pass
        # Force wrapper finalizers on the UI/main thread before Tcl is destroyed.
        gc.collect()
        try:
            super().destroy()
        except tk.TclError:
            pass
        self._destroy_complete=True

    def _on_close(self):
        if self.session and self.session.dirty and not self._confirm_discard():return
        self.destroy()
