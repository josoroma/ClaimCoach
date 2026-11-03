#!/usr/bin/env python3
"""Validate real server vectors and API behavior; never substitute generated vectors."""
import argparse
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:18203')
parser.add_argument('--output', type=Path, default=Path(__file__).with_name('embedding-validation.json'))
args = parser.parse_args()
if not args.url.startswith('http://127.0.0.1:'):
    raise SystemExit('Only local loopback servers are accepted')
texts = [
    'Authorization evidence is required to review this denied claim.',
    'The clinic must attach the authorization record to its appeal.',
    'Saturn is a large planet with rings.',
    'Authorization evidence is required to review this denied claim.',
]
start = time.monotonic()
request = urllib.request.Request(args.url + '/v1/embeddings', data=json.dumps({'input': texts, 'model': 'default'}).encode(), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=120) as response:
    result = json.load(response)
rows = [item['embedding'] for item in result['data']]
norms = [math.sqrt(sum(value * value for value in row)) for row in rows]
dot = lambda left, right: sum(x * y for x, y in zip(left, right))
assert len(rows) == 4
assert [item['index'] for item in result['data']] == [0, 1, 2, 3]
assert all(len(row) == 4096 and all(math.isfinite(x) for x in row) for row in rows)
assert all(abs(norm - 1) < 1e-5 for norm in norms)
assert dot(rows[0], rows[3]) > 0.9999
assert dot(rows[0], rows[1]) > dot(rows[0], rows[2])
invalid = urllib.request.Request(args.url + '/v1/embeddings', data=b'{"input": [""]}', headers={'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(invalid, timeout=10)
    raise AssertionError('Empty input was accepted')
except urllib.error.HTTPError as error:
    assert error.code == 400
summary = {
    'model': result['model'], 'count': len(rows), 'dimensions': [len(row) for row in rows],
    'norms': norms, 'same_text_similarity': dot(rows[0], rows[3]),
    'related_text_similarity': dot(rows[0], rows[1]), 'unrelated_text_similarity': dot(rows[0], rows[2]),
    'elapsed_seconds': round(time.monotonic() - start, 3), 'usage': result['usage'],
    'empty_input_status': 400,
    'inference': 'real local MLX weights; last-token hidden-state pooling; L2-normalized',
}
args.output.write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
