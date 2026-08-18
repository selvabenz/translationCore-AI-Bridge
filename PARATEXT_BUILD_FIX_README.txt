translationCore AI Bridge v0.7.4 — Paratext buildfix4
=====================================================

Target: Paratext 9.5.110.1

What field testing proved
-------------------------
- The local Paratext connector and two-way verse synchronization are working.
- buildfix3 moved Project Notes sync away from the failing Registry/Data Access grant and into the local Plugin API.
- On smaller screens, the Production page could still crop long status text and hide lower Paratext controls after a project/connector was loaded.

What buildfix4 changes
----------------------
1. Production is vertically scrollable, including after project/Paratext state expands.
2. Production automatically stacks into one column on smaller windows.
3. Production and Paratext action toolbars reflow instead of clipping horizontally.
4. The old separate Notes 1.1 and Live Connector cards are merged into one compact Paratext card.
5. Daily Paratext actions are now only:
   - Connect / Refresh
   - Verify / Bind Project
   - Sync Notes
   - Export Notes XML
6. Duplicate top-level Paratext sync/export buttons were removed.
7. Separate Bind Active Project and Create Live Note diagnostic buttons were removed from Production.
8. Connector installation/update was moved to Settings & Log.
9. The live-review checkbox is shortened to Auto-send review notes; its tooltip preserves the full behavior.
10. Long internal Notes companion paths are no longer displayed in the normal Production status line.
11. Verify / Bind Project can explicitly bind an unbound project or replace an intentional mismatch after confirmation.

No Scripture-writing capability was added.

Windows update steps
--------------------
1. Extract this ZIP into a new folder; do not mix files into the old source folder.
2. The Paratext plugin code did not require a protocol change for this UI fix, but installing the packaged connector again is safe if desired.
3. Restart translationCore AI Bridge.
4. Open the intended Paratext Scripture project.
5. On Production, use Connect / Refresh and Verify / Bind Project.
6. Confirm the displayed Paratext user/project are correct.
7. Enable Sync verse navigation and/or Auto-send review notes as desired.
8. Use Sync Notes for pending reviewer notes.

Expected note identity
----------------------
Paratext Author:  the real current Paratext user (for example Yesu Selva Benz)
AI provenance:    AI Suggestion
Export filename:  Notes_AI_Suggestion.xml

The filename is not a Paratext account.
