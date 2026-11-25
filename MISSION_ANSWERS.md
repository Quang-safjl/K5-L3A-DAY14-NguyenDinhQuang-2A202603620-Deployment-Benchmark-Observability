# Day 14 — Mission Answers

**Họ tên:** Nguyễn Đình Quang · **MSSV:** 2A202603620 · **Lớp:** K5-L3A

**Môi trường chạy:** Windows 11 + WSL2 (Ubuntu 26.04), Python 3.11.18, Docker Engine 29.9.3 (Docker Desktop). Ngày chạy: 25/11/2026.

---

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns trong `01-localhost-vs-production/develop/app.py`

| # | Dòng | Anti-pattern | Hậu quả |
|---|---|---|---|
| 1 | 17 | API key hardcode: `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` | Push lên GitHub public là lộ key → bị dùng chùa, tốn tiền |
| 2 | 18 | Credential DB hardcode: `postgresql://admin:password123@localhost:5432/mydb` | Lộ mật khẩu DB; đổi môi trường phải sửa code |
| 3 | 21 | `DEBUG = True` cố định | Production lộ stack trace / thông tin nội bộ |
| 4 | 33–34, 38 | Log bằng `print()`, **in cả API key** (`[DEBUG] Using key: ...`) và nội dung câu hỏi của user | Secret lọt vào log; log không có cấu trúc, không có level, khó tìm kiếm |
| 5 | 42–43 | Không có health check endpoint (`GET /health` → 404) | Platform/LB không biết app chết để restart hoặc ngừng route traffic |
| 6 | 48–53 | `host="localhost"`, `port=8000`, `reload=True` cố định | Không nhận request từ ngoài container; không chạy được trên Railway/Render (PORT do platform cấp); reload tốn tài nguyên |
| 7 | 36 | Không xử lý lỗi khi gọi LLM | LLM lỗi → 500 không kiểm soát |
| 8 | 31 | Không validate / giới hạn độ dài `question` | Prompt quá dài → tốn chi phí, dễ bị lạm dụng |
| 9 | — | Không xử lý SIGTERM / graceful shutdown | Deploy hoặc scale down cắt ngang request đang chạy |
| 10 | 7, 17–22 | `import os` nhưng không đọc config từ env | Vi phạm 12-factor: config phải tách khỏi code |

**Một anti-pattern được bản production sửa (kèm dòng):** API key hardcode ở `develop/app.py` dòng 17 → bản production đọc từ biến môi trường ở `production/config.py` dòng 27 và 32:

```
config.py:27:    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
config.py:32:    api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
```

Tương tự host/port (dòng 17–18 đọc `HOST`, `PORT`) và debug (dòng 19 đọc `DEBUG`, mặc định `false`).

### Exercise 1.2 — Chạy bản develop

```
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
{"detail":"Not Found"}
```

Log server khi nhận request (secret bị in ra log):

```
Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). ...
```

**Có production-ready không?** Không. App trả lời được nhưng: lộ secret trong code và trong log, không có `/health` (404), chỉ bind `localhost:8000` (container/cloud không gọi vào được), bật reload/debug, không graceful shutdown. Lưu ý: bản develop nhận `question` qua query parameter; gửi JSON body bị 422 (`"loc":["query","question"]`).

### Exercise 1.3 — So sánh develop vs production

| Feature | Basic (develop) | Advanced (production) | Why it matters |
|---|---|---|---|
| Config | Hardcode trong code | Đọc từ env vars (`config.py`, `.env` không commit) | Cùng một code/image chạy được nhiều môi trường; đổi config không cần sửa code |
| Secrets | `"sk-hardcoded..."` trong source, in ra log | `os.getenv("OPENAI_API_KEY")`, `AGENT_API_KEY`; cảnh báo nếu thiếu | Không lộ secret khi push code / đọc log |
| Host / Port | `localhost:8000` cố định | `HOST` (mặc định `0.0.0.0`), `PORT` từ env | Cloud cấp PORT động; container phải bind `0.0.0.0` |
| Health check | Không có (`/health` → 404) | `GET /health` (200, uptime, version) + `GET /ready` | Platform/LB phát hiện instance chết để restart và ngừng route |
| Logging | `print()`, lộ secret | Structured JSON logging (`logger.info(json.dumps({...}))`, comment "KHÔNG log secrets") | Dễ parse trong log aggregator (Loki, Datadog...); không log secret |
| Shutdown | Đột ngột | Graceful: `signal.signal(SIGTERM, handle_sigterm)` (dòng 189) + `lifespan` đóng kết nối | Deploy/scale không làm rơi request của user |
| Debug | `DEBUG=True`, `reload=True` | `DEBUG` mặc định `false` | Không lộ thông tin nội bộ, không tốn tài nguyên |

