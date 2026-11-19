#!/usr/bin/env python3
"""Launch the local game. No agents, network services or API keys required."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT","1")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chain Reaction: three human players, no AI")
    parser.add_argument("--backend",choices=("auto","pygame","tk"),default="auto")
    parser.add_argument("--example",action="store_true",help="Load a fixed, legal cascade teaching position")
    parser.add_argument("--replay",type=Path,help="Load and validate a saved match")
    parser.add_argument("--rows",type=int,default=9)
    parser.add_argument("--cols",type=int,default=6)
    parser.add_argument("--move-limit",type=int,default=None,help="Optional total-move draw rule; off by default")
    parser.add_argument("--size",default="1366x873")
    parser.add_argument("--data-dir",type=Path,default=None)
    parser.add_argument("--no-save",action="store_true",help="Disable autosave (useful for testing)")
    parser.add_argument("--screenshot",type=Path,help="Render a PNG without opening a window")
    parser.add_argument("--frames",type=int,default=0,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if sys.version_info < (3,10):
        parser.error("Python 3.10 or later is required")
    try:
        from chain_reaction.controller import Controller
        from chain_reaction.engine import Config
        from chain_reaction.render import Renderer
        from chain_reaction.session import Session
        from chain_reaction.window import run_pygame,run_tk
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nRun: python -m pip install -r requirements.txt",file=sys.stderr)
        return 1
    try:
        size=tuple(int(x) for x in args.size.lower().split("x"))
        if len(size)!=2 or min(size)<200:
            raise ValueError("Use --size WIDTHxHEIGHT, e.g. 1366x873")
        model=Controller(Config(rows=args.rows,cols=args.cols,move_limit=args.move_limit),args.data_dir)
        model.storage_enabled=not args.no_save
        if args.replay:
            model.load_session(Session.load(args.replay))
            model.notify("Saved match loaded and validated.")
        elif args.example:
            model.action("example")
        renderer=Renderer()
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True,exist_ok=True)
            renderer.render(model).save(args.screenshot)
            print(f"Screenshot saved: {args.screenshot}")
            return 0
        backend=args.backend
        if backend=="auto":
            try:
                import pygame
                backend="pygame"
            except ImportError:
                backend="tk"
                print("pygame-ce not installed; using the shared-renderer Tk fallback.")
        print(f"Chain Reaction: 3 local human players | backend={backend} | no AI")
        (run_pygame if backend=="pygame" else run_tk)(model,renderer,size,args.frames)
        return 0
    except (OSError,ValueError,ImportError) as exc:
        print(f"Cannot start the game: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
