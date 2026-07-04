import argparse



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("poll")
    subparsers.add_parser("digest")
    subparsers.add_parser("bot")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "poll":
        print("poll")
    elif args.command == "digest":
        print("digest")
    else:
        print("bot")
