import socket
import argparse
import os
import json
import datetime
import random
import string
import threading
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.getcwd()
RESOURCE_DIR = os.path.join(BASE_DIR, "resources")
UPLOAD_DIR = os.path.join(RESOURCE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

SUPPORTED_HTML = [".html"]
SUPPORTED_TEXT = [".txt"]
SUPPORTED_IMAGES = [".png", ".jpg", ".jpeg"]

MAX_PERSISTENT_REQUESTS = 100
KEEP_ALIVE_TIMEOUT = 30


# --- Utility Functions ---
def safe_path(base, *parts):
    base = os.path.abspath(base)
    final = os.path.abspath(os.path.join(base, *parts))
    return final if final.startswith(base) else None


def log(message):
    thread_name = threading.current_thread().name
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} [Thread-{thread_name[-1]}] {message}")


def generate_id(length=4):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def build_response(status, headers=None, body=b""):
    headers = headers or {}
    lines = [
        f"HTTP/1.1 {status}",
        f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
        "Server: Multi-threaded HTTP Server"
    ]
    for k, v in headers.items():
        lines.insert(1, f"{k}: {v}")
    lines.append("")
    lines.append("")
    return "\r\n".join(lines).encode("utf-8") + body


def parse_request(data):
    try:
        text = data.decode("utf-8", errors="ignore")
        lines = text.split("\r\n")
        method, path, version = lines[0].split()
        headers = {}
        idx = 1
        while idx < len(lines) and lines[idx]:
            if ": " in lines[idx]:
                key, value = lines[idx].split(": ", 1)
                headers[key.strip()] = value.strip()
            idx += 1
        body = "\r\n".join(lines[idx + 1:]) if idx + 1 < len(lines) else ""
        return method, path, version, headers, body
    except Exception:
        return None, None, None, {}, ''


# --- File Handling ---
def read_file(path):
    if path == "/":
        path = "index.html"
    else:
        path = path.lstrip("/")

    filepath = safe_path(RESOURCE_DIR, path)
    if not filepath or not os.path.isfile(filepath):
        return None, None, None, 404

    ext = os.path.splitext(filepath)[1].lower()
    if ext in SUPPORTED_HTML:
        return open(filepath, "rb").read(), "text/html; charset=utf-8", None, 200
    elif ext in SUPPORTED_TEXT + SUPPORTED_IMAGES:
        disposition = f'attachment; filename="{os.path.basename(filepath)}"'
        return open(filepath, "rb").read(), "application/octet-stream", disposition, 200
    else:
        return None, None, None, 415


def save_upload(payload):
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_id = generate_id()
    filename = f"upload_{timestamp}_{file_id}.json"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return f"/uploads/{filename}"


# --- HTTP Handlers ---
def handle_get(path, conn, keep_alive):
    data, ctype, disposition, status = read_file(path)
    if status in [404, 415]:
        conn.sendall(build_response(
            f"{status} {'Not Found' if status == 404 else 'Unsupported Media Type'}",
            {"Content-Length": "0", "Connection": "close"}
        ))
        return

    headers = {
        "Content-Type": ctype,
        "Content-Length": str(len(data)),
        "Connection": "keep-alive" if keep_alive else "close"
    }

    if disposition:
        headers["Content-Disposition"] = disposition
        log(f"Sending binary file: {os.path.basename(path)} ({len(data)} bytes)")
    else:
        log(f"Sending HTML file: {os.path.basename(path)} ({len(data)} bytes)")

    if keep_alive:
        headers["Keep-Alive"] = f"timeout={KEEP_ALIVE_TIMEOUT}, max={MAX_PERSISTENT_REQUESTS}"

    conn.sendall(build_response("200 OK", headers, data))
    log(f"Response: 200 OK ({len(data)} bytes transferred)")
    log(f"Connection: {'keep-alive' if keep_alive else 'close'}")


