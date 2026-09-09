#!/usr/bin/env python3
"""Bounded starter/milestone verification. Contract: VERIFICATION_CONTRACT.md."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
VERSION = 1
MAX_BYTES = 16 * 1024 * 1024
SOURCE_ROOTS = ('api', 'web', 'ingestion-worker', 'chatops-bot', 'infra',
                'observability', 'security', 'tools', 'scripts', 'tests', '.github',
                '.agents/rules', '.agent/rules')
EXCLUDED_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.next',
                 '.pytest_cache', '.terraform', 'dist', 'build', 'coverage', 'reports',
                 'evidence', 'artifacts', 'test-results'}
REPORT_NAME = re.compile(r'^(?:eval[-_]|cost[-_]|red-team[-_]|incident[-_]|audit\.|chatops-audit\.|day[1-7]\.json|source-manifest\.json)')
REQUIRED_TESTS = {
    1: {'test_refactor_regression', 'test_empty_input', 'test_duplicate_or_invalid'},
    3: {'test_policy_allows_valid', 'test_policy_denies_unsafe'},
    5: {'test_permission_denied', 'test_approval_required',
        'test_approval_bound_to_action', 'test_duplicate_event'},
    6: {'test_injection_blocked', 'test_benign_allowed', 'test_budget_enforced'},
}


class Incomplete(Exception):
    pass


class Failed(Exception):
    pass


def need(condition, message):
    if not condition:
        raise Incomplete(message)


def require(condition, message):
    if not condition:
        raise Failed(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, name):
    need(isinstance(name, str) and name and not Path(name).is_absolute(),
         'Artifact path must be repository-relative')
    p = (root / name).resolve()
    need(p.is_relative_to(root.resolve()), 'Artifact escapes repository: ' + name)
    need(p.is_file(), 'Missing artifact: ' + name)
    need(0 < p.stat().st_size <= MAX_BYTES, 'Empty or oversized artifact: ' + name)
    return p


def load_json(path):
    try:
        need(path.is_file() and 0 < path.stat().st_size <= MAX_BYTES,
             'Missing, empty or oversized JSON: ' + str(path))
        # Reject duplicate keys and non-finite numbers, not silently last-key-wins.
        def pairs(items):
            result = {}
            for key, value in items:
                need(key not in result, 'Duplicate JSON key: ' + key)
                result[key] = value
            return result
        def invalid(value):
            raise Incomplete('Non-finite JSON number: ' + value)
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                          parse_constant=invalid)
    except (ValueError, UnicodeError, OSError, RecursionError) as exc:
        raise Incomplete('Invalid JSON: ' + str(path)) from exc


def timestamp(value):
    need(isinstance(value, str), 'Timestamp must be RFC3339 with timezone')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        need(parsed.tzinfo is not None, 'Timestamp needs a timezone')
        return parsed.timestamp()
    except ValueError as exc:
        raise Incomplete('Invalid timestamp: ' + value) from exc


def fresh(value, hours):
    observed = timestamp(value)
    age = time.time() - observed
    need(-60 <= age <= hours * 3600, 'Evidence is stale or future-dated')
    return observed


def real_text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return not re.search(r'(?i)^(?:TODO.*|placeholder|dummy|example|mock|fixture|fake|TBD|<[^>]+>|\.\.\.)$', value)


def number(value, nonnegative=True):
    return (type(value) in (int, float) and math.isfinite(value)
            and (not nonnegative or value >= 0))


def source_files(root):
    files = []
    for folder in SOURCE_ROOTS:
        base = root / folder
        if not base.exists():
            continue
        need(not base.is_symlink() and base.resolve().is_relative_to(root.resolve()),
             'Source directory escapes repository: ' + folder)
        for current, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS
                             and not (Path(current) / d).is_symlink())
            for name in names:
                p = Path(current) / name
                if (name.startswith('.env') or name.endswith(('.pyc', '.log', '.zip', '.html'))
                        or name == '.DS_Store' or REPORT_NAME.match(name)):
                    continue
                # Symlink targets outside the repo cannot become hidden source inputs.
                need(not p.is_symlink(), 'Source symlink unsupported: ' + str(p))
                files.append(p)
    for p in root.iterdir():
        if p.is_file() and (p.name in {'.env.example', '.mcp.json', '.mcp.json.template',
                           'AGENTS.md', 'CLAUDE.md', 'Running-Project-Specification-Student.md',
                           'Makefile', 'pyproject.toml', 'requirements.txt', 'package.json',
                           'package-lock.json', '.dockerignore'}
                           or re.fullmatch(r'(?:docker-)?compose.*\.ya?ml', p.name)):
            need(not p.is_symlink(), 'Source symlink unsupported: ' + str(p))
            files.append(p)
    for name in ('.codex/config.toml', '.agents/mcp_config.json'):
        p = root / name
        if p.is_file():
            need(not p.is_symlink() and p.resolve().is_relative_to(root.resolve()),
                 'Host config escapes repository: ' + name)
            files.append(p)
    return sorted(set(files), key=lambda p: p.relative_to(root).as_posix())


def fingerprint(root):
    digest = hashlib.sha256()
    files = source_files(root)
    need(files, 'No source files found')
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(bytes.fromhex(sha(path)))
    return digest.hexdigest()


def command(argv, cwd, timeout=60, env=None):
    need(shutil.which(str(argv[0])) is not None, 'Missing tool: ' + str(argv[0]))
    # No shell and no commands from evidence. Kill descendants on timeout.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(x) for x in argv], cwd=cwd, env=env,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise Incomplete('Command timed out: ' + str(argv[0])) from exc
        output.seek(0)
        result = output.read(MAX_BYTES + 1)
    need(len(result) <= MAX_BYTES, 'Command output exceeds limit')
    return process.returncode, result.decode('utf-8', errors='replace')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def valid_url(value):
    url = urllib.parse.urlsplit(value)
    need(url.scheme in {'http', 'https'} and url.hostname and not url.username
         and not url.password and not url.fragment, 'Expected HTTP(S) URL without credentials/fragment')
    return value.rstrip('/')


def read_http_body(response, deadline):
    chunks, size = [], 0
    while True:
        need(time.monotonic() < deadline, 'HTTP body exceeded total time budget')
        chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
        if not chunk:
            return b''.join(chunks)
        size += len(chunk)
        need(size <= MAX_BYTES, 'HTTP response exceeds limit')
        chunks.append(chunk)


def http(url, timeout, body=None, headers=None, method=None):
    valid_url(url)
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = read_http_body(response, deadline)
            return response.status, raw
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, read_http_body(exc, deadline)
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Incomplete('Endpoint unavailable: ' + url) from exc


def json_response(raw):
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise Failed('Endpoint returned invalid JSON') from exc


def smoke(args, async_required=False):
    for url in (args.api_url + '/healthz', args.api_url + '/readyz', args.web_url + '/api/health'):
        status, _ = http(url, args.timeout)
        require(status == 200, 'Health endpoint HTTP ' + str(status) + ': ' + url)
    # Unique filename prevents an old document from satisfying the new request.
    sample = safe_path(args.repo, args.sample)
    filename = 'verify-' + uuid.uuid4().hex + '.md'
    boundary = 'InsightHub' + uuid.uuid4().hex
    payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
               'Content-Type: text/markdown\r\n\r\n').encode() + sample.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    started = time.time()
    clock = time.monotonic()
    status, raw = http(args.api_url + '/documents', args.timeout, payload,
                       {'Content-Type': 'multipart/form-data; boundary=' + boundary})
    elapsed = time.monotonic() - clock
    require(status in ({202} if async_required else {201, 202}),
            'Upload expected ' + ('202 async' if async_required else '201 or 202') + ', got ' + str(status))
    if async_required:
        require(elapsed <= args.max_upload_seconds, 'Async upload exceeded responsiveness budget')
    doc = json_response(raw)
    require(isinstance(doc, dict) and type(doc.get('id')) in (str, int)
            and bool(str(doc['id'])) and not isinstance(doc['id'], bool), 'Upload missing document id')
    doc_id = doc['id']
    if status == 201:
        require(doc.get('status') == 'ready', 'Synchronous upload did not finish ready')
    else:
        require(doc.get('status') in {'pending', 'queued', 'processing', 'ready'}, 'Unknown upload state')
        deadline = time.monotonic() + args.poll_timeout
        # Always poll the freshly assigned ID, even if POST 202 already says ready.
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'Document did not become ready within polling budget')
            code, raw = http(args.api_url + '/documents', min(args.timeout, remaining))
            require(code == 200, 'Document polling HTTP ' + str(code))
            documents = json_response(raw)
            require(isinstance(documents, list), 'Document list must be an array')
            matches = [d for d in documents if isinstance(d, dict) and str(d.get('id')) == str(doc_id)]
            require(len(matches) <= 1, 'Duplicate document IDs in runtime response')
            if matches:
                doc = matches[0]
                require(doc.get('filename') == filename, 'Polled document does not match this upload')
                require(doc.get('status') in {'pending', 'queued', 'processing', 'ready'}, 'Worker failed or returned unknown state')
                if doc['status'] == 'ready':
                    break
            time.sleep(min(args.poll_interval, max(0, deadline - time.monotonic())))
    require(type(doc.get('chunk_count')) is int and doc['chunk_count'] > 0, 'Ready document has no chunks')
    code, raw = http(args.api_url + '/chat', args.timeout,
                     json.dumps({'question': args.question}).encode(), {'Content-Type': 'application/json'})
    require(code == 200, 'Chat HTTP ' + str(code))
    chat = json_response(raw)
    require(isinstance(chat, dict) and isinstance(chat.get('answer'), str)
            and bool(chat['answer'].strip()) and isinstance(chat.get('sources'), list)
            and bool(chat['sources']) and all(isinstance(x, str) and x.strip() for x in chat['sources'])
            and isinstance(chat.get('contexts'), list) and bool(chat['contexts'])
            and all(isinstance(x, dict) and any(isinstance(x.get(k), str) and x[k].strip()
                    for k in ('chunk_text', 'text', 'content')) for x in chat['contexts']), 'Chat needs nonempty answer, sources and contexts')
    code, raw = http(args.api_url + '/metrics', args.timeout)
    require(code == 200, 'Metrics endpoint unavailable')
    metric_lines = [line for line in raw.decode(errors='replace').splitlines() if not line.startswith('#')]
    numeric_samples = []
    for line in metric_lines:
        match = re.fullmatch(r'insighthub_[a-zA-Z0-9_:]+(?:\{.*\})?\s+(\S+)(?:\s+\d+)?', line)
        if match:
            try:
                numeric_samples.append(math.isfinite(float(match.group(1))))
            except ValueError:
                pass
    require(any(numeric_samples), 'No numeric InsightHub metric samples')
    return {'document_id': doc_id, 'filename': filename, 'started_at': started,
            'upload_status': status, 'runtime_verified': True,
            'note': 'Pipeline smoke only; retrieval quality/provider effectiveness not evaluated. Uploaded document retained.'}


def evidence(args, day):
    data = load_json(args.evidence_dir / f'day{day}.json')
    need(isinstance(data, dict) and type(data.get('schema_version')) is int and data.get('schema_version') == VERSION
         and type(data.get('day')) is int and data['day'] == day, 'Wrong evidence schema/day')
    need(data.get('mode') in {'real', 'fixture'}, 'Evidence mode must be real or fixture')
    fresh(data.get('observed_at'), args.max_age_hours)
    need(data.get('source_sha256') == fingerprint(args.repo), 'Evidence source digest differs from current content (including dirty edits)')
    need(isinstance(data.get('artifacts'), dict), 'Evidence artifacts must be an object')
    return data


def artifact(args, data, role):
    ref = data['artifacts'].get(role)
    need(isinstance(ref, dict), 'Missing artifact role: ' + role)
    p = safe_path(args.repo, ref.get('path'))
    need(ref.get('sha256') == sha(p), 'Artifact changed: ' + role)
    if p.stat().st_size < 2048:
        try:
            content = p.read_text().strip()
            need(real_text(content) and content not in {'{}', '[]'}, 'Known dummy artifact: ' + role)
        except UnicodeError:
            pass
    return p


def implemented_python(path):
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeError) as exc:
        raise Incomplete('Invalid Python: ' + str(path)) from exc
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    need(functions, 'No implemented functions: ' + str(path))
    meaningful = []
    for function in functions:
        body = [n for n in function.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                                               and isinstance(n.value.value, str))]
        if body and any(isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id == 'NotImplementedError')
                        for statement in body for n in ast.walk(statement)):
            meaningful.append(function)
    need(meaningful, 'Only placeholder Python functions: ' + str(path))


def validate_junit(path, required):
    need(path.is_file(), 'Test runner did not produce JUnit')
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise Incomplete('Malformed JUnit') from exc
    cases = list(root.iter('testcase'))
    need(cases, 'No tests collected')
    require(not any(c.find('failure') is not None or c.find('error') is not None for c in cases), 'Behavioral tests failed')
    need(not any(c.find('skipped') is not None for c in cases), 'Skipped/xfail tests do not complete a milestone')
    names = {c.get('name', '').split('[')[0] for c in cases}
    need(required <= names, 'Missing required scenarios: ' + ', '.join(sorted(required - names)))
    return len(cases)


def run_tests(args, day, scratch):
    folder = args.repo / 'tests' / 'milestones' / f'day{day}'
    files = sorted(folder.glob('test_*.py'))
    need(files, f'Missing student contract tests: tests/milestones/day{day}/test_*.py')
    for file in files:
        implemented_python(file)
    report = scratch / f'day{day}-junit.xml'
    observations = scratch / f'day{day}-observations.json'
    run_id = uuid.uuid4().hex
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               INSIGHTHUB_REPO_ROOT=str(args.repo), INSIGHTHUB_API_URL=args.api_url,
               INSIGHTHUB_WEB_URL=args.web_url, INSIGHTHUB_BOT_URL=args.bot_url,
               INSIGHTHUB_BOT_TRANSPORT=args.bot_transport,
               INSIGHTHUB_KUBE_CONTEXT=args.kube_context or '', INSIGHTHUB_NAMESPACE=args.namespace,
               INSIGHTHUB_VERIFY_RUN_ID=run_id, INSIGHTHUB_VERIFY_OBSERVATIONS=str(observations))
    # No project pytest config/conftest and no shell/plugin loading from JSON.
    code, output = command([sys.executable, '-B', '-m', 'pytest', '-c', '/dev/null',
                            '--confcutdir', str(folder), '-p', 'no:cacheprovider',
                            '--junitxml', str(report), *map(str, files)], scratch,
                           args.test_timeout, env)
    need(code not in {2, 3, 4, 5} and 'No module named pytest' not in output,
         'Test dependency/collection incomplete: ' + output[-1200:])
    require(code == 0, 'Test runner failed (exit ' + str(code) + '): ' + output[-1200:])
    required = set(REQUIRED_TESTS[day])
    if day == 1:
        required |= {'test_async_upload', 'test_worker_ingests', 'test_retry_idempotent'}
    if day == 5:
        required.add('test_invalid_signature' if args.bot_transport == 'http' else 'test_socket_event_ack')
    count = validate_junit(report, required)
    return {'count': count, 'run_id': run_id, 'observations': observations}


def docker_args(args):
    return ['docker'] + (['--context', args.docker_context] if args.docker_context else [])


def compose_args(args):
    result = docker_args(args) + ['compose', '-f', str(safe_path(args.repo, args.compose_file))]
    if args.compose_project:
        result += ['--project-name', args.compose_project]
    return result


def day1(args, data, scratch):
    implemented_python(artifact(args, data, 'refactor'))
    review = artifact(args, data, 'review').read_text()
    prose = re.sub(r'<!--.*?-->', '', review, flags=re.S)
    prose = '\n'.join(line for line in prose.splitlines() if line.strip() and not line.lstrip().startswith('#'))
    need(real_text(prose.strip()) and len(prose.split()) >= 15, 'Review artifact contains only headings/placeholders; explain change, risk and validation')
    run_tests(args, 1, scratch)
    implemented_python(artifact(args, data, 'worker'))
    dockerfile = artifact(args, data, 'worker_dockerfile').read_text()
    instructions = [line.strip() for line in dockerfile.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    need(any(line.upper().startswith('FROM ') for line in instructions)
         and any(line.upper().startswith(('CMD ', 'ENTRYPOINT ')) for line in instructions), 'Worker Dockerfile is a placeholder')
    code, text = command(compose_args(args) + ['ps', '--format', 'json', args.worker_service], scratch, args.timeout)
    require(code == 0, 'Cannot inspect selected Compose worker')
    try:
        records = json.loads(text) if text.lstrip().startswith('[') else [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError as exc:
        raise Incomplete('Unsupported Compose ps JSON') from exc
    require(any(r.get('Service') == args.worker_service and r.get('State', '').lower() == 'running' for r in records), 'Selected worker is not running')
    result = smoke(args, async_required=True)
    since = dt.datetime.fromtimestamp(result['started_at'], dt.timezone.utc).isoformat()
    code, logs = command(compose_args(args) + ['logs', '--no-color', '--no-log-prefix', '--since', since, args.worker_service], scratch, args.timeout)
    require(code == 0, 'Cannot read selected worker logs')
    matched = False
    for line in logs.splitlines():
        try:
            event = json.loads(line)
            if (isinstance(event, dict) and event.get('event') == 'ingestion_completed'
                    and str(event.get('document_id')) == str(result['document_id'])
                    and event.get('status') == 'ready'
                    and result['started_at'] - 1 <= timestamp(event.get('timestamp')) <= time.time() + 1):
                matched = True
        except (ValueError, Incomplete):
            continue
    require(matched, 'No fresh ingestion_completed event for this upload in running worker logs')
    return result


def day2(args, data, scratch):
    manifest = artifact(args, data, 'mcp_manifest')
    config = load_json(manifest)
    need(isinstance(config, dict) and config.get('schemaVersion') == 1
         and config.get('transport') == 'stdio', 'Unsupported MCP manifest')
    tools = config.get('tools', {})
    defaults, optional = tools.get('default'), tools.get('optional')
    need(isinstance(defaults, list) and defaults and isinstance(optional, list)
         and all(real_text(t) for t in defaults + optional), 'Manifest lacks supported tool capabilities')
    supported = set(defaults + optional)
    requested = set((args.mcp_tools if args.mcp_tools is not None else ','.join(defaults)).split(','))
    requested = {t.strip() for t in requested if t.strip()}
    need(requested and requested <= supported, 'Requested MCP tools empty or unsupported by manifest')
    sdk = safe_path(args.repo, 'tools/mcp/smoke.mjs')
    core_test = safe_path(args.repo, 'tools/mcp/test/core.test.mjs')
    server_test = safe_path(args.repo, 'tools/mcp/test/server.test.mjs')
    env = dict(os.environ, INSIGHTHUB_API_URL=args.api_url,
               INSIGHTHUB_MCP_TOOLS=','.join(sorted(requested)),
               INSIGHTHUB_MCP_PROMETHEUS='1' if 'prometheus_summary' in requested else '0')
    if args.prometheus_url:
        env['INSIGHTHUB_PROMETHEUS_URL'] = args.prometheus_url
    # Paths and arguments are fixed here. manifest install/test/smoke fields are never executed.
    for argv in (['node', '--test', '--test-reporter=tap', str(core_test), str(server_test)],
                 ['node', str(sdk)] + (['--live'] if data['mode'] == 'real' else [])):
        code, output = command(argv, scratch, args.test_timeout, env)
        need(code == 0 or not re.search(r'listen EACCES|listen EPERM', output),
             'Loopback socket permission unavailable for MCP integration tests')
        need(not re.search(r'ERR_MODULE_NOT_FOUND|Cannot find package|Cannot find module', output),
             'MCP dependencies missing; run npm ci --prefix tools/mcp --ignore-scripts')
        require(code == 0, 'MCP SDK/permission tests failed: ' + output[-1600:])
        if '--test' in argv:
            counts = {key: int(value) for key, value in re.findall(r'^# (tests|pass|fail|skipped|todo) (\d+)$', output, re.M)}
            need(counts.get('tests', 0) > 0 and counts.get('pass') == counts['tests']
                 and counts.get('fail') == 0 and counts.get('skipped') == 0 and counts.get('todo') == 0,
                 'MCP tests missing, skipped or incomplete')
    result = json_response(output.encode())
    need(isinstance(result, dict) and result.get('backend_mode') == ('live' if data['mode'] == 'real' else 'fixture')
         and result.get('live') is (data['mode'] == 'real') and result.get('backend') ==
         ('live-loopback' if data['mode'] == 'real' else 'fixture-loopback'),
         'MCP backend provenance missing or fixture used as live evidence')
    require(result.get('passed') is True, 'MCP contract did not pass')
    results = result.get('results')
    need(isinstance(results, list) and results, 'MCP smoke contains no SDK observations')
    protocol = config.get('protocol')
    need(isinstance(protocol, dict) and real_text(protocol.get('modern')) and real_text(protocol.get('legacy')),
         'Manifest lacks supported protocol versions')
    observed_modes = set()
    for item in results:
        need(isinstance(item, dict) and item.get('mode') not in observed_modes, 'Duplicate/invalid MCP SDK observation')
        mode = item.get('mode')
        need(mode in {'modern', 'auto', 'legacy', 'v1'}, 'Unsupported SDK negotiation mode')
        expected_protocol = protocol['modern'] if mode in {'modern', 'auto'} else protocol['legacy']
        require(item.get('protocol') == expected_protocol, 'SDK negotiated protocol differs from manifest')
        observed_modes.add(mode)
        calls, methods = item.get('calls'), item.get('methods')
        require(item.get('passed') is True and isinstance(calls, list) and bool(calls)
                and isinstance(methods, list) and {'tools/list', 'tools/call'} <= set(methods),
                'MCP requires actual listing and successful tool invocation')
        need(set(calls) <= supported, 'SDK called tools outside supported manifest')
        if data['mode'] == 'real':
            require(set(calls) == requested, 'Live MCP calls differ from requested capabilities')
    return {'runtime_verified': data['mode'] == 'real', 'sdk_result': result,
            'note': 'Real SDK subprocess and permission tests executed; backend mode explicitly recorded.'}


def day3(args, data, scratch):
    deployment = artifact(args, data, 'deployment')
    binding = load_json(artifact(args, data, 'ci_binding'))
    expected = {'source_sha256': fingerprint(args.repo), 'artifact_sha256': sha(deployment)}
    need(isinstance(binding, dict) and all(binding.get(k) == v for k, v in expected.items()), 'CI binding does not match current source/artifact')
    if args.ci_profile == 'github':
        need(args.ci_repo and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.ci_repo)
         and args.ci_run_id and args.ci_run_id.isdigit(), 'Day 3 needs --ci-repo owner/repo and --ci-run-id NUMBER')
    run_tests(args, 3, scratch)
    infra = args.repo / 'infra'
    need(list(infra.glob('*.tf')), 'Missing Terraform implementation')
    target = scratch / 'infra'
    shutil.copytree(infra, target, ignore=shutil.ignore_patterns('.terraform', '*.tfstate*'))
    for cmd in (['terraform', 'fmt', '-check', '-recursive'],
                ['terraform', 'init', '-backend=false', '-input=false'],
                ['terraform', 'validate', '-no-color'], ['checkov', '-d', '.', '--quiet']):
        code, output = command(cmd, target, args.test_timeout)
        require(code == 0, 'Policy/tool failed: ' + cmd[0] + ' ' + ' '.join(cmd[1:]) + '\n' + output[-1000:])
    if args.ci_profile == 'local':
        return {'runtime_verified': True, 'ci_profile': 'local', 'source_sha256': expected['source_sha256'],
                'artifact_sha256': expected['artifact_sha256'],
                'note': 'Fresh local policy/tests verified; content binding checked. Artifact build provenance and deployed health require separate review.'}
    code, raw = command(['gh', 'run', 'view', args.ci_run_id, '--repo', args.ci_repo,
                         '--json', 'status,conclusion,updatedAt,headSha,url'], scratch, args.timeout)
    require(code == 0, 'Cannot fetch requested CI run')
    live = json_response(raw.encode())
    require(live.get('status') == 'completed' and live.get('conclusion') == 'success', 'Requested CI run is not successful')
    fresh(live.get('updatedAt'), args.max_age_hours)
    downloaded = scratch / 'ci-binding'
    downloaded.mkdir()
    code, _ = command(['gh', 'run', 'download', args.ci_run_id, '--repo', args.ci_repo,
                       '--name', 'verification-source', '--dir', str(downloaded)], scratch, args.timeout)
    need(code == 0, 'CI run lacks downloadable verification-source artifact')
    actual = load_json(downloaded / 'source-manifest.json')
    require(isinstance(actual, dict) and all(actual.get(k) == v for k, v in expected.items()), 'Live CI artifact belongs to different source/build')
    return {'runtime_verified': True, 'ci_url': live.get('url'),
            'note': 'CI/policy verified; deployment health is not attested.'}


def load_yaml(path):
    try:
        import yaml
    except ImportError as exc:
        raise Incomplete('PyYAML required for structured rule/test validation; install scripts/requirements-verification.txt') from exc
    try:
        return yaml.safe_load(path.read_text())
    except (yaml.YAMLError, UnicodeError, OSError) as exc:
        raise Incomplete('Invalid rule/test YAML: ' + str(path)) from exc


def validate_rule_tests(rules, tests):
    rule_data, test_data = load_yaml(rules), load_yaml(tests)
    need(isinstance(rule_data, dict) and isinstance(rule_data.get('groups'), list)
         and rule_data['groups'], 'Rules contain no groups')
    actual_rules = [r for g in rule_data['groups'] if isinstance(g, dict)
                    for r in g.get('rules', []) if isinstance(r, dict) and real_text(r.get('expr'))
                    and (real_text(r.get('alert')) or real_text(r.get('record'))) ]
    need(actual_rules, 'No executable alert/recording expressions')
    need(isinstance(test_data, dict) and isinstance(test_data.get('tests'), list)
         and test_data['tests'], 'Promtool test file contains no tests')
    rule_files = test_data.get('rule_files')
    need(isinstance(rule_files, list) and rule_files
         and all(isinstance(f, str) and (tests.parent / f).resolve() == rules.resolve() for f in rule_files),
         'Rule tests must reference the submitted rule artifact')
    for case in test_data['tests']:
        need(isinstance(case, dict) and isinstance(case.get('input_series'), list)
             and case['input_series'], 'Rule test missing telemetry input series')
        need(all(isinstance(series, dict) and real_text(series.get('series'))
                 and real_text(series.get('values')) for series in case['input_series']), 'Placeholder input series')
        alerts, expressions = case.get('alert_rule_test', []), case.get('promql_expr_test', [])
        need(isinstance(alerts, list) and isinstance(expressions, list) and (alerts or expressions),
             'Rule test missing expected assertions')
        for assertion in alerts:
            need(isinstance(assertion, dict) and real_text(assertion.get('alertname'))
                 and 'eval_time' in assertion and isinstance(assertion.get('exp_alerts'), list), 'Invalid alert assertion')
        for assertion in expressions:
            need(isinstance(assertion, dict) and real_text(assertion.get('expr'))
                 and 'eval_time' in assertion and isinstance(assertion.get('exp_samples'), list), 'Invalid expression assertion')


def verify_rca_component(args, data, scratch):
    rca = load_json(artifact(args, data, 'rca'))
    dashboard = load_json(artifact(args, data, 'dashboard'))
    rules = artifact(args, data, 'rules')
    tests = artifact(args, data, 'rule_tests')
    validate_rule_tests(rules, tests)
    need(isinstance(dashboard, dict) and isinstance(dashboard.get('panels'), list)
         and any(isinstance(p, dict) and any(isinstance(t, dict) and real_text(t.get('expr'))
                 for t in p.get('targets', [])) for p in dashboard['panels']), 'Dashboard has no real query targets')
    need(isinstance(rca, dict) and real_text(rca.get('incident_id'))
         and isinstance(rca.get('hypotheses'), list) and rca['hypotheses']
         and all(real_text(x) for x in rca['hypotheses']), 'RCA needs incident and substantive hypotheses')
    start = fresh(rca.get('started_at'), args.max_age_hours)
    end = fresh(rca.get('ended_at'), args.max_age_hours)
    need(start < end, 'RCA incident window must have positive duration')
    samples = rca.get('samples')
    need(isinstance(samples, list) and samples, 'RCA has no timestamped samples')
    need(args.prometheus_url, 'Day 4 needs --prometheus-url')
    for cmd in (['promtool', 'check', 'rules', str(rules)], ['promtool', 'test', 'rules', str(tests)]):
        code, output = command(cmd, rules.parent, args.test_timeout)
        require(code == 0, 'Prometheus rule validation failed: ' + output[-1000:])
    for sample in samples:
        need(isinstance(sample, dict) and re.fullmatch(r'[a-zA-Z_:][a-zA-Z0-9_:]*', sample.get('metric', '')),
             'Invalid RCA metric name')
        at = timestamp(sample.get('timestamp'))
        need(start <= at <= end and number(sample.get('value'), False), 'Sample outside incident window or nonnumeric')
        labels = sample.get('labels')
        need(isinstance(labels, dict) and all(re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', k)
             and isinstance(v, str) for k, v in labels.items()), 'Invalid metric labels')
        selector = sample['metric'] + ('{' + ','.join(k + '=' + json.dumps(v) for k, v in sorted(labels.items())) + '}' if labels else '')
        query = urllib.parse.urlencode({'query': selector, 'start': at, 'end': at + 1, 'step': 1})
        code, raw = http(args.prometheus_url + '/api/v1/query_range?' + query, args.timeout)
        require(code == 200, 'Prometheus query failed')
        response = json_response(raw)
        require(response.get('status') == 'success' and response.get('data', {}).get('resultType') == 'matrix', 'Prometheus did not return range data')
        matched = False
        for series in response['data'].get('result', []):
            for ts, value in series.get('values', []):
                if abs(float(ts) - at) < 1 and math.isclose(float(value), sample['value'], rel_tol=1e-6, abs_tol=1e-9):
                    matched = True
        require(matched, 'RCA citation does not match live telemetry at timestamp')
    return {'runtime_verified': True, 'samples_checked': len(samples),
            'note': 'Telemetry citations validated; causal quality of RCA still requires review.'}


def day4(args, data, scratch):
    dashboard = load_json(artifact(args, data, 'dashboard'))
    def query_panels(panels):
        result = []
        for panel in panels:
            if not isinstance(panel, dict):
                continue
            if any(isinstance(t, dict) and real_text(t.get('expr')) for t in panel.get('targets', [])):
                result.append(panel)
            result.extend(query_panels(panel.get('panels', [])))
        return result
    need(isinstance(dashboard, dict) and len(query_panels(dashboard.get('panels', []))) >= 9,
         'Day 4 requires at least nine panels with real query targets')
    artifact(args, data, 'mlops_notes')
    roles = ('rca', 'rca_2', 'rca_3')
    reports = [load_json(artifact(args, data, role)) for role in roles]
    need(all(isinstance(r, dict) and real_text(r.get('incident_id')) for r in reports)
         and len({r['incident_id'] for r in reports}) == 3, 'Day 4 requires three distinct incident reports')
    results = []
    for role in roles:
        one = dict(data, artifacts=dict(data['artifacts'], rca=data['artifacts'][role]))
        results.append(verify_rca_component(args, one, scratch))
    return {'runtime_verified': all(r['runtime_verified'] for r in results),
            'incidents_checked': 3, 'samples_checked': sum(r['samples_checked'] for r in results),
            'note': 'Three RCA telemetry contracts checked; alert delivery, panel coverage and MLOps knowledge still require specification review.'}


def audit_events(data, run_id=None, after=None):
    need(isinstance(data, dict) and isinstance(data.get('events'), list) and data['events'], 'Missing structured audit events')
    decisions = set()
    for event in data['events']:
        need(isinstance(event, dict) and all(real_text(event.get(k)) for k in ('event_id', 'action', 'user')), 'Invalid audit event')
        at = timestamp(event.get('timestamp'))
        need(at <= time.time() + 60, 'Future audit event')
        need(event.get('decision') in {'allowed', 'denied', 'approval_required'}, 'Invalid audit decision')
        if run_id:
            need(event.get('test_run_id') == run_id and at >= after - 1, 'Audit not bound to this test run')
        decisions.add(event['decision'])
    need({'denied', 'approval_required'} <= decisions, 'Audit lacks permission/approval evidence')


def day5(args, data, scratch):
    implemented_python(artifact(args, data, 'permissions'))
    saved = load_json(artifact(args, data, 'audit'))
    audit_events(saved)
    before = time.time()
    tests = run_tests(args, 5, scratch)
    actual = load_json(tests['observations'])
    need(actual.get('run_id') == tests['run_id'], 'Fresh audit has wrong run_id')
    audit_events(actual, tests['run_id'], before)
    if args.bot_transport == 'http':
        code, raw = http(args.bot_url + '/healthz', args.timeout)
        require(code == 200 and isinstance(json_response(raw), dict), 'ChatOps health failed')
    return {'runtime_verified': True, 'tests': tests['count'],
            'bot_transport': args.bot_transport,
            'note': 'Permission/approval/dedup and selected transport tested locally with audit; external Slack delivery not tested.'}


def eval_report(report, dataset, digest, source, args, final):
    need(isinstance(report, dict) and report.get('mode') in {'real', 'fixture'}, 'Evaluation missing mode')
    fresh(report.get('observed_at'), args.max_age_hours)
    need(report.get('source_sha256') == source and report.get('dataset_sha256') == digest, 'Evaluation source/dataset digest mismatch')
    results = report.get('results')
    need(isinstance(results, list) and results, 'Evaluation missing results')
    by_id = {}
    request_ids = set()
    for result in results:
        need(isinstance(result, dict) and result.get('case_id') in dataset and result['case_id'] not in by_id,
             'Unknown/duplicate evaluation case')
        need(type(result.get('passed')) is bool and result.get('severity') in {'low', 'medium', 'high', 'critical'}, 'Evaluation needs boolean passed and severity')
        for key in ('input_tokens', 'output_tokens'):
            need(type(result.get(key)) is int and result[key] >= 0, 'Invalid token count')
        for key in ('provider', 'model', 'request_id'):
            need((isinstance(result.get(key), str) and bool(result[key].strip()))
                 if report['mode'] == 'fixture' else real_text(result.get(key)), 'Missing/placeholder evaluation provenance: ' + key)
        need(result['request_id'] not in request_ids, 'Duplicate evaluation request_id')
        request_ids.add(result['request_id'])
        if report['mode'] == 'real':
            need(not re.search(r'(?i)(hash|extractive|fallback|fixture|mock|dummy|fake)', result['provider'] + ' ' + result['model']), 'Fallback is not real-model evaluation')
        if final:
            require(result['passed'], 'Final evaluation failed case: ' + result['case_id'])
        by_id[result['case_id']] = result
    need(set(by_id) == set(dataset), 'Evaluation does not cover the whole dataset')
    return by_id


def cost_report(cost, results, source, args):
    need(isinstance(cost, dict) and cost.get('mode') in {'real', 'fixture'} and cost.get('currency') == 'USD', 'Cost report missing mode/USD currency')
    fresh(cost.get('observed_at'), args.max_age_hours)
    need(cost.get('source_sha256') == source, 'Cost source digest mismatch')
    need(number(cost.get('budget_usd')) and cost['budget_usd'] > 0 and number(cost.get('total_usd')), 'Invalid budget/total')
    expected = {r['request_id']: r for r in results.values()}
    entries = cost.get('entries')
    need(isinstance(entries, list) and entries, 'Missing cost entries')
    seen, total = set(), 0
    for row in entries:
        need(isinstance(row, dict) and row.get('request_id') in expected and row['request_id'] not in seen, 'Unknown/duplicate cost request')
        result = expected[row['request_id']]
        for key in ('input_tokens', 'output_tokens'):
            need(type(row.get(key)) is int and row[key] == result[key], 'Cost tokens differ from evaluation')
        for key in ('input_usd_per_million', 'output_usd_per_million', 'cost_usd'):
            need(number(row.get(key)), 'Invalid cost/rate')
        calculated = (row['input_tokens'] * row['input_usd_per_million'] + row['output_tokens'] * row['output_usd_per_million']) / 1_000_000
        require(math.isclose(calculated, row['cost_usd'], rel_tol=1e-6, abs_tol=1e-9), 'Cost arithmetic mismatch')
        if cost['mode'] == 'real' and row['cost_usd'] == 0:
            usage = row.get('resource_usage')
            need(isinstance(usage, dict) and real_text(usage.get('measurement_source'))
                 and number(usage.get('duration_seconds')) and usage['duration_seconds'] > 0
                 and type(usage.get('memory_peak_bytes')) is int and usage['memory_peak_bytes'] > 0,
                 'Zero provider cost requires measured duration and peak memory; electricity is not assumed free')
        total += row['cost_usd']
        seen.add(row['request_id'])
    need(seen == set(expected), 'Cost report does not cover final evaluation requests')
    require(math.isclose(total, cost['total_usd'], rel_tol=1e-6, abs_tol=1e-9), 'Cost total mismatch')
    require(total <= cost['budget_usd'], 'Evaluation exceeds declared budget')


def day6(args, data, scratch):
    dataset_file = artifact(args, data, 'dataset')
    dataset = load_json(dataset_file)
    need(isinstance(dataset, dict) and isinstance(dataset.get('cases'), list) and dataset['cases'], 'Missing evaluation dataset')
    cases = {}
    for row in dataset['cases']:
        need(isinstance(row, dict) and all(real_text(row.get(k)) for k in ('id', 'category', 'input', 'expected')), 'Invalid/placeholder dataset case')
        need(row['id'] not in cases, 'Duplicate dataset case id')
        cases[row['id']] = row
    need({'injection', 'benign'} <= {row['category'] for row in cases.values()}, 'Dataset must test attacks and benign requests')
    source = fingerprint(args.repo)
    initial = load_json(artifact(args, data, 'eval_initial'))
    final = load_json(artifact(args, data, 'eval_final'))
    cost = load_json(artifact(args, data, 'cost'))
    eval_report(initial, cases, sha(dataset_file), source, args, False)
    results = eval_report(final, cases, sha(dataset_file), source, args, True)
    cost_report(cost, results, source, args)
    need(timestamp(initial['observed_at']) <= timestamp(final['observed_at']), 'Final evaluation predates initial')
    before = time.time()
    tests = run_tests(args, 6, scratch)
    actual = load_json(tests['observations'])
    need(isinstance(actual, dict) and actual.get('run_id') == tests['run_id'], 'Evaluation observations not bound to this run')
    actual_final, actual_cost = actual.get('eval_final'), actual.get('cost')
    live_results = eval_report(actual_final, cases, sha(dataset_file), source, args, True)
    cost_report(actual_cost, live_results, source, args)
    need(timestamp(actual_final['observed_at']) >= before - 1 and timestamp(actual_cost['observed_at']) >= before - 1, 'Tests reused stale evaluation/cost observations')
    need(all(r['mode'] == data['mode'] for r in (initial, final, cost, actual_final, actual_cost)), 'Mixed real/fixture evidence modes')
    return {'runtime_verified': data['mode'] == 'real', 'cases': len(cases),
            'note': 'Executed local evaluation contract; provider identity/billing and dataset adequacy require review.'}


def starter(args):
    for name in ('api/app/main.py', 'api/app/routers/documents.py', 'web/package.json',
                 'api/requirements.txt', 'infra/db/init.sql', args.compose_file, args.sample):
        safe_path(args.repo, name)
    for path in (args.repo / 'api').rglob('*.py'):
        if '__pycache__' not in path.parts:
            ast.parse(path.read_text(), filename=str(path))
    package = load_json(args.repo / 'web/package.json')
    need(isinstance(package, dict) and package.get('scripts'), 'Web package scripts missing')
    return {'runtime_verified': False, 'note': 'Starter file/syntax contract only. Run base tests and smoke separately; Days 1-6 remain student work.'}


def setup(args, scratch):
    need(sys.version_info >= (3, 11), 'Python 3.11+ required')
    for tool in ('docker', 'node', 'npm'):
        need(shutil.which(tool), 'Missing starter tool: ' + tool)
    code, output = command(['node', '-p', 'process.versions.node.split(".")[0]'], scratch, args.timeout)
    need(code == 0 and output.strip().isdigit() and int(output.strip()) >= 20, 'Node.js 20+ required')
    code, _ = command(docker_args(args) + ['info'], scratch, args.timeout)
    need(code == 0, 'Selected Docker daemon unavailable')
    code, output = command(compose_args(args) + ['config', '--format', 'json'], scratch, args.timeout)
    require(code == 0, 'Compose config failed')
    config = json_response(output.encode())
    require({'api', 'web', 'postgres'} <= set(config.get('services', {})), 'Compose missing core starter services')
    return {'runtime_verified': False, 'note': 'Local tools and Compose configuration validated; application runtime not checked.'}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Incomplete('Invalid arguments: ' + message)


def positive(value):
    try:
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError()
        return number
    except ValueError as exc:
        raise argparse.ArgumentTypeError('must be finite and positive') from exc


def parser():
    p = Parser(description=__doc__)
    p.add_argument('target', nargs='?', default='starter', choices=['starter', 'setup', 'smoke', 'fingerprint'] + [f'day{i}' for i in range(1, 8)])
    p.add_argument('--repo', type=Path, default=ROOT)
    p.add_argument('--evidence-dir', type=Path, default=Path('evidence'))
    p.add_argument('--json', action='store_true')
    p.add_argument('--api-url', default=os.environ.get('API_URL', 'http://localhost:8000'))
    p.add_argument('--web-url', default=os.environ.get('WEB_URL', 'http://localhost:3000'))
    p.add_argument('--bot-url', default=os.environ.get('BOT_URL', 'http://localhost:8080'))
    p.add_argument('--prometheus-url', default=os.environ.get('PROMETHEUS_URL'))
    p.add_argument('--docker-context', default=os.environ.get('DOCKER_CONTEXT'))
    p.add_argument('--kube-context', default=os.environ.get('KUBE_CONTEXT'))
    p.add_argument('--namespace', default=os.environ.get('NAMESPACE', 'insighthub-dev'))
    p.add_argument('--compose-file', default='docker-compose.yml')
    p.add_argument('--compose-project')
    p.add_argument('--worker-service', default='ingestion-worker')
    p.add_argument('--extended', action='store_true', help='Legacy alias; Day 1 always requires async worker')
    p.add_argument('--ci-profile', choices=['local', 'github'], default='github')
    p.add_argument('--bot-transport', choices=['socket', 'http'], default='http')
    p.add_argument('--mcp-tools', default=os.environ.get('INSIGHTHUB_MCP_TOOLS'))
    p.add_argument('--ci-repo')
    p.add_argument('--ci-run-id')
    p.add_argument('--sample', default='sample-docs/so-tay-van-hanh.md')
    p.add_argument('--question', default='InsightHub có những thành phần chính nào?')
    p.add_argument('--timeout', type=positive, default=10)
    p.add_argument('--test-timeout', type=positive, default=120)
    p.add_argument('--poll-timeout', type=positive, default=30)
    p.add_argument('--poll-interval', type=positive, default=1)
    p.add_argument('--max-upload-seconds', type=positive, default=1)
    p.add_argument('--max-age-hours', type=positive, default=24)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    report = {'schema_version': VERSION, 'target': 'unknown', 'status': 'INCOMPLETE',
              'scope': 'none', 'runtime_verified': False, 'source_sha256': None, 'milestone_complete': False, 'checks': []}
    try:
        args = parser().parse_args(argv)
        args.repo = args.repo.resolve()
        need(args.repo.is_dir(), 'Repository directory does not exist')
        args.evidence_dir = (args.repo / args.evidence_dir).resolve()
        for name in ('api_url', 'web_url', 'bot_url', 'prometheus_url'):
            if getattr(args, name):
                setattr(args, name, valid_url(getattr(args, name)))
        report.update(target=args.target, source_sha256=fingerprint(args.repo),
                      scope='structure' if args.target in {'starter', 'fingerprint'} else
                      'environment' if args.target == 'setup' else
                      'partial-runtime-contract' if args.target.startswith('day') else 'runtime-contract')
        if args.target == 'fingerprint':
            report['status'] = 'PASS'
        else:
            targets = [f'day{i}' for i in range(1, 7)] if args.target == 'day7' else [args.target]
            
            # Force use /tmp directory for Linux/MacOS, otherwise use default temp directory (Window)
            default_tmp = '/tmp' if os.path.exists('/tmp') else None
            
            with tempfile.TemporaryDirectory(prefix='insighthub-verify-', dir=default_tmp) as tmp:
                for target in targets:
                    scratch = Path(tmp) / target
                    scratch.mkdir()
                    check = {'id': target, 'status': 'PASS', 'runtime_verified': False}
                    try:
                        if target.startswith('day'):
                            day = int(target[3:])
                            data = evidence(args, day)
                            detail = globals()[target](args, data, scratch)
                            need(not (day == 3 and args.ci_profile == 'local'), 'Local preparation checked; GitHub pipeline remains mandatory for Day 3')
                            need(data['mode'] == 'real', 'Fixture checks completed; real milestone remains INCOMPLETE')
                        elif target == 'smoke':
                            detail = smoke(args)
                        elif target == 'setup':
                            detail = setup(args, scratch)
                        else:
                            detail = starter(args)
                        check.update(detail)
                    except (Incomplete, Failed) as exc:
                        check.update(status='INCOMPLETE' if isinstance(exc, Incomplete) else 'FAIL', message=str(exc))
                    except (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError) as exc:
                        check.update(status='INCOMPLETE', message='Malformed artifact or unavailable dependency: ' + str(exc))
                    report['checks'].append(check)
            # Fail takes precedence; missing prerequisites can never be PASS.
            statuses = {c['status'] for c in report['checks']}
            report['status'] = 'FAIL' if 'FAIL' in statuses else 'INCOMPLETE' if 'INCOMPLETE' in statuses else 'PASS'
            report['runtime_verified'] = report['status'] == 'PASS' and all(c['runtime_verified'] for c in report['checks'])
            if args.target.startswith('day'):
                report['specification_review_required'] = True
                report['note'] = 'PASS covers implemented checks only, not all project requirements; use the complete specification and reviewer evidence.'
            if args.target == 'day7' and report['status'] == 'PASS':
                report.update(status='INCOMPLETE', runtime_verified=False)
                report['checks'].append({'id': 'full-project-review', 'status': 'INCOMPLETE',
                                         'message': 'Automated subset passed; full Must-have, showcase and submission review is required.'})
            if fingerprint(args.repo) != report['source_sha256']:
                report.update(status='INCOMPLETE', runtime_verified=False)
                report['checks'].append({'id': 'source-stability', 'status': 'INCOMPLETE',
                                         'message': 'Source changed during verification; rerun on settled content.'})
    except (Incomplete, OSError, ValueError) as exc:
        report['checks'].append({'id': 'input', 'status': 'INCOMPLETE', 'message': str(exc)})
    if '--json' in argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report['target'] == 'fingerprint' and report['status'] == 'PASS':
        print(report['source_sha256'])
    else:
        print(f"{report['status']} {report['target']} (scope={report['scope']}, runtime_verified={str(report['runtime_verified']).lower()})")
        for check in report['checks']:
            print(f"  {check['status']} {check['id']}: {check.get('message', check.get('note', 'bounded contract satisfied'))}")
    return {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
