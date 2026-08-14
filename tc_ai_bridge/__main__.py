from __future__ import annotations
import argparse
from .ui import BridgeApp


def main():
    parser=argparse.ArgumentParser(description='translationCore AI Bridge v0.7.0')
    parser.add_argument('--root',help='translationCore data root to load at startup')
    args=parser.parse_args()
    app=BridgeApp(args.root)
    app.mainloop()

if __name__=='__main__': main()