def handle_post(headers, body, conn, keep_alive):
    if headers.get("Content-Type", "").lower() != "application/json":
        conn.sendall(build_response(
            "415 Unsupported Media Type",
            {"Content-Length": "0", "Connection": "close"}
        ))
        return

    try:
        payload = json.loads(body)
    except Exception:
        conn.sendall(build_response("400 Bad Request", {"Content-Length": "0", "Connection": "close"}))
        return

    try:
        relpath = save_upload(payload)
    except Exception:
        conn.sendall(build_response(
            "500 Internal Server Error",
            {"Content-Length": "0", "Connection": "close"}
        ))
        return

    response_body = json.dumps({
        "status": "success",
        "message": "File created successfully",
        "filepath": relpath
    }).encode("utf-8")

    resp_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(response_body)),
        "Connection": "keep-alive" if keep_alive else "close"
    }

    if keep_alive:
        resp_headers["Keep-Alive"] = f"timeout={KEEP_ALIVE_TIMEOUT}, max={MAX_PERSISTENT_REQUESTS}"

    conn.sendall(build_response("201 Created", resp_headers, response_body))
    log(f"Response: 201 Created ({len(response_body)} bytes transferred)")


def validate_host(host_header, server_host, server_port):
    return host_header == f"{server_host}:{server_port}" if host_header else False


# --- Client Handling ---
def serve_client(conn, addr, server_host, server_port):
    log(f"Connection from {addr}")
    persistent_count = 0
    conn.settimeout(KEEP_ALIVE_TIMEOUT)

    while persistent_count < MAX_PERSISTENT_REQUESTS:
        try:
            data = conn.recv(8192)
        except socket.timeout:
            break
        if not data:
            break

        method, path, version, headers, body = parse_request(data)
        log(f"Received: {method} {path} {version}")

        if not method:
            conn.sendall(build_response("400 Bad Request", {"Content-Length": "0"}))
            break

        host_header = headers.get("Host", "")
        if not validate_host(host_header, server_host, server_port):
            log(f"Host validation failed: {host_header}")
            conn.sendall(build_response("403 Forbidden", {"Content-Length": "0", "Connection": "close"}))
            break
        else:
            log(f"Host validation: {host_header}")

        keep_alive = headers.get("Connection", "").lower() == "keep-alive" or version == "HTTP/1.1"
        if method == "GET":
            handle_get(path, conn, keep_alive)
        elif method == "POST":
            handle_post(headers, body, conn, keep_alive)
        else:
            conn.sendall(build_response("405 Method Not Allowed", {"Content-Length": "0"}))
            break

        persistent_count += 1
        if not keep_alive:
            break

    conn.close()


# --- Server ---
def run_server(host, port, max_threads):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(50)
    server.settimeout(1.0)

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP Server started on http://{host}:{port}")
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Thread pool size: {max_threads}")
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Serving files from 'resources' directory")
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Press Ctrl+C to stop the server")
    print()

    pool = ThreadPoolExecutor(max_workers=max_threads)
    connection_queue = []
    active_tasks = 0
    lock = threading.Lock()

    def client_wrapper(conn, addr):
        nonlocal active_tasks
        with lock:
            active_tasks += 1
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Thread pool status: {active_tasks}/{max_threads} active")
        try:
            serve_client(conn, addr, host, port)
        finally:
            with lock:
                active_tasks -= 1
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Thread pool status: {active_tasks}/{max_threads} active")
                # Serve queued connections if any
                if connection_queue:
                    queued_conn, queued_addr = connection_queue.pop(0)
                    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection dequeued, assigned to Thread-{threading.current_thread().name[-1]}")
                    pool.submit(client_wrapper, queued_conn, queued_addr)

    try:
        while True:
            try:
                conn, addr = server.accept()
                with lock:
                    if active_tasks >= max_threads:
                        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Warning: Thread pool saturated, queuing connection")
                        connection_queue.append((conn, addr))
                        continue
                pool.submit(client_wrapper, conn, addr)
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Server shutting down.")
    finally:
        server.close()
        pool.shutdown(wait=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-threaded HTTP Server")
    parser.add_argument("port", type=int, nargs="?", default=8080)
    parser.add_argument("host", type=str, nargs="?", default="127.0.0.1")
    parser.add_argument("max_threads", type=int, nargs="?", default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.host, args.port, args.max_threads)