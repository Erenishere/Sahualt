import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Internal-only Sahulat AI voice HTTP runtime")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    import uvicorn

    uvicorn.run(
        "sahulat_api.voice:create_voice_app",
        factory=True,
        host="127.0.0.1",
        port=args.port,
        workers=1,
        access_log=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
