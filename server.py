"""Local-only OpenAI Canvas. No ComfyUI or machine-learning runtime required."""
from datetime import datetime, timezone
import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import engine

APP_ID = 'openai-canvas-portable'
VERSION = '1.1.0'
ROOT = Path(__file__).resolve().parent
if os.environ.get('OPENAI_CANVAS_DATA_DIR'):
    DATA = Path(os.environ['OPENAI_CANVAS_DATA_DIR']).expanduser().resolve()
elif sys.platform == 'win32':
    DATA = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'OpenAI Canvas'
elif sys.platform == 'darwin':
    DATA = Path.home() / 'Library/Application Support/OpenAI Canvas'
else:
    DATA = Path.home() / '.local/share/openai-canvas'
OUTPUT = DATA / 'outputs'
engine.CONFIG = DATA / 'config.local.json'
MAX_BODY = 180 * 1024 * 1024
api_lock = threading.Lock()
file_lock = threading.Lock()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_workflow(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('工作流格式错误')
    nodes, edges = value.get('nodes'), value.get('edges')
    if not isinstance(nodes, list) or len(nodes) > 200 or not isinstance(edges, list):
        raise ValueError('工作流节点或连线格式错误')
    # The UI validates graph semantics; never interpret a saved workflow as code.
    if any(not isinstance(node, dict) or 'api_key' in node for node in nodes) or 'api_key' in value:
        raise ValueError('工作流不得保存 API Key')
    return value


def reference_labels(data, images):
    labels = data.get('labels', [])
    if not isinstance(labels, list) or (labels and len(labels) != len(images)):
        raise ValueError('参考图标签数量不匹配')
    allowed = {'未指定', '人物', '服装', '场景', '动作构图', '商品', '风格'}
    if any(not isinstance(label, str) or label not in allowed for label in labels):
        raise ValueError('参考图角色标签无效')
    return labels


def labeled_prompt(prompt, labels):
    if not labels or all(label == '未指定' for label in labels):
        return prompt
    return prompt + '\n\n参考图角色（按输入顺序）：\n' + '\n'.join(
        f'图{i + 1}：{label}' for i, label in enumerate(labels))


class Handler(BaseHTTPRequestHandler):
    server_version = 'OpenAICanvas/1.0'

    def log_message(self, fmt, *args):
        pass  # Do not log submitted prompts, pictures or keys.

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json_response(self, status, value):
        self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def is_local_request(self):
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        return host in allowed and (not origin or origin == 'http://' + host)

    def do_GET(self):
        if not self.is_local_request():
            return self.json_response(403, {'error': '只允许本机同源访问'})
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path == '/openai-canvas/status':
            try:
                engine.api_key()
                configured = True
            except (ValueError, OSError):
                configured = False
            return self.json_response(200, {'app': APP_ID, 'version': VERSION, 'configured': configured, 'busy': api_lock.locked(), 'output_directory': str(OUTPUT), 'key_source': 'environment' if os.environ.get('OPENAI_API_KEY') else 'local'})
        if path == '/openai-canvas/workflow':
            try:
                with file_lock:
                    value = json.loads((DATA / 'workflow.json').read_text(encoding='utf-8')) if (DATA / 'workflow.json').exists() else None
                return self.json_response(200, {'workflow': value})
            except (ValueError, OSError):
                return self.json_response(500, {'error': '已保存工作流无法读取，请从导出的 JSON 恢复。'})
        if path == '/openai-canvas/history':
            records = []
            with file_lock:
                for item in (DATA / 'history').glob('*.json'):
                    try:
                        entry = json.loads(item.read_text(encoding='utf-8'))
                        records.append({k: entry[k] for k in ('id', 'created_at', 'images', 'parameters')})
                    except (OSError, ValueError, KeyError):
                        continue
            records.sort(key=lambda entry: entry['created_at'], reverse=True)
            return self.json_response(200, {'history': records})
        if path.startswith('/openai-canvas/history/'):
            identifier = path.rsplit('/', 1)[-1]
            if not re.fullmatch(r'[a-f0-9]{32}', identifier):
                return self.json_response(400, {'error': '历史记录编号无效'})
            try:
                with file_lock:
                    value = json.loads((DATA / 'history' / (identifier + '.json')).read_text(encoding='utf-8'))
                return self.json_response(200, value)
            except (OSError, ValueError):
                return self.json_response(404, {'error': '历史记录不存在或无法读取'})
        file = None
        if path in {'/', '/openai-canvas', '/openai-canvas/'}:
            file = ROOT / 'studio/index.html'
        elif path.startswith('/openai-canvas/assets/'):
            name = path.rsplit('/', 1)[-1]
            if name in {'style.css', 'app.js'}:
                file = ROOT / 'studio' / name
        elif path == '/view':
            query = urllib.parse.parse_qs(parsed.query)
            name = query.get('filename', [''])[0]
            if re.fullmatch(r'[a-f0-9]{32}\.png', name):
                file = OUTPUT / name
        if file and file.is_file():
            return self.send_bytes(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        return self.json_response(404, {'error': '文件不存在。导入别人工作流中的结果图片需另行传输原图。'})

    def do_POST(self):
        if not self.is_local_request():
            return self.json_response(403, {'error': '只允许本机同源访问'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json_response(415, {'error': '请求必须使用 JSON'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                return self.json_response(413, {'error': '图片总量过大，请缩小图片后重试。'})
            self.connection.settimeout(60)
            body = self.rfile.read(length)
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError('请求必须是 JSON 对象')
            action = urllib.parse.urlsplit(self.path).path
            if action == '/openai-canvas/settings':
                key = data.get('api_key')
                if not isinstance(key, str) or not key.strip() or not key.strip().isascii() or any(c.isspace() for c in key.strip()):
                    raise ValueError('请填写正确的 API Key，不包含空格或换行')
                if api_lock.locked():
                    return self.json_response(409, {'error': '任务运行中，请完成后修改密钥'})
                with file_lock:
                    atomic_json(engine.CONFIG, {'api_key': key.strip()})
                return self.json_response(200, {'ok': True, 'environment_override': bool(os.environ.get('OPENAI_API_KEY'))})
            if action == '/openai-canvas/workflow':
                value = validate_workflow(data)
                with file_lock:
                    atomic_json(DATA / 'workflow.json', value)
                return self.json_response(200, {'ok': True})
            if action == '/openai-canvas/shutdown':
                if api_lock.locked():
                    return self.json_response(409, {'error': '仍在生成，请等待任务完成后退出'})
                self.json_response(200, {'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if action not in {'/openai-canvas/llm', '/openai-canvas/generate'}:
                return self.json_response(404, {'error': '接口不存在'})
            prompt = data.get('prompt')
            images = data.get('images', [])
            model = data.get('model')
            if not isinstance(prompt, str) or not prompt.strip() or not isinstance(images, list) or not isinstance(model, str) or not model.strip():
                raise ValueError('提示词、图片列表或模型名称格式错误')
            labels = reference_labels(data, images)
            effective_prompt = labeled_prompt(prompt, labels)
            if not api_lock.acquire(blocking=False):
                return self.json_response(409, {'error': '另一窗口已有任务运行，请等待完成，避免重复计费。'})
            try:
                if action.endswith('/llm'):
                    system = data.get('system', engine.SYSTEM)
                    if not isinstance(system, str):
                        raise ValueError('System 提示词必须是文本')
                    text = engine.refine(effective_prompt, images, model, system)
                    self.json_response(200, {'text': text})
                else:
                    count = data.get('count', 1)
                    if type(count) is not int or not 1 <= count <= 10:
                        raise ValueError('数量必须是 1–10 的整数')
                    size, quality = data.get('size', '1536x864'), data.get('quality', 'auto')
                    if not isinstance(size, str) or not re.fullmatch(r'\d+x\d+', size) or quality not in ['auto', 'low', 'medium', 'high']:
                        raise ValueError('尺寸或质量参数错误')
                    values = engine.generate(effective_prompt, images, model, size, quality, count)
                    OUTPUT.mkdir(parents=True, exist_ok=True)
                    files = []
                    for value in values:
                        name = uuid.uuid4().hex + '.png'
                        (OUTPUT / name).write_bytes(base64.b64decode(value, validate=True))
                        files.append({'filename': name, 'subfolder': 'OpenAI-Canvas', 'type': 'output'})
                    identifier = uuid.uuid4().hex
                    record = {'id': identifier, 'created_at': datetime.now(timezone.utc).isoformat(),
                              'images': files, 'parameters': {'prompt': prompt, 'model': model,
                              'size': size, 'quality': quality, 'count': count},
                              'references': images, 'labels': labels, 'effective_prompt': effective_prompt}
                    warning = None
                    try:
                        with file_lock:
                            atomic_json(DATA / 'history' / (identifier + '.json'), record)
                    except OSError:
                        warning = '图片已保存，但历史记录写入失败，请检查磁盘空间。'
                    self.json_response(200, {'images': files, 'history_id': identifier if not warning else None, 'warning': warning})
            finally:
                api_lock.release()
        except (ValueError, TypeError) as exc:
            self.json_response(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.json_response(502, {'error': str(exc)})
        except OSError:
            self.json_response(500, {'error': '文件读写或本机连接失败，请检查磁盘空间。若生成中断，请检查输出目录，勿连续重试。'})


def serve(port):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8189)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = serve(port)
            break
        except OSError:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/openai-canvas/status', timeout=1) as response:
                    info = json.load(response)
                if info.get('app') == APP_ID:
                    if not args.no_browser:
                        webbrowser.open(f'http://127.0.0.1:{port}/openai-canvas')
                    print('OpenAI Canvas is already running.')
                    return
            except (OSError, ValueError):
                pass
    if server is None:
        raise RuntimeError('Ports 8189–8198 are busy. Close the previous application and try again.')
    url = f'http://127.0.0.1:{server.server_port}/openai-canvas'
    print(f'OpenAI Canvas {VERSION}\n{url}\nData: {DATA}\nKeep this window open. Ctrl+C stops the server.', flush=True)
    if not args.no_browser:
        threading.Timer(.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