Kết quả chạy bản production:

```
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T13:06:58.118597+00:00"}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

Log khởi động: `WARNING:root:OPENAI_API_KEY not set — using mock LLM` → app không có key thật vẫn chạy với mock và cảnh báo rõ ràng, thay vì hardcode key. Bản production nhận JSON body (gửi query parameter không có body sẽ lỗi 500 vì `request.json()` không parse được body rỗng).

---

## Part 2 — Docker

### Exercise 2.1 — Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (dòng 8) — bản Python đầy đủ (~1 GB, có compiler, header, nhiều tool).
2. **Working directory:** `/app` (`WORKDIR /app`, dòng 11).
3. **Vì sao copy `requirements.txt` trước code?** Để tận dụng Docker layer cache. Layer `pip install` (dòng 17) chỉ bị build lại khi `requirements.txt` thay đổi. Sửa `app.py` chỉ làm mất cache từ dòng `COPY app.py` trở đi → build lại vài giây thay vì cài lại toàn bộ dependencies.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh/tham số mặc định, bị ghi đè hoàn toàn khi truyền lệnh khác vào `docker run <image> <cmd>`. `ENTRYPOINT` là executable cố định của container; tham số của `docker run` được nối vào sau ENTRYPOINT (muốn đổi phải dùng `--entrypoint`). Thường dùng `ENTRYPOINT ["python"]` + `CMD ["app.py"]` để cố định chương trình nhưng cho đổi tham số. Dockerfile này dùng `CMD ["python", "app.py"]` (exec form, process là PID 1 nhận tín hiệu trực tiếp).

### Exercise 2.2 — Build và chạy

```
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -p 8000:8000 my-agent:develop
$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

$ docker images my-agent:develop
IMAGE              ID             DISK USAGE   CONTENT SIZE
my-agent:develop   7773cda2784d       1.67GB          426MB
```

### Exercise 2.3 — Multi-stage build (`02-docker/production/Dockerfile`)

1. **Stage 1 (`builder`, `python:3.11-slim`):** cài build tools (`gcc`, `libpq-dev`), rồi `pip install --user -r requirements.txt` vào `/root/.local`. Stage này chỉ dùng để build, không deploy.
2. **Stage 2 (`runtime`, `python:3.11-slim`):** image sạch, tạo user non-root `appuser`, chỉ copy `/root/.local` (packages đã cài) từ builder + `main.py` + `utils/mock_llm.py`, chạy bằng `USER appuser`, có `HEALTHCHECK` và `CMD uvicorn ... --workers 2`.
3. **Vì sao image nhỏ hơn?** Base `slim` thay cho `python:3.11` full; gcc, header, apt cache, pip cache ở stage 1 bị bỏ lại, không vào image cuối; chỉ giữ đúng những gì cần để chạy.

Kích thước đo trên máy (`docker images | grep my-agent`):

```
my-agent:advanced   298fe6487692   240MB   57.4MB
my-agent:develop    7773cda2784d   1.67GB  426MB
```

| Image | Disk usage | Content size (nén) |
|---|---|---|
| `my-agent:develop` (single-stage, `python:3.11`) | 1 667.8 MB (1 667 784 000 B) | 426 MB |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | 239.8 MB (239 815 430 B) | 57.4 MB |
| **Chênh lệch** | **nhỏ hơn 85.6%** (≈ 7× nhỏ hơn) | **nhỏ hơn 86.5%** |

### Exercise 2.4 — Docker Compose stack (`02-docker/production/docker-compose.yml`)

Chạy với `docker compose -p k5-day14-docker up -d --build` (đã tạo `.env.local`).

**Sơ đồ kiến trúc:**

```
            Client (curl)
                 │  :80 / :443
                 ▼
        ┌──────────────────┐
        │  nginx (alpine)  │  reverse proxy + load balancer
        └────────┬─────────┘  upstream agent_backend → agent:8000
                 │  network "internal" (bridge)
                 ▼
        ┌──────────────────┐
        │ agent (FastAPI)  │  build từ 02-docker/production/Dockerfile (target runtime)
        │ uvicorn :8000    │  không expose port ra ngoài
        └───┬──────────┬───┘
            │          │
  redis://redis:6379   http://qdrant:6333
            ▼          ▼
   ┌────────────┐  ┌────────────────┐
   │ redis:7    │  │ qdrant v1.9.0  │
   │ session,   │  │ vector DB (RAG)│
   │ rate limit │  └────────────────┘
   └────────────┘  volumes: redis_data, qdrant_data
