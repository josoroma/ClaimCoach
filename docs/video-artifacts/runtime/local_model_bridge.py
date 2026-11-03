#!/usr/bin/env python3
"""Loopback-only adapter to the existing authenticated MTPLX model.

No inference is synthesized here. The adapter forwards actual model responses,
and reads the local server key from its existing protected file at launch.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', choices=['127.0.0.1'], default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18206)
    parser.add_argument('--model', required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    args = parser.parse_args()
    token = args.key_file.read_text().strip()
    opener = build_opener(ProxyHandler({}))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def forward(self):
            if self.path not in ('/v1/models', '/v1/chat/completions'):
                self.send_error(404)
                return
            payload = None
            if self.command == 'POST':
                size = int(self.headers.get('Content-Length', 0))
                if size > 8 * 1024 * 1024:
                    self.send_error(413)
                    return
                body = json.loads(self.rfile.read(size))
                body['model'] = args.model
                body['stream'] = False
                payload = json.dumps(body).encode()
            request = Request('http://127.0.0.1:8080' + self.path, data=payload,
                              headers={'Authorization': 'Bearer ' + token,
                                       'Content-Type': 'application/json'}, method=self.command)
            try:
                with opener.open(request, timeout=240) as response:
                    data, status = response.read(), response.status
            except (HTTPError, URLError, TimeoutError):
                data, status = b'{"error":"local_model_unavailable"}', 502
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = forward
        do_POST = forward

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
