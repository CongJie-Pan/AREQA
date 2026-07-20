"""Command-line entry point for the PELICAN MVP web server."""

import argparse

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the PELICAN MVP web server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    uvicorn.run("pelican_mvp.server:app", host=args.host, port=args.port)