```

**Service nào khởi động?** 4 service: `agent`, `redis`, `qdrant`, `nginx`. Agent chờ redis và qdrant `service_healthy` (`depends_on.condition`) rồi mới start; nginx chờ agent.

**Giao tiếp thế nào?** Tất cả nằm trong network bridge `internal`, gọi nhau bằng tên service (Docker DNS): agent → `redis://redis:6379/0`, `http://qdrant:6333`; nginx → `agent:8000`. Chỉ nginx publish port ra host (80/443); agent, redis, qdrant không lộ ra ngoài.

```
$ docker compose -p k5-day14-docker ps
NAME                       IMAGE                   SERVICE   STATUS                    PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up 11 seconds (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up 10 seconds             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up 22 seconds (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          redis     Up 21 seconds (healthy)   6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
{"status":"ok","uptime_seconds":9.4,"version":"2.0.0","timestamp":"2026-11-25T13:10:06.983828"}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Request đi qua Nginx (header `Server: nginx` và các security header do Nginx thêm), tới agent, trả 200.

---

## Part 3 — Cloud Deployment

Theo ghi chú K5, Part 3 deploy **agent của Part 6** (`06-lab-complete/`), không deploy app mẫu.

### Exercise 3.1 — Deploy Railway

- **Public URL:** https://k5-l3a-day14-nguyendinhquang-2a202603620-deploym-production.up.railway.app
- **Cách deploy:** Railway → Deploy from GitHub repo (auto-deploy mỗi lần push), Root Directory = `06-lab-complete`, build bằng `Dockerfile` multi-stage theo `railway.toml` (`builder = "DOCKERFILE"`, `healthcheckPath = "/health"`).
- **Redis:** Railway managed Redis, agent nối qua `REDIS_URL=${{Redis.REDIS_URL}}`.
- **Env vars đặt trên platform:** `AGENT_API_KEY` (secret), `REDIS_URL`, `RATE_LIMIT_PER_MINUTE=10`, `MONTHLY_BUDGET_USD=10`, `ENVIRONMENT=production`, `LOG_LEVEL=INFO`; `PORT` do Railway cấp.
- **Screenshots:** [`screenshots/dashboard.png`](screenshots/dashboard.png), [`screenshots/running.png`](screenshots/running.png), [`screenshots/test.png`](screenshots/test.png). Chi tiết lệnh test trong [`DEPLOYMENT.md`](DEPLOYMENT.md).

Kết quả test trên URL public:

```
$ curl $URL/health
{"status":"ok","environment":"production"}
$ curl $URL/ready
{"status":"ready","redis":"ok"}
$ curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL/ask -H "Content-Type: application/json" -d '{"question":"hi"}'
401
$ curl -X POST $URL/ask -H "X-API-Key: <redacted>" -H "Content-Type: application/json" -d '{"question":"What is deployment?"}'
{"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."}
$ (12 request liên tiếp)
200 200 200 200 200 200 200 200 200 429 429 429
```

`check_production_ready.py --public-url <URL>` → `Public URL: GET .../health → 200` (xem Part 6).

### Exercise 3.2 — `render.yaml` vs `railway.toml`

| | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
|---|---|---|
| Phạm vi | Cấu hình build/deploy cho **một service** | Mô tả **cả hạ tầng** (Infrastructure as Code): nhiều service + database trong 1 file |
| Build | `[build] builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `dockerfilePath` |
| Health check | `[deploy] healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, số lần retry | Do platform quản lý |
| Redis / DB | Thêm qua dashboard hoặc CLI (`railway add --database redis`), nối bằng biến tham chiếu `${{Redis.REDIS_URL}}` | Khai báo ngay trong file (`type: redis`), nối bằng `fromService ... property: connectionString` |
| Secrets | Đặt bằng `railway variables set` / dashboard, không nằm trong file | Trong file chỉ khai báo tên: `generateValue: true` (Render tự sinh) hoặc `sync: false` (nhập ở dashboard) |
| Định dạng | TOML | YAML |

Tóm lại: `railway.toml` chỉ mô tả cách build/chạy một service, còn hạ tầng đi kèm tạo ở dashboard; `render.yaml` là blueprint khai báo toàn bộ stack (web + Redis + env) để tạo lại được bằng một lần "New → Blueprint".

### Exercise 3.3 — Pipeline Cloud Run (đọc `cloudbuild.yaml` + `service.yaml`)

1. Cloud Build chạy 4 bước nối tiếp: **test** (`pytest tests/` trên `python:3.11-slim`) → **build** image Docker, tag theo commit SHA và `latest` (dùng `latest` làm cache) → **push** lên `gcr.io/$PROJECT_ID/ai-agent` → **deploy** image tag SHA lên Cloud Run.
2. Bước sau chỉ chạy khi bước trước thành công (`waitFor`), nên test fail thì không build/deploy; tag theo SHA giúp biết chính xác version đang chạy và rollback được.
3. Service chạy ở `asia-southeast1`, min 1 / max 10 instance (min 1 để tránh cold start), 1 CPU / 512Mi, concurrency 80 request/instance, timeout 60s.
4. `service.yaml` dùng liveness probe `GET /health` và startup probe `GET /ready`; secret `OPENAI_API_KEY`, `AGENT_API_KEY` lấy từ Secret Manager, không nằm trong image hay repo.
5. File chỉ định nghĩa pipeline; muốn tự chạy khi push lên `main` cần tạo Cloud Build trigger riêng (hoặc chạy tay `gcloud builds submit`).

---

## Part 4 — API Security

### Exercise 4.1 — API key authentication (`04-api-gateway/develop`, chạy với `AGENT_API_KEY=secret-key-123`)

1. **Key được kiểm tra ở đâu?** Trong dependency `verify_api_key` (dòng 39), đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key")` (dòng 36), so với `API_KEY = os.getenv("AGENT_API_KEY", ...)` (dòng 35). Endpoint `/ask` gắn `Depends(verify_api_key)` (dòng 70).
2. **Sai key thì sao?** Thiếu key → **401** `Missing API key`; có key nhưng sai → **403** `Invalid API key`. Request không tới được LLM.
3. **Rotate key thế nào?** Key nằm trong env var nên chỉ cần đổi `AGENT_API_KEY` trên platform (hoặc secret manager) rồi restart/redeploy, không sửa code. Để không gián đoạn: tạm thời chấp nhận cả key cũ và key mới (danh sách key), phát key mới cho client, rồi gỡ key cũ.

