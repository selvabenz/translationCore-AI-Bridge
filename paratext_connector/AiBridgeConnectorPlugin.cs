using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.Threading;
using Paratext.PluginInterfaces;

namespace TranslationCoreAiBridge.ParatextConnector
{
    /// <summary>
    /// Paratext 9.5 companion for translationCore AI Bridge.
    /// Deliberate write boundary: this plugin can create Project Notes only. It contains no
    /// PutUSFM/PutUSX/Scripture-write operation.
    /// </summary>
    public sealed class AiBridgeConnectorPlugin : IParatextStartupAutomaticPlugin, IPluginObject
    {
        private const string PluginVersion = "0.7.4";
        private IPluginHost _host;
        private NamedPipeBridgeServer _server;
        private SynchronizationContext _uiContext;
        private long _stateRevision;
        private string _lastEvent = "startup";
        private string _lastOriginId = String.Empty;
        private readonly object _stateLock = new object();

        public string Name { get { return "translationCore AI Bridge Connector"; } }
        public string Publisher { get { return "translationCore AI Bridge"; } }
        public Version Version { get { return new Version(0, 7, 4, 0); } }
        public string VersionString { get { return PluginVersion; } }

        public string GetDescription(string locale)
        {
            return "Local connector for translationCore AI Bridge: Paratext user/project state, " +
                   "two-way Scripture navigation, selected text, and Project Notes. Scripture writing is disabled.";
        }

        public IDataFileMerger GetMerger(IPluginHost host, string dataIdentifier)
        {
            return null;
        }

        public void Run(IPluginHost host)
        {
            if (host == null) throw new ArgumentNullException("host");
            _host = host;
            _uiContext = SynchronizationContext.Current;

            _host.VerseRefChanged += OnVerseRefChanged;
            _host.ActiveWindowSelectionChanged += OnActiveWindowSelectionChanged;
            _host.ShuttingDown += OnShuttingDown;

            _server = new NamedPipeBridgeServer(HandlePipeRequest);
            _server.Start();
            TouchState("startup", String.Empty);
        }

        private void OnVerseRefChanged(IPluginHost sender, IVerseRef newReference, SyncReferenceGroup group)
        {
            TouchState("reference_changed", String.Empty);
        }

        private void OnActiveWindowSelectionChanged(IPluginHost sender, IParatextChildState activeWindowState, IReadOnlyList<ISelection> currentSelections)
        {
            TouchState("selection_changed", String.Empty);
        }

        private void OnShuttingDown(object sender, CancelEventArgs e)
        {
            try
            {
                if (_host != null)
                {
                    _host.VerseRefChanged -= OnVerseRefChanged;
                    _host.ActiveWindowSelectionChanged -= OnActiveWindowSelectionChanged;
                    _host.ShuttingDown -= OnShuttingDown;
                }
            }
            catch { }
            try { if (_server != null) _server.Dispose(); }
            catch { }
            _server = null;
        }

        private void TouchState(string eventName, string originId)
        {
            lock (_stateLock)
            {
                _stateRevision++;
                _lastEvent = eventName ?? String.Empty;
                if (!String.IsNullOrEmpty(originId)) _lastOriginId = originId;
            }
        }

        private BridgeResponse HandlePipeRequest(BridgeRequest request)
        {
            BridgeResponse response = null;
            Exception failure = null;
            Action action = delegate
            {
                try { response = HandleOnParatextThread(request); }
                catch (Exception ex) { failure = ex; }
            };

            if (_uiContext != null && SynchronizationContext.Current != _uiContext)
                _uiContext.Send(delegate(object ignored) { action(); }, null);
            else
                action();

            if (failure != null)
                return new BridgeResponse { ok = false, error = failure.Message, plugin_version = PluginVersion };
            return response ?? new BridgeResponse { ok = false, error = "Paratext connector returned no response.", plugin_version = PluginVersion };
        }

        private BridgeResponse HandleOnParatextThread(BridgeRequest request)
        {
            string action = (request.action ?? String.Empty).Trim().ToLowerInvariant();
            if (action == "get_state") return BuildStateResponse();
            if (action == "set_reference") return SetReference(request.payload);
            if (action == "create_note") return CreateNote(request.payload);
            return new BridgeResponse { ok = false, error = "Unsupported connector action: " + action, plugin_version = PluginVersion };
        }

