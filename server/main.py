import argparse
import os
import uvicorn

def main():
    parser = argparse.ArgumentParser(description="Codenames server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    parser.add_argument("--token", default=None, help="Auth token")
    parser.add_argument("--no-auth", action="store_true", help="Disable auth")
    args = parser.parse_args()

    if not args.no_auth and not args.token:
        parser.error("--token is required unless --no-auth is set")

    if args.no_auth:
        os.environ["CODENAMES_TOKEN"] = ""
    else:
        os.environ["CODENAMES_TOKEN"] = args.token
        print(f"Auth token: {args.token}")

    print(f"Starting Codenames server on {args.host}:{args.port}")
    uvicorn.run("server.api:app", host=args.host, port=args.port)

if __name__ == "__main__":
    main()