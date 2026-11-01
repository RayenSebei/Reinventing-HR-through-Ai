"""Run the server:  python -m app  [--host 127.0.0.1] [--port 8000] [--seed]"""
import argparse

import uvicorn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--seed", action="store_true", help="create demo users and a demo case (wipes existing data)")
    args = ap.parse_args()
    import os
    import sys
    from .config import validate
    problems = validate(os.environ)       # RB-14: refuse to start with unsafe or incomplete settings
    if problems:
        print("Vouch will not start:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        raise SystemExit(2)
    if args.seed:
        from .seed import seed
        print(seed())
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
