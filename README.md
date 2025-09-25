# Multithreaded HTTP Server

This project is a lightweight multi-threaded HTTP/1.1 server built in Python using only the standard library. It supports serving static HTML, text, and image files from a themed resources/ directory, as well as handling JSON file uploads. The server uses a configurable thread pool to process multiple client connections concurrently and includes basic security protections such as path traversal prevention, host header validation, and MIME type enforcement.

---

## Build and Run Instructions

### Requirements

* Python 3.7+
* No external libraries required (uses only Python standard library)

### Steps to Run

1. Clone or download the repository.
2. Ensure the `resources` directory is present in the project root. This directory contains themed resources (HTML pages, text documents, and car-themed images such as `ae_86_front.png`, `ae_86_interior.jpg`, etc.).
3. Run the server:

   ```bash
   python server.py 
   # Defaults to host: 127.0.0.1, port: 8080, max_threads: 10
   ```

   or

   ```bash
   python server.py --host 127.0.0.1 --port 8080 --max_threads 10 
   # Specify the host, port, and max_threads
   ```
4. Open a browser and visit:

   ```
   http://127.0.0.1:8080
   ```

---

## Binary Transfer Implementation

* Files in the `resources` directory are read in **binary mode (`rb`)** to ensure correct transfer of text and media files.
* For `.html` files, the server sets the header `Content-Type: text/html; charset=utf-8` and sends them directly to the client.
* For `.txt` and supported image formats (`.png`, `.jpg`, `.jpeg`), files are sent as raw binary with headers:

  * `Content-Type: application/octet-stream`
  * `Content-Disposition: attachment; filename="<filename>"`
* This ensures the client receives files exactly as stored, preserving integrity (no unintended encoding issues).

---

## Thread Pool Architecture

* The server uses a **ThreadPoolExecutor** for concurrency.
* When a client connects:

  1. If a worker thread is available, the request is immediately assigned.
  2. If all threads are busy, the connection is queued until a thread becomes free.
* Each worker thread handles:

  * Parsing HTTP requests (GET/POST)
  * Serving files or saving uploads
  * Logging activity with timestamps and thread identifiers
* This architecture prevents resource exhaustion and ensures fairness between connections.

---

## Security Measures Implemented

1. **Path Traversal Protection**: Requests are sanitized using `safe_path()` to ensure files are only served from the `resources` directory.
2. **MIME Enforcement**: Only specific file types are supported:

   * `.html`, `.txt`, `.png`, `.jpg`, `.jpeg`
   * Other file types result in `415 Unsupported Media Type`.
3. **Host Header Validation**: Ensures requests match the configured host and port, preventing Host Header attacks.
4. **Restricted Uploads**: Only JSON (`Content-Type: application/json`) is accepted via POST. Uploaded files are saved in the `resources/uploads` directory.
5. **Connection Control**: Limits per-connection requests (`max=100`) and applies a keep-alive timeout (30 seconds) to prevent long-lived idle connections.

---

## Limitations

* **Binary transfer buffering**: Files are currently read fully into memory before sending. Large files could cause high memory usage.
* **Limited MIME types**: Only a small set of file types are supported.
* **Single-directory serving**: All files must reside under the `resources` directory. Serving from multiple roots is not supported.

---

This server provides a **lightweight, themed demonstration** of HTTP functionality, resource serving, concurrency via threads, and basic security measures.