```
# Không có key
$ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Sai key
$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

# Đúng key
$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 — JWT authentication (`04-api-gateway/production`)

Luồng JWT (`auth.py`): `POST /auth/token` kiểm tra username/password → `create_token` ký payload `{sub, role, iat, exp}` bằng HS256 với `JWT_SECRET`, hạn 60 phút → client gửi `Authorization: Bearer <token>` → `verify_token` giải mã, kiểm tra chữ ký và hạn (hết hạn → 401, token sai → 403) → lấy `username`, `role` mà không cần tra DB.

```
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username": "student", "password": "demo123"}'
HTTP/1.1 200 OK
{"access_token":"<TOKEN_REDACTED>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."}

# Không có token
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# Có token
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <TOKEN_REDACTED>" -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

### Exercise 4.3 — Rate limiting (`rate_limiter.py`)

1. **Thuật toán:** **Sliding window** (sliding window log): mỗi user có một `deque` timestamp; mỗi request xoá các timestamp cũ hơn 60 giây, nếu số còn lại ≥ limit thì trả 429.
2. **Limit:** user thường **10 request / 60 giây** (`rate_limiter_user`), admin 100 request / 60 giây (`rate_limiter_admin`).
3. **Bypass cho admin:** `app.py` chọn limiter theo role trong JWT: `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`. Muốn bỏ hẳn limit cho admin thì bỏ qua `limiter.check()` khi `role == "admin"` (hoặc tạo limiter rất cao). Role nằm trong JWT đã ký nên client không tự sửa được.

Vòng lặp 20 request với token `student` (đã dùng 1 request ở 4.2 → còn 9):

