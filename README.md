# Multi-threaded HTTP Server  

A lightweight HTTP/1.1 server written in Python that supports:  
- Serving static HTML, text, and binary files (PNG, JPEG, etc.)  
- File uploads via `POST` requests with JSON payloads  
- Concurrent request handling with a thread pool  
- Basic security protections against path traversal and host header injection  

## 🚀 Build and Run Instructions  

### Requirements
- Python 3.8+  
- No external dependencies (only Python standard library)  

### Run the server
```bash
python server.py
```
### By default, it:

- Binds to 127.0.0.1:8080
- Serves files from the resources/ directory
- Stores uploads in the resources/uploads/ directory

---

## 📦 Binary Transfer Implementation  

- The server uses `open(filepath, "rb")` to read binary files.  
- Files are sent using `conn.sendall()` to ensure the **entire file** is transferred.  
- HTTP headers include:  
  - `Content-Type: application/octet-stream`  
  - `Content-Disposition: attachment; filename="<name>"`  
- Integrity is preserved — no encoding/decoding occurs during transfer.  
- Large files are supported using buffered reads to avoid memory overflow.  

---

## ⚙️ Thread Pool Architecture  

- The server uses `concurrent.futures.ThreadPoolExecutor` with a configurable pool size (default: 10).  
- Each incoming connection is passed to a worker thread.  
- If the pool is saturated, connections are **queued** until a worker is available.  
- Active thread usage is tracked with a counter (protected by a `threading.Lock`).  
- Logging shows real-time pool activity:  

Example:
- [2025-09-20 14:03:10] Thread pool status: 3/10 active
- [2025-09-20 14:03:15] Warning: Thread pool saturated, queuing connection
- [2025-09-20 14:03:17] Connection dequeued, assigned to Thread-4
---
## 🔒 Security Measures Implemented  

1. **Path Traversal Protection**  
   - Uses a `safe_path()` function to prevent access outside the `resources/` directory.  
   - Example: requests like `/../etc/passwd` are blocked.  

2. **Host Header Validation**  
   - Ensures that incoming requests include the correct `Host: host:port`.  
   - Prevents Host header injection attacks.  

3. **MIME Type Enforcement**  
   - Only `.html`, `.txt`, `.png`, `.jpg`, `.jpeg` are supported.  
   - Unsupported extensions return `415 Unsupported Media Type`.  

4. **Graceful Connection Handling**  
   - Timeouts (`KEEP_ALIVE_TIMEOUT`) applied to persistent connections.  
   - Limits maximum requests per connection (`MAX_PERSISTENT_REQUESTS`). 

---

## ⚠️ Known Limitations  

- No HTTPS/TLS support (plaintext only).  
- No directory listing — files must be requested explicitly.  
- Limited MIME type support (HTML, text, images only).  
- Request body parsing is minimal (only JSON POST is supported).  
- Not production-ready: designed for **learning/demo purposes** only.  