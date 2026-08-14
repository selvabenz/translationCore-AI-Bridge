# Changing the Application Icon

The Bridge uses one source design to generate all icon assets used by Windows and the UI.

## Recommended source image

Use a square PNG at least **512×512** pixels. Transparent background is supported. Avoid very fine text or details because the Windows taskbar may display the icon at 16–32 pixels.

## One-command method

From the application source folder run:

```bat
set_app_icon.bat "C:\path\to\my-new-icon.png"
```

The helper creates an isolated `.venv-icon` on the **build computer only**, installs Pillow there, and regenerates:

- `assets\app_icon.ico` — multi-resolution Windows icon (16 through 256 px)
- `assets\app_icon.png` — large UI/documentation icon
- `assets\app_icon_48.png` — Tk title/header icon
- `userguide\app_icon_48.png` — user-guide icon
- `assets\app_icon_source.*` — copy of the chosen source image

Then rebuild:

```bat
build_windows_installer.bat
```

or at minimum:

```bat
build_windows_exe.bat
```

Windows embeds the icon into the EXE at build time, so simply replacing the image after the EXE is built will not change the executable icon.

## Manual method

If you already have a high-quality multi-resolution `.ico`, replace `assets\app_icon.ico`. Also replace `assets\app_icon.png` and `assets\app_icon_48.png` so the in-app icon matches the EXE/installer icon.

After rebuilding, Windows Explorer may temporarily show an old cached icon. Testing the new EXE under a new filename/version or restarting Explorer usually confirms the embedded icon correctly.