```
$ for i in {1..20}; do curl -s -o /dev/null -w "%{http_code} " -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"question\": \"Test $i\"}"; done
200 200 200 200 200 200 200 200 200 429 429 429 429 429 429 429 429 429 429 429

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <TOKEN_REDACTED>" -H "Content-Type: application/json" -d '{"question": "Test 21"}'
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795612278
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Hạn chế: limiter này lưu trong memory của process → chạy nhiều instance/worker thì mỗi instance đếm riêng. Ở Part 6 mình chuyển state sang Redis (sorted set + Lua script) để đếm chung và giữ được qua restart.

### Exercise 4.4 — Cost guard

**Cách làm:** mỗi user có một key Redis theo tháng `budget:{user_id}:{YYYY-MM}`. Trước khi gọi LLM, đọc tổng đã tiêu; nếu `đã tiêu + chi phí ước tính > $10` → từ chối (API trả 402). Ngược lại cộng dồn bằng `INCRBYFLOAT`. Key gắn theo tháng nên sang tháng mới là key mới → **tự reset đầu tháng**; đặt TTL 32 ngày để key cũ tự xoá. State nằm trong Redis nên mọi instance thấy cùng một số dư.

```python
from datetime import datetime, timezone
import redis

r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
MONTHLY_BUDGET_USD = 10.0

def check_budget(user_id: str, estimated_cost: float) -> bool:
    """Return True nếu còn budget, False nếu vượt. Budget $10/tháng/user, lưu trong Redis, reset đầu tháng."""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    current = float(r.get(key) or 0)
    if current + estimated_cost > MONTHLY_BUDGET_USD:
        return False
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)   # key theo tháng → tháng mới là key mới (tự reset)
    return True
```

Test với Redis thật (`redis:7-alpine`):

```
spend 4.00 -> True
spend 5.50 -> True
spend 0.60 -> False (9.50 + 0.60 > 10)
spend 0.50 -> True (9.50 + 0.50 = 10)
spend 0.01 -> False
redis budget:student-test:2026-11 = 10 ttl(s) = 2764800
other user -> True
```

Budget được tính riêng từng user (user khác vẫn `True`), TTL = 2 764 800 s = 32 ngày. Bản `cost_guard.py` có sẵn trong `04-api-gateway/production` làm tương tự theo ngày ($1/ngày/user, trả **402**) và thêm global budget $10/ngày (trả **503**), nhưng lưu in-memory. Ở Part 6 (`06-lab-complete/app/cost_guard.py`) mình cài bản Redis: `check_budget()` trả 402 khi vượt `DAILY_BUDGET_USD`/`MONTHLY_BUDGET_USD`, `record_cost()` cộng dồn bằng `INCRBYFLOAT` vào key `cost:daily:{YYYY-MM-DD}` và `cost:monthly:{YYYY-MM}`; grader xác nhận "hết budget → 402".

---

## Part 5 — Scaling & Reliability

### Exercise 5.1 — Health checks (`05-scaling-reliability/develop`)

- `GET /health` (liveness): trả 200 khi process còn sống, kèm uptime, version và check memory (psutil).
- `GET /ready` (readiness): trả 200 khi agent đã khởi động xong (`_is_ready = True`); lúc startup chưa xong hoặc đang shutdown thì trả **503** để load balancer ngừng gửi traffic.

```
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T13:10:26.345915+00:00","checks":{"memory":{"status":"ok","used_percent":24.5}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

**Trường hợp 503:** bản Part 6 (`06-lab-complete`) có `/ready` ping Redis; `check_production_ready.py` dừng Redis và xác nhận:

```
✅ Khi chạy: GET /ready → 200
✅ Khi chạy: Redis mất kết nối → /ready 503 (còn /health vẫn 200)
```

Ý nghĩa: liveness fail → platform restart container; readiness fail → chỉ ngừng route traffic vào instance đó (không restart), vì lỗi nằm ở dependency (Redis) chứ không phải process.

### Exercise 5.2 — Graceful shutdown

App đăng ký handler SIGTERM/SIGINT (`handle_sigterm`), lifespan shutdown đặt `_is_ready = False` rồi chờ request đang xử lý xong (tối đa 30 s), uvicorn chạy với `timeout_graceful_shutdown=30`.

Test: gửi `/ask`, rồi gửi `kill -TERM` ngay khi request đang chạy:

```
$ python app.py &  PID=$!
$ curl -X POST "http://localhost:8000/ask?question=Long%20task" &
$ kill -TERM $PID

# Response của request đang xử lý khi nhận SIGTERM:
HTTP/1.1 200 OK
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
curl exit=0
# process exit code: 0 ; thời gian từ SIGTERM tới khi thoát: 3.13 s
```

