from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def _load_pillow():
    try:
        from PIL import Image
        return Image
    except Exception as exc:
        raise SystemExit(
            'Pillow is required only for icon preparation. Run set_app_icon.bat instead, '
            'which creates an isolated build-time environment automatically.\n'
            f'Detail: {exc}'
        )


def square_icon(image, size: int, Image):
    image = image.convert('RGBA')
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    margin = max(1, int(size * 0.06))
    inner = max(1, size - margin * 2)
    image.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    x = (size - image.width) // 2
    y = (size - image.height) // 2
    canvas.alpha_composite(image, (x, y))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description='Prepare all translationCore AI Bridge icon assets from one image.')
    parser.add_argument('source', help='PNG/JPG/WEBP/ICO source image')
    parser.add_argument('--assets', default=str(Path(__file__).resolve().parents[1] / 'assets'))
    parser.add_argument('--userguide', default=str(Path(__file__).resolve().parents[1] / 'userguide'))
    args = parser.parse_args()
    source = Path(args.source).expanduser().resolve()
    assets = Path(args.assets).expanduser().resolve()
    userguide = Path(args.userguide).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f'Icon source not found: {source}')
    Image = _load_pillow()
    assets.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as im:
            base = square_icon(im, 512, Image)
            png = assets / 'app_icon.png'
            png48 = assets / 'app_icon_48.png'
            ico = assets / 'app_icon.ico'
            base.save(png, 'PNG', optimize=True)
            small = square_icon(base, 48, Image)
            small.save(png48, 'PNG', optimize=True)
            # Multi-resolution Windows icon. Keeping common shell/taskbar sizes avoids fuzzy scaling.
            base.save(
                ico,
                'ICO',
                sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)],
            )
            shutil.copy2(source, assets / ('app_icon_source' + source.suffix.lower()))
            if userguide.exists():
                small.save(userguide / 'app_icon_48.png', 'PNG', optimize=True)
    except Exception as exc:
        raise SystemExit(f'Could not prepare icon: {exc}')
    print(f'Updated: {assets / "app_icon.ico"}')
    print(f'Updated: {assets / "app_icon.png"}')
    print(f'Updated: {assets / "app_icon_48.png"}')
    if userguide.exists(): print(f'Updated: {userguide / "app_icon_48.png"}')
    print('Rebuild the EXE and installer so Windows embeds the new icon.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
