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
def safe_path(base, path):
    """
    Ensure that a path is within a given base directory.

    Given a base directory and a path, this function
    will return a path that is within the base directory. If the
    resulting path is not within the base directory, this function
    will return None.

    Args:
        base (str): The base directory.
        *parts (str): The path parts to join with the base directory.

    Returns:
        str or None: The resulting path if it is within the base directory,
        otherwise None.
    """
    base = os.path.abspath(base)
    final = os.path.abspath(os.path.join(base, path))
    return final if final.startswith(base) else None


def log(message):
    """
    Logs a message with a timestamp and thread name.

    Args:
        message (str): The message to log.

    """
    thread_name = threading.current_thread().name
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} [Thread-{thread_name[-1]}] {message}")


def generate_id(length=4):
    """
    Generates a random string identifier of a given length.

    Args:
        length (int): The length of the identifier to generate.

    Returns:
        str: A random string identifier of the given length.
    """
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def build_response(status, headers=None, body=b""):
    """
    Builds an HTTP response with a given status code, headers, and body.

    Args:
        status (int): The HTTP status code.
        headers (dict): A dictionary of headers to include in the response.
        body (bytes): The response body.

    Returns:
        bytes: The HTTP response as a byte string.
    """
    headers = headers or {}
    lines = [
        f"HTTP/1.1 {status}",
        f"Date: {datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
        f"Server: Multi-threaded HTTP Server"
    ]
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("")
    return "\r\n".join(lines).encode("utf-8") + body


def parse_request(data):
    """
    Parses an HTTP request byte string into its constituent parts.

    Args:
        data (bytes): The HTTP request byte string to parse.

    Returns:
        tuple: A tuple containing the parsed method, path, version, headers, and body.
            method (str): The HTTP method (e.g. GET, POST, PUT, etc.)
            path (str): The requested path (e.g. /index.html, /api/data, etc.)
            version (str): The HTTP version (e.g. HTTP/1.1)
            headers (dict): A dictionary of headers (e.g. Content-Type, Accept, etc.)
            body (str): The request body (e.g. JSON data, uploaded file, etc.)
    """
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
    """
    Reads a file from the resources directory and returns its contents, content type, and a disposition header.

    Args:
        path (str): The path to the file to read.

    Returns:
        tuple: A tuple containing the file contents, content type, disposition header, and HTTP status code.
            contents (bytes): The contents of the file.
            content_type (str): The content type of the file (e.g. text/html, application/octet-stream, etc.).
            disposition (str): The disposition header of the file (e.g. attachment; filename="example.txt", etc.).
            status (int): The HTTP status code of the response (e.g. 200, 404, 415, etc.).
    """
    if path == "/":
        path = "index.html"
    else:
        path = path.lstrip("/")

    filepath = safe_path(RESOURCE_DIR, path)

    if not filepath:
        return None, None, None, 403, None
        
    if not os.path.isfile(filepath):
        return None, None, None, 404, None

    ext = os.path.splitext(filepath)[1].lower()
    if ext in SUPPORTED_HTML:
        return open(filepath, "rb").read(), "text/html; charset=utf-8", None, 200, ext
    elif ext in SUPPORTED_TEXT + SUPPORTED_IMAGES:
        disposition = f'attachment; filename="{os.path.basename(filepath)}"'
        return open(filepath, "rb").read(), "application/octet-stream", disposition, 200, ext
    else:
        return None, None, None, 415, None


def save_upload(payload):
    """
    Saves a JSON payload to a file in the uploads directory.

    Args:
        payload (dict): The JSON payload to save.

    Returns:
        str: The path to the saved file relative to the uploads directory.
    """

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_id = generate_id()
    filename = f"upload_{timestamp}_{file_id}.json"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return f"/uploads/{filename}"


# --- HTTP Handlers ---
def handle_get(path, conn, keep_alive):
    """
    Handles an HTTP GET request by reading a file from the resources directory
    and sending its contents, content type, and disposition header to the client.

    Args:
        path (str): The path to the file to read.
        conn (socket.socket): The socket object for the client connection.
        keep_alive (bool): Whether to keep the connection alive after sending the response.

    Returns:
        None
    """
    data, ctype, disposition, status, ext = read_file(path)
    if status in [404, 415, 403]:
        conn.sendall(build_response(
            f"{status} {'Not Found' if status == 404 else 'Forbidden' if status == 403 else 'Unsupported Media Type'}",
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
    log(f"Sending {ext.upper()[1:]} file: {os.path.basename(path)} ({len(data)} bytes)")

    if keep_alive:
        headers["Keep-Alive"] = f"timeout={KEEP_ALIVE_TIMEOUT}, max={MAX_PERSISTENT_REQUESTS}"

    conn.sendall(build_response("200 OK", headers, data))
    log(f"Response: 200 OK ({len(data)} bytes transferred)")
    log(f"Connection: {'keep-alive' if keep_alive else 'close'}")


def handle_post(headers, body, conn, keep_alive):
    """
    Handles an HTTP POST request by parsing the JSON body and saving the
    uploaded file to the resources/uploads directory.

    Args:
        headers (dict): The request headers.
        body (str): The request body.
        conn (socket.socket): The socket object for the client connection.
        keep_alive (bool): Whether to keep the connection alive after sending the response.

    Returns:
        None
    """

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
    """
    Validates an HTTP Host header against the server's host and port.

    Args:
        host_header (str): The Host header from the HTTP request.
        server_host (str): The server's host.
        server_port (int): The server's port.

    Returns:
        bool: True if the Host header matches the server's host and port, False otherwise.
    """
    return host_header == f"{server_host}:{server_port}" if host_header else False


# --- Client Handling ---
def serve_client(conn, addr, server_host, server_port):
    """
    Handles a client connection by processing incoming HTTP requests
    and sending back responses.

    Args:
        conn (socket.socket): The socket object for the client connection.
        addr (tuple): The address of the client.
        server_host (str): The server's host.
        server_port (int): The server's port.

    Returns:
        None
    """
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
    """
    Starts an HTTP server that listens on the given host and port.
    The server serves files from the 'resources' directory and
    handles GET and POST requests. The server also supports
    persistent connections and keep-alive requests.

    Args:
        host (str): The host to listen on.
        port (int): The port to listen on.
        max_threads (int): The maximum number of threads to use for
            serving client connections.

    Returns:
        None
    """
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
    """
    Parse command-line arguments using argparse.

    Returns a namespace containing the parsed arguments.

    The available arguments are:

    - port (int, default 8080): the port number to listen on
    - host (str, default 127.0.0.1): the hostname or IP address to listen on
    - max_threads (int, default 10): the maximum number of threads to use in the thread pool

    The parsed arguments are returned as a namespace object. For example, to access the parsed port number, use args.port.
    """
    parser = argparse.ArgumentParser(description="Multi-threaded HTTP Server")
    parser.add_argument("--port", type=int, nargs="?", default=8080)
    parser.add_argument("--host", type=str, nargs="?", default="127.0.0.1")
    parser.add_argument("--max_threads", type=int, nargs="?", default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_server(args.host, args.port, args.max_threads)