Log server:

```
INFO:     Shutting down
INFO:     127.0.0.1:39520 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
INFO 🔄 Graceful shutdown initiated...
INFO ✅ Shutdown complete
INFO:     Finished server process [6931]
INFO Received signal 15 — uvicorn will handle graceful shutdown
```

**Request đang chạy có hoàn thành không?** Có — uvicorn ngừng nhận kết nối mới ("Shutting down") nhưng vẫn trả **200** cho request đang xử lý, rồi chạy lifespan shutdown và thoát với **exit code 0**.

### Exercise 5.3 — Stateless design (`05-scaling-reliability/production/app.py`)

Lịch sử hội thoại không lưu trong biến của process mà lưu trong Redis theo `session_id`:

```python
def save_session(session_id: str, data: dict, ttl_seconds: int = 3600):
    serialized = json.dumps(data)
    if USE_REDIS:
        _redis.setex(f"session:{session_id}", ttl_seconds, serialized)
    else:
        _memory_store[f"session:{session_id}"] = data   # fallback, KHÔNG scale được

def load_session(session_id: str) -> dict:
    if USE_REDIS:
        data = _redis.get(f"session:{session_id}")
        return json.loads(data) if data else {}
    return _memory_store.get(f"session:{session_id}", {})
```

`POST /chat` đọc session → thêm câu hỏi/câu trả lời vào `history` (giữ 20 message gần nhất) → `save_session` với TTL 1 giờ; response có `served_by` (INSTANCE_ID) và `storage` để kiểm chứng.

**Vì sao state in-memory là vấn đề khi scale?** Mỗi instance có bộ nhớ riêng. Load balancer round-robin gửi request 1 của user vào instance A, request 2 vào instance B → B không có lịch sử, agent "quên" cuộc hội thoại. Instance restart/crash/scale down cũng mất toàn bộ session. Khi state nằm ở Redis dùng chung, instance nào cũng phục vụ được bất kỳ request nào → thêm/bớt instance tuỳ ý.

### Exercise 5.4 — Load balancing với Nginx

Chạy: `docker compose -p k5-day14-scaling up -d --build --scale agent=3` (port 8080, endpoint `POST /chat`).

```
$ docker compose -p k5-day14-scaling ps
k5-day14-scaling-agent-1   Up 13 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   Up 12 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   Up 12 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   Up 12 seconds             0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up 23 seconds (healthy)   6379/tcp
```

10 request liên tiếp (rút gọn trường `served_by`):

| Request | served_by | | Request | served_by |
|---|---|---|---|---|
| 1 | instance-fe28e5 | | 6 | instance-0fb227 |
| 2 | instance-98b121 | | 7 | instance-fe28e5 |
| 3 | instance-0fb227 | | 8 | instance-98b121 |
| 4 | instance-fe28e5 | | 9 | instance-0fb227 |
| 5 | instance-98b121 | | 10 | instance-fe28e5 |

`docker compose logs agent`: agent-3 (instance-fe28e5) nhận 4 `POST /chat`, agent-1 (instance-98b121) 3, agent-2 (instance-0fb227) 3. Nginx phân phối **round-robin** đều giữa 3 instance; mọi response đều `"storage":"redis"`. Nginx dùng `resolver 127.0.0.11` (Docker DNS) để thấy các instance, `proxy_next_upstream error timeout http_503` để chuyển sang instance khác khi một instance lỗi, và thêm header `X-Served-By`.

### Exercise 5.5 — Test stateless

