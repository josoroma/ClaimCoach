#!/usr/bin/env python3
"""Loopback-only Qwen3 embedding adapter for this recorded demo.

Uses installed local MLX weights, the transformer body (not vocabulary logits),
last-token pooling and L2 normalization, per the Qwen embedding model card:
https://huggingface.co/Qwen/Qwen3-Embedding-8B#transformers-usage

Documents are encoded without an instruction or chat template. Each input is
processed separately, so there is no padding and the final token is always real.
No network model downloads, model stand-ins, or request-content logs.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class EmbeddingEngine:
    def __init__(self, model_path: Path, max_tokens: int = 8192):
        if not model_path.is_dir() or not (model_path / 'config.json').is_file():
            raise ValueError('A local model directory is required')
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import mlx.core as mx
        from mlx_lm import load
        self.mx = mx
        self.model, self.tokenizer = load(str(model_path))
        self.model_id = model_path.name
        self.max_tokens = max_tokens
        if self.model.model_type != 'qwen3':
            raise ValueError('This adapter requires a Qwen3 transformer')

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        rows = []
        tokens = 0
        mx = self.mx
        for text in texts:
            ids = self.tokenizer.encode(text, add_special_tokens=True)
            if not ids or len(ids) > self.max_tokens:
                raise ValueError('Input is empty or exceeds the token limit')
            # Qwen3Model returns normalized final hidden states before the LM head.
            hidden = self.model.model(mx.array([ids]))
            pooled = hidden[0, -1, :].astype(mx.float32)
            vector = pooled / mx.maximum(mx.sqrt(mx.sum(pooled * pooled)), 1e-12)
            mx.eval(vector)
            rows.append(vector.tolist())
            tokens += len(ids)
            del hidden, pooled, vector
            mx.clear_cache()
        return rows, tokens


def serve(engine: EmbeddingEngine, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def reply(self, status: int, body: dict) -> None:
            payload = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path in ('/health', '/healthz'):
                self.reply(200, {'status': 'ok', 'model': engine.model_id})
            elif self.path == '/v1/models':
                self.reply(200, {'object': 'list', 'data': [{'id': engine.model_id, 'object': 'model'}]})
            else:
                self.reply(404, {'error': {'message': 'Not found'}})

        def do_POST(self):
            if self.path != '/v1/embeddings':
                self.reply(404, {'error': {'message': 'Not found'}})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2 * 1024 * 1024:
                    raise ValueError('Request exceeds the byte limit')
                data = json.loads(self.rfile.read(length))
                inputs = data.get('input')
                if isinstance(inputs, str):
                    inputs = [inputs]
                if not isinstance(inputs, list) or not 1 <= len(inputs) <= 32:
                    raise ValueError('Input must contain between one and 32 strings')
                if not all(isinstance(item, str) and item.strip() for item in inputs):
                    raise ValueError('Input must contain non-empty strings')
                if data.get('encoding_format', 'float') != 'float':
                    raise ValueError('Only float encoding is supported')
                if data.get('dimensions', 4096) != 4096:
                    raise ValueError('This adapter returns 4096 dimensions')
                rows, tokens = engine.embed(inputs)
                self.reply(200, {
                    'object': 'list', 'model': engine.model_id,
                    'data': [{'object': 'embedding', 'index': i, 'embedding': row} for i, row in enumerate(rows)],
                    'usage': {'prompt_tokens': tokens, 'total_tokens': tokens},
                })
            except (ValueError, TypeError, json.JSONDecodeError):
                self.reply(400, {'error': {'message': 'Invalid embedding request'}})
            except Exception:
                self.reply(500, {'error': {'message': 'Local embedding inference failed'}})

    server = HTTPServer((host, port), Handler)
    print(json.dumps({'ready': True, 'host': host, 'port': port, 'model': engine.model_id}), flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--host', choices=['127.0.0.1'], default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18203)
    args = parser.parse_args()
    serve(EmbeddingEngine(args.model.expanduser().resolve()), args.host, args.port)


if __name__ == '__main__':
    main()
