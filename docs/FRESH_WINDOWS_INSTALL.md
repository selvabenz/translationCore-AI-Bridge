# Fresh Windows Installation

## End-user prerequisites

The normal installed application is intended to be self-contained. End-user computers do **not** need Python, Tk, Pillow, PyInstaller, or Inno Setup.

Required:

- Windows 10 or Windows 11, 64-bit compatible
- access to the translationCore data folder the reviewer will use
- internet access for OpenAI-powered features
- an OpenAI API key for AI features

Optional:

- **Git for Windows** — only for Git checkpoint/history/diff features. The rest of the application remains available without Git.

## Recommended distribution format

Distribute `translationCore-AI-Bridge-v0.7.5-Setup.exe`, not the source ZIP. The installer places the packaged PyInstaller one-directory application under the current user's Local AppData Programs directory, creates Start Menu shortcuts, and supports an optional desktop shortcut.

The installer itself should be built on a Windows build machine using `build_windows_installer.bat` or the included GitHub Actions workflow.

## Fresh-machine certification

Before broad distribution, test the exact installer on a clean Windows Sandbox/VM with no Python installed:

1. Install the Setup EXE.
2. Launch from Start Menu.
3. Confirm the custom icon appears.
4. Open a translationCore data folder.
5. Confirm project discovery and verse navigation.
6. Enter/test an API key.
7. Run AI alignment and Full Verse Review on a disposable project copy.
8. Close/reopen the app and confirm settings/state persistence.
9. Confirm uninstall removes program files without deleting translationCore projects.
10. If Git is not installed, confirm only Git-specific functionality is unavailable.

## Why Python is not installed as a prerequisite

The packaged app is produced by PyInstaller in one-directory mode. The Python interpreter and imported application libraries are placed inside the application bundle. Installing a separate system Python would add an unnecessary global dependency and could introduce version conflicts.