```
$ python test_stateless.py
Session ID: fafe91d1-2b09-4ca2-a776-c436dce0fb05
Request 1: [instance-98b121]  Q: What is Docker?
Request 2: [instance-0fb227]  Q: Why do we need containers?
Request 3: [instance-fe28e5]  Q: What is Kubernetes?
Request 4: [instance-98b121]  Q: How does load balancing work?
Request 5: [instance-0fb227]  Q: What is Redis used for?
------------------------------------------------------------
Total requests: 5
Instances used: {'instance-fe28e5', 'instance-98b121', 'instance-0fb227'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

5 câu trong cùng một session được 3 instance khác nhau phục vụ, nhưng history vẫn đủ 10 message (5 user + 5 assistant).

**Thêm: kill một instance giữa cuộc hội thoại** (theo mô tả của `CODE_LAB.md`):

```
session_id=d3fac801-800f-4e57-b3ea-22ed003e8c2e
served_by instance-0fb227 turn 3 storage redis
served_by instance-fe28e5 turn 4 storage redis
served_by instance-98b121 turn 5 storage redis
# docker stop 1 instance
served_by instance-0fb227 turn 6 storage redis
served_by instance-fe28e5 turn 7 storage redis
(request thứ 3 sau khi kill trả về lỗi, không phải JSON)
# history sau khi kill instance:
count 12   (user "Ghi nho: ten toi la Quang" ... turn 5, đủ 6 cặp hỏi–đáp)
```

**Conversation có sống sót sau khi kill instance không?** Có. Sau khi dừng một instance, các request tiếp theo của cùng `session_id` được 2 instance còn lại phục vụ và tiếp tục đúng số turn (6, 7) — lịch sử (12 message) vẫn đầy đủ vì nằm trong Redis, không nằm trong instance đã chết. Có 1 request bị lỗi ngay sau khi kill: Nginx vẫn còn route vào địa chỉ của instance vừa dừng cho tới khi phát hiện nó chết; request lỗi đó không được ghi vào history. Đây là lý do production cần health check ở load balancer và retry phía client.

Dọn dẹp: `docker compose -p k5-day14-scaling down`.

---

## Part 6 — Production Readiness Check

Output đầy đủ của `python check_production_ready.py --public-url https://k5-l3a-day14-nguyendinhquang-2a202603620-deploym-production.up.railway.app` (chạy đầy đủ, có Docker):