        private BridgeResponse BuildStateResponse()
        {
            IParatextChildState window = _host.ActiveWindowState;
            IReadOnlyProject project = window == null ? null : window.Project;
            IScriptureTextSelection selection = FirstScriptureSelection(window == null ? null : window.Selections);

            long revision;
            string lastEvent;
            string lastOrigin;
            lock (_stateLock)
            {
                revision = _stateRevision;
                lastEvent = _lastEvent;
                lastOrigin = _lastOriginId;
            }

            BridgeResponse r = new BridgeResponse();
            r.ok = true;
            r.user = _host.UserInfo == null ? String.Empty : (_host.UserInfo.Name ?? String.Empty);
            r.project_name = project == null ? String.Empty : (project.ShortName ?? String.Empty);
            r.project_id = project == null ? String.Empty : (project.ID ?? String.Empty);
            r.project_language = project == null ? String.Empty : (project.LanguageName ?? String.Empty);
            r.reference = window == null ? String.Empty : FormatReference(window.VerseRef);
            r.selected_text = selection == null ? String.Empty : (selection.SelectedText ?? String.Empty);
            r.selection_reference = selection == null ? String.Empty : FormatReference(selection.VerseRefStart);
            r.before_context = selection == null ? String.Empty : (selection.BeforeContext ?? String.Empty);
            r.after_context = selection == null ? String.Empty : (selection.AfterContext ?? String.Empty);
            r.selection_offset = selection == null ? -1 : selection.Offset;
            r.sync_group = window == null ? String.Empty : window.SyncReferenceGroup.ToString();
            r.paratext_version = _host.ApplicationVersion == null ? String.Empty : _host.ApplicationVersion.ToString();
            r.plugin_version = PluginVersion;
            r.state_revision = revision;
            r.last_event = lastEvent;
            r.last_origin_id = lastOrigin;
            r.capabilities = new string[] { "state", "navigation", "selection", "project_notes" };
            return r;
        }

        private BridgeResponse SetReference(IDictionary<string, object> payload)
        {
            IParatextChildState window = _host.ActiveWindowState;
            if (window == null || window.Project == null)
                return Fail("Open a Paratext Scripture project window before synchronizing navigation.");

            string text = BridgeJson.GetString(payload, "reference").Trim().ToUpperInvariant();
            string originId = BridgeJson.GetString(payload, "origin_id");
            if (String.IsNullOrEmpty(text))
                return Fail("Scripture reference is empty.");

            SyncReferenceGroup group = window.SyncReferenceGroup;
            if (group == SyncReferenceGroup.None)
                return Fail("The active Paratext window is not in a scroll/sync group. Put it in group A-E, then retry.");

            IVerseRef verseRef;
            try
            {
                // Let Paratext's own versification/reference parser resolve the book. This avoids
                // hard-coding the 66-book canon and remains correct for project-specific canons.
                verseRef = window.Project.Versification.CreateReference(text);
            }
            catch (Exception ex)
            {
                return Fail("Paratext could not resolve Scripture reference " + text + ": " + ex.Message);
            }
            if (verseRef == null)
                return Fail("Paratext could not resolve Scripture reference: " + text);

            _host.SetReferenceForSyncGroup(verseRef, group);
            TouchState("reference_set_by_bridge", originId);

            BridgeResponse r = BuildStateResponse();
            r.message = "Paratext navigation updated to " + text + ".";
            return r;
        }

        private BridgeResponse CreateNote(IDictionary<string, object> payload)
        {
            IParatextChildState window = _host.ActiveWindowState;
            if (window == null || window.Project == null)
                return Fail("Open the destination Paratext project before creating a note.");

            IProject project = window.Project as IProject;
            if (project == null)
                return Fail("The active Paratext project is read-only and cannot accept Project Notes.");

            string expectedProjectId = BridgeJson.GetString(payload, "project_id").Trim();
            if (!String.IsNullOrEmpty(expectedProjectId) && !String.Equals(project.ID, expectedProjectId, StringComparison.OrdinalIgnoreCase))
                return Fail("The active Paratext project changed. Refresh the connector before creating the note.");

            string referenceText = BridgeJson.GetString(payload, "reference").Trim().ToUpperInvariant();
            string selectedText = BridgeJson.GetString(payload, "selected_text");
            string beforeContext = BridgeJson.GetString(payload, "before_context");
            string afterContext = BridgeJson.GetString(payload, "after_context");
            string comment = BridgeJson.GetString(payload, "comment").Trim();
            string assigneeName = BridgeJson.GetString(payload, "assignee").Trim();
            string externalAuthor = BridgeJson.GetString(payload, "external_author").Trim();
            string noteAuthor = _host.UserInfo == null ? String.Empty : (_host.UserInfo.Name ?? String.Empty).Trim();

            if (String.IsNullOrEmpty(noteAuthor))
                return Fail("Project Note AUTHOR failed: Paratext did not expose the current logged-in user. The Bridge will not invent an AI Paratext account.");
            if (String.IsNullOrEmpty(comment)) return Fail("Reviewer note text is empty.");

            if (String.IsNullOrEmpty(referenceText))
                return Fail("Scripture reference is empty.");
            IVerseRef verseRef;
            try
            {
                verseRef = project.Versification.CreateReference(referenceText);
            }
            catch (Exception ex)
            {
                return Fail("Paratext could not resolve Scripture reference " + referenceText + ": " + ex.Message);
            }
            if (verseRef == null)
                return Fail("Paratext could not resolve Scripture reference: " + referenceText);

            IScriptureTextSelection anchor;
            string anchorError;
            if (!TryResolveAnchor(project, window, verseRef, selectedText, beforeContext, afterContext, out anchor, out anchorError))
                return Fail(anchorError);

            IUserInfo assignee = FindProjectUser(project, assigneeName);
            string body = comment;
            if (!String.IsNullOrEmpty(externalAuthor))
                body = "[" + externalAuthor + "]\r\n" + comment;

            IWriteLock writeLock = null;
            try
            {
                try
                {
                    writeLock = project.RequestWriteLock(this, delegate(IWriteLock requested)
                    {
                        try { if (requested != null) requested.Dispose(); }
                        catch { }
                    }, WriteLockScope.ProjectNotes);
                }
                catch (Exception ex)
                {
                    return Fail("Project Note WRITE_LOCK failed: " + ex.Message);
                }
                if (writeLock == null)
                    return Fail("Project Note WRITE_LOCK failed: Paratext could not grant a Project Notes write lock. Check project permissions and try again.");

                try
                {
                    CommentParagraph paragraph = new CommentParagraph(new FormattedString(body));
                    project.AddNote(writeLock, anchor, new CommentParagraph[] { paragraph }, null, assignee);
                }
                catch (Exception ex)
                {
                    return Fail("Project Note ADD_NOTE failed for " + referenceText + " as " + noteAuthor + ": " + ex.Message);
                }
            }
            finally
            {
                try { if (writeLock != null) writeLock.Dispose(); }
                catch { }
            }

            TouchState("project_note_created", String.Empty);
            BridgeResponse r = BuildStateResponse();
            r.note_created = true;
            r.message = "Paratext Project Note created at " + referenceText + " by " + noteAuthor +
                        (String.IsNullOrEmpty(externalAuthor) ? "." : ". External source: " + externalAuthor + ".");
            return r;
        }