```
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 44/44 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một số chi tiết từ output: image 273 MB (< 500 MB), build 28 s; rate limit "429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)" và "restart agent vẫn bị 429" (state trong Redis); cost guard "402 ở request thứ 1" (budget ≈ 0); graceful shutdown "SIGTERM lúc đang có request → request vẫn 200, exit code 0" và "`docker stop` tắt êm (exit code 0, 0.7s)"; public URL "GET .../health → 200".

**Vì sao `/health` 200 nhưng `/ready` 503 khi Redis mất kết nối?** `/health` là liveness: chỉ trả lời câu hỏi "process còn sống không?" — process vẫn sống nên 200, platform không cần restart. `/ready` là readiness: "instance có phục vụ được request không?" — không có Redis thì rate limit và cost guard không hoạt động, nên trả 503 để load balancer tạm ngừng gửi traffic vào instance này cho tới khi Redis trở lại. Nếu gộp chung, Redis chết sẽ làm platform restart liên tục mọi instance mà không giải quyết được gì.

---

## AI log
**Công cụ:** Claude (Anthropic), qua giao diện chat claude.ai
**Thời điểm:** 25/11/2026, khoảng 20:30–20:40 (GMT+7)
**Mục đích:** Hỏi khái niệm, review repo và kiểm tra checklist nộp bài. AI không viết code Part 6 hộ.

### 1. Các câu hỏi đã hỏi

| # | Phần | Câu hỏi |
|---|---|---|
| 1 | Chuẩn bị | Tóm tắt README/CHECKPOINTS: phải nộp gì, mỗi phần bao nhiêu điểm, nên làm theo thứ tự nào trong 4 tiếng |
| 2 | Chuẩn bị | Docker Desktop báo "Virtual Machine Platform is not enabled", tính năng kẹt ở `EnablePending` |
| 3 | Part 1 | 12-factor app là gì, vì sao config phải nằm trong biến môi trường |
| 4 | Part 1 | Các anti-pattern trong `01-localhost-vs-production/develop/app.py` và hậu quả |
| 5 | Part 2 | Vì sao copy `requirements.txt` trước code thì build nhanh hơn; CMD khác ENTRYPOINT thế nào |
| 6 | Part 2 | Multi-stage build giảm image từ 1,67 GB xuống 240 MB bằng cách nào |
| 7 | Part 4 | So sánh API key và JWT; cách rotate key không gây gián đoạn |
| 8 | Part 4 | Sliding window khác token bucket; vì sao rate limiter trong RAM sai khi chạy 2 worker |
| 9 | Part 5 | `/health` khác `/ready`; vì sao Redis chết thì chỉ `/ready` trả 503 |
| 10 | Part 5 | Graceful shutdown trong uvicorn; vì sao tự viết SIGTERM handler có thể làm process không thoát |
| 11 | Part 6 | Review `rate_limiter.py` khi bộ chấm báo ❌ "restart agent vẫn phải bị 429" (nhờ review, không nhờ viết code) |
| 12 | Part 6 | Vì sao `CMD` dạng shell làm `docker stop` mất 10 giây, và cách để uvicorn là PID 1 |
| 13 | Part 6 | Những gì cần kiểm tra khi gặp `ModuleNotFoundError: uvicorn` với user non-root |
| 14 | Part 7 | Vì sao avg latency gây hiểu nhầm; cách đọc p95, p99 |
| 15 | Part 7 | RPS giảm khi concurrency lên 100 có nghĩa là gì |
| 16 | Part 7 | Scale từ 1 lên 3 instance mà p95 không đổi thì nhìn vào đâu để tìm nút thắt |
| 17 | Part 7 | Thí nghiệm E không làm alert nào firing; production phát hiện lỗi chất lượng câu trả lời bằng cách nào |
| 18 | Nộp bài | Đối chiếu checklist nộp bài với repo: còn thiếu gì, có lỗi nào bị trừ điểm không |
| 19 | Nộp bài | Viết mục AI log này |

### 2. AI đã giúp gì

- **Giải thích khái niệm** cho Part 1–5 và Part 7 (câu 3–10, 14–17). Mình dùng làm ý tham khảo và **tự viết lại** câu trả lời trong `MISSION_ANSWERS.md` bằng lời của mình.
- **Review code, không viết hộ** (câu 11–13): AI đọc `rate_limiter.py` và `Dockerfile` trên GitHub rồi chỉ ra chỗ cần kiểm tra. AI không sinh code cho các file trong `06-lab-complete/`.
- **Đọc số liệu của chính mình**: AI dùng số trong `benchmark-results/scale_1_stats.csv` và `BENCHMARK_REPORT.md` để minh họa (avg 216.94 ms, p95 250 ms, p99 1700 ms). Mọi số liệu trong báo cáo đều do mình đo.
- **Kiểm tra trước khi nộp** (câu 18): AI phát hiện `06-lab-complete/app/main.py` trên GitHub vẫn là bản khung (còn TODO, chỉ có route `/ask`) và `MISSION_ANSWERS.md` còn trống nhiều mục.

### 3. Mình đã kiểm chứng và xử lý thế nào

Tôi không nộp nguyên kết quả AI đưa ra mà tự chạy lại và đối chiếu:

- [x] **Code Part 6:** tự chạy `python check_production_ready.py` bản đầy đủ (có Docker) trên máy (WSL2) → **PASS 12/12, 44/44 checks**; chạy thêm `--public-url` với URL Railway → `GET /health → 200`.
- [x] **Bản deploy Railway:** tự gọi URL public bằng curl → `/health` 200, `/ready` 200 (`"redis":"ok"`), `/ask` không key → 401, có key → 200, gọi liên tục → 429 sau 10 request.
- [x] **Số liệu Part 7:** mọi con số trong `BENCHMARK_REPORT.md` lấy từ output tôi tự chạy (`load_test.py`, `run_eval.py`, Locust headless) và khớp với file trong `reports/` và `benchmark-results/`; thời gian alert firing tôi tự ghi khi theo dõi Prometheus.
- [x] **Screenshots:** tự chụp trên máy (Railway, Grafana, Jaeger, Prometheus); trace ID trong log JSON (`b1690f5b...`) tôi tự tra trên Jaeger và khớp với trace.
- [x] **Part 1–5:** các output curl/docker trong `MISSION_ANSWERS.md` là kết quả chạy thật trên máy tôi (script do AI viết, tôi chạy trong Ubuntu); kích thước image (1 667.8 MB → 239.8 MB) đo bằng `docker images`.
- [x] **Bảo mật:** kiểm tra `git log --all -- '*.env' '.env'` không có kết quả; token JWT trong bài đã được che (`<TOKEN_REDACTED>`); `AGENT_API_KEY` chỉ đặt trên Railway, không có trong repo.

### 4. Đánh giá

- **Hữu ích:** giải thích liveness/readiness, PID 1 và tín hiệu SIGTERM, percentile và phân bố hai đỉnh; phát hiện file chưa push trước deadline.
- **Giới hạn:** AI chỉ đọc file qua GitHub, không clone hay chạy được repo, nên mọi kết luận về code đều phải tự chạy lại để kiểm chứng.