        private static bool TryResolveAnchor(IProject project, IParatextChildState window, IVerseRef reference,
            string selectedText, string beforeContext, string afterContext,
            out IScriptureTextSelection anchor, out string error)
        {
            anchor = null;
            error = String.Empty;

            if (String.IsNullOrEmpty(selectedText))
            {
                anchor = project.GetScriptureSelectionForVerse(reference);
                if (anchor == null)
                {
                    error = "Paratext could not create a verse-level note anchor.";
                    return false;
                }
                return true;
            }

            IScriptureTextSelection active = FirstScriptureSelection(window.Selections);
            if (active != null && String.Equals(active.SelectedText, selectedText, StringComparison.Ordinal) &&
                String.Equals(FormatReference(active.VerseRefStart), FormatReference(reference), StringComparison.OrdinalIgnoreCase))
            {
                anchor = active;
                return true;
            }

            IReadOnlyList<IScriptureTextSelection> matches = project.FindMatchingScriptureSelections(reference, selectedText, null, false, false);
            if (matches == null || matches.Count == 0)
            {
                error = "The selected text was not found in the current Paratext verse. Select the exact text in Paratext and retry.";
                return false;
            }
            if (matches.Count == 1)
            {
                anchor = matches[0];
                return true;
            }

            IScriptureTextSelection contextMatch = null;
            int contextMatches = 0;
            for (int i = 0; i < matches.Count; i++)
            {
                IScriptureTextSelection candidate = matches[i];
                if (ContextCompatible(candidate.BeforeContext, beforeContext, true) &&
                    ContextCompatible(candidate.AfterContext, afterContext, false))
                {
                    contextMatch = candidate;
                    contextMatches++;
                }
            }
            if (contextMatches == 1)
            {
                anchor = contextMatch;
                return true;
            }

            error = "The selected text occurs more than once in this verse. Select the exact occurrence inside Paratext, then retry so the note cannot attach to the wrong word.";
            return false;
        }

        private static bool ContextCompatible(string actual, string supplied, bool compareSuffix)
        {
            if (String.IsNullOrEmpty(supplied)) return true;
            actual = actual ?? String.Empty;
            supplied = supplied.Trim();
            if (supplied.Length > 80)
                supplied = compareSuffix ? supplied.Substring(supplied.Length - 80) : supplied.Substring(0, 80);
            return compareSuffix
                ? actual.EndsWith(supplied, StringComparison.Ordinal)
                : actual.StartsWith(supplied, StringComparison.Ordinal);
        }

        private static IScriptureTextSelection FirstScriptureSelection(IReadOnlyList<ISelection> selections)
        {
            if (selections == null) return null;
            for (int i = 0; i < selections.Count; i++)
            {
                IScriptureTextSelection text = selections[i] as IScriptureTextSelection;
                if (text != null) return text;
            }
            return null;
        }

        private static IUserInfo FindProjectUser(IProject project, string name)
        {
            if (String.IsNullOrEmpty(name) || project.NonObserverUsers == null) return null;
            for (int i = 0; i < project.NonObserverUsers.Count; i++)
            {
                IUserInfo user = project.NonObserverUsers[i];
                if (user != null && String.Equals(user.Name, name, StringComparison.OrdinalIgnoreCase))
                    return user;
            }
            return null;
        }

        private static BridgeResponse Fail(string message)
        {
            return new BridgeResponse { ok = false, error = message, plugin_version = PluginVersion };
        }

        private static string FormatReference(IVerseRef reference)
        {
            if (reference == null) return String.Empty;
            return String.Format(CultureInfo.InvariantCulture, "{0} {1}:{2}", reference.BookCode, reference.ChapterNum, reference.VerseNum);
        }

    }
}
