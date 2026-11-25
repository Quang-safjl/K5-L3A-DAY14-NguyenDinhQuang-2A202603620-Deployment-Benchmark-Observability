# Benchmark & Observability Report — Day 14

- **Họ tên:** Nguyễn Đình Quang · **MSSV:** 2A202603620 · **Lớp:** K5-L3A
- **Ngày chạy:** 25/11/2026
- **Môi trường:** Windows 11 + WSL2 (Ubuntu 26.04), Docker Desktop 4.100.1 (Docker Engine 29.9.3), Python 3.11.18 (qua `uv`), mock LLM chạy offline. Docker Desktop dùng giới hạn tài nguyên mặc định.
- **Ghi chú:** stack production chạy với project name mặc định `production` (thư mục), không dùng `-p k5-day14-observability`; kết quả không bị ảnh hưởng.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms (load test) · alert khi > 1 s trong 2 phút | Mock LLM mất ~190 ms/lần gọi; 500 ms cho dư ~2.5× để chịu tải. Ngưỡng alert (1 s) lỏng hơn SLO để tránh báo động giả khi có vài request chậm lẻ tẻ. |
| Error rate `/ask` | ≤ 2% (load test) · alert critical khi > 5% trong 1 phút | Mock LLM có ~1% lỗi 503 nền; 2% cho phép dao động thống kê. > 5% là sự cố thật cần xử lý ngay. |
| Accuracy trên golden dataset | ≥ 80% và không regression so với baseline | Quality gate chặn bản deploy làm agent trả lời sai, điều mà latency/error rate không phát hiện được. |

---

## 2. Performance benchmark (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO p95 ≤ 500 ms |
|---|---|---|---|---|---|---|
| 1 | 3.99 | 190.8 | 222.2 | 1683.2 | 1.00% | ✅ PASS |
| 10 | 35.66 | 195.5 | 225.3 | 1698.0 | 1.33% | ✅ PASS |
| 50 | 103.7 | 202.1 | 298.2 | 1711.1 | 1.00% | ✅ PASS |
| 100 | 57.33 | 539.9 | 3431.1 | 3687.0 | 1.00% | ❌ FAIL |

File: `06-lab-complete/benchmark-observability/develop/reports/load_v2_c{1,10,50,100}.json`

**RPS có tăng tuyến tính không?** Gần tuyến tính đến concurrency 50 (4 → 36 → 104 req/s, ~×9 rồi ×2.9) trong khi p50 gần như không đổi (~190–200 ms) — agent còn dư năng lực, mỗi request chủ yếu chờ LLM (I/O). Ở concurrency 100 hệ thống **bão hoà**: RPS *giảm* còn 57, p50 tăng ~3 lần lên 540 ms, p95 lên 3.4 s. Một process agent không xử lý thêm song song được nên request xếp hàng; thời gian chờ trong hàng đợi cộng vào latency. Throughput tối đa của 1 instance nằm khoảng giữa concurrency 50 và 100.

### 2.2 Tail latency (agent v2, concurrency 10, 300 requests)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | RPS |
|---|---|---|---|---|
| 0 | 191.5 | 218.2 | 224.3 | 51.7 |
| 0.03 (mặc định) | 244.0 | 232.0 | 1680.5 | 37.33 |
| 0.1 | 353.4 | 1692.7 | 1709.0 | 26.08 |

File: `reports/load_v2_slow0.json`, `reports/load_v2_slow003.json`, `reports/load_v2_slow01.json`

**Chỉ số nào nhạy nhất với request chậm?** Percentile đuôi. Với 3% request chậm, chỉ **p99** nhảy (224 → 1680 ms, ×7.5) vì 3% < 5% nên p95 chưa bị ảnh hưởng. Với 10% request chậm, **p95** tăng ×7.8 (218 → 1693 ms) và vi phạm SLO. Trong khi đó **avg** chỉ tăng ×1.3 rồi ×1.85 và **p50 gần như không đổi**.

**Vì sao không nên đặt SLO theo avg?** Avg trộn lẫn đa số request nhanh với thiểu số rất chậm, nên che mất trải nghiệm tệ: ở slow rate 0.1, avg = 353 ms trông "ổn" nhưng 1/10 người dùng phải chờ ~1.7 s. SLO theo p95/p99 mô tả trực tiếp "x% người dùng được phục vụ dưới ngưỡng" và phát hiện được tail latency.

*Ghi chú:* lần chạy slow rate 0.03 có error rate 2.33% (7/300 lỗi 503), vượt SLO 2% do dao động thống kê của mock LLM (~1% lỗi) trên mẫu nhỏ 300 request.

---

## 3. Quality benchmark (develop, `eval/run_eval.py`, 23 câu golden dataset)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100% (23/23)** |
| Avg tokens / câu | 58.7 | 109.0 | 119.9 |
| Tổng cost (USD) | 0.000426 | 0.000760 | 0.000845 |
| Cost / câu đúng (USD) | 0.00042555 | 0.00003619 | 0.00003673 |
| Latency p95 (ms) | 191.8 | 215.0 | 217.5 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (0 regression) |

File: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`

### Câu v2 trả lời sai và cách sửa

| ID | Câu hỏi | Keyword thiếu | Cách sửa |
|---|---|---|---|
| `security-02` | JWT khác gì API key trong xác thực? | `token`, `hết hạn`, `chữ ký` | Thêm entry `["jwt", "json web token"]` vào `KNOWLEDGE_BASE` (`develop/utils/mock_llm.py`) giải thích JWT là token tự chứa claims, có thời điểm hết hạn (`exp`), được ký bằng chữ ký số; so sánh với API key tĩnh. |
| `scaling-03` | Kubernetes HPA scale dựa trên những chỉ số nào? | `cpu`, `memory`, `custom metrics` | Thêm entry `["hpa", "horizontal pod autoscaler", "autoscal"]` mô tả HPA scale theo cpu, memory và custom metrics (qua Prometheus Adapter), external metrics. |

Trước khi sửa, cả hai câu không khớp tài liệu nào nên agent trả câu fallback chung chung (score 0). Sau khi thêm 2 entry và restart v2: 23/23, 2 câu cải thiện, 0 regression.

### Trade-off chất lượng / chi phí / latency giữa v1 và v2

- v2 tốn **gấp ~1.9 lần token** và cost tổng (0.000426 → 0.000760 USD) và chậm hơn ~23 ms ở p95 vì đưa thêm ngữ cảnh retrieval vào prompt và trả lời dài hơn.
- Nhưng **cost trên mỗi câu đúng giảm ~12 lần** (0.000426 → 0.000036 USD) vì v1 gần như trả lời sai hết. Chỉ số đúng để so sánh là cost/câu đúng, không phải cost/request.
- Sửa KB làm tăng thêm ~10% token (109 → 120/câu) và +2.5 ms p95 để đạt 100% — đáng giá.
- v1 nhìn "tốt hơn" trên mọi chỉ số hạ tầng (nhanh hơn, rẻ hơn) nhưng vô dụng về chất lượng → minh chứng cần eval quality gate song song với metrics hạ tầng.

### CI quality gate

Chạy v1 với baseline v2: accuracy 4.3%, **20 câu regression**, quality gate FAIL, **exit code = 1**.

```bash
python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json
echo $?   # 1
```

Exit code ≠ 0 làm job CI fail → PR không merge được (cần bật branch protection "Require status checks to pass"):

```yaml
# .github/workflows/eval-gate.yml
name: eval-quality-gate
on: pull_request
jobs:
  eval:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 06-lab-complete/benchmark-observability/develop
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Start agent under test
        run: |
          AGENT_VERSION=v2 PORT=8002 python app.py &
          sleep 5
      - name: Quality gate (fail = block merge)
        run: python eval/run_eval.py --url http://localhost:8002 --baseline reports/eval_v2.json
```

---

## 4. Observability stack (production)

**Sự cố khi khởi động:** hai container agent bị `Restarting (1)` với lỗi `ModuleNotFoundError: No module named 'uvicorn'`. Nguyên nhân: Dockerfile cài thư viện bằng `pip install --user` rồi copy sang `/home/agent/.local`, nhưng user `agent` được tạo với home `/app` (`useradd -d /app`), nên Python tìm user site-packages ở `/app/.local`. Sửa bằng `ENV PYTHONUSERBASE=/home/agent/.local PATH=/home/agent/.local/bin:$PATH` trước lệnh `COPY --from=builder`. Sau khi agent được tạo lại cần `docker compose restart nginx` để Nginx nhận IP mới (trước đó trả 502).

### 4.1 Screenshot checklist

| Ảnh | File | Nội dung |
|---|---|---|
| ✅ Grafana dashboard khi có tải | `screenshots/grafana-dashboard.png` | Golden signals: 18.6 req/s, error 0.98%, p95 290.7 ms, 2 instances |
| ✅ Trace chậm trong Jaeger | `screenshots/jaeger-slow-trace.png` | Trace 1.7 s, span LLM chiếm gần toàn bộ |
| ✅ Trace lỗi có event `exception` | `screenshots/jaeger-error-trace.png` | `POST /ask` 503, exception "Upstream LLM error: 503" |
| ✅ Prometheus Alerts firing | `screenshots/prometheus-alert-firing.png` | 2 alert cùng FIRING: `LLMCostBurnRateHigh` + `AgentInstanceDown` |

### 4.2 Thí nghiệm phá hệ thống (Locust ~30 users chạy suốt quá trình)

| # | Thay đổi | Alert firing | Thời gian từ thay đổi → firing | Panel lộ rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (critical, value 0.19) | ~1 phút (thay đổi 17:12:05, pending ~17:12:10, `for: 1m` → firing ~17:13:10) | Error rate (Golden Signals) chuyển đỏ; Req/s theo status (503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (warning, p95 = 1.92 s) | ~2 phút 30 giây (thay đổi 17:17:04, pending ~17:17:35, `for: 2m` → firing ~17:19:35) | Latency p50/p95/p99: p95/p99 vọt lên ~1.7–1.9 s, avg tăng ít hơn |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | ~1–2 phút (đã FIRING lúc 17:45, sau thay đổi lúc 17:42:02/17:44:24) | Cost burn rate (USD/giờ) tăng mạnh; LLM latency p95 tăng |
| D | `docker pause production-agent-1` | `AgentInstanceDown` (critical, `up == 0` instance 172.18.0.7:8000) | ~1 phút (1 chu kỳ scrape thất bại + `for: 30s`) | Instances (2 → 1); Prometheus Target health |
| E | `AGENT_VERSION=v1` | **Không có alert** (agent-slo: 3 INACTIVE) | — | Retrieval hit ratio và tokens/s giảm; bảng version chuyển v1 |

Ghi chú:
- **D – pause thay vì stop:** container bị pause vẫn còn trong DNS nhưng không phản hồi, nên scrape thất bại và `up == 0`. Container bị stop biến mất khỏi DNS, Prometheus không còn target đó nên không báo down. Lỗi 504 Locust thấy không hiện trên dashboard agent vì Nginx timeout trước khi agent ghi metric → production cần giám sát thêm ở tầng load balancer và synthetic check từ bên ngoài.
- **Trong ảnh lúc làm E**, `LLMCostBurnRateHigh` vẫn FIRING là dư âm của thí nghiệm C (rule tính trên cửa sổ 5 phút), không phải do E.

**Làm sao phát hiện vấn đề của E trong production khi không có alert?** E làm agent trả lời sai nhưng latency, error rate, instance đều bình thường — observability hạ tầng "mù" với lỗi chất lượng. Cần:
1. Chạy eval định kỳ (synthetic probe) trên golden dataset và alert khi accuracy < 80%.
2. Alert theo tín hiệu chất lượng gián tiếp: retrieval hit ratio, độ dài câu trả lời / tokens trung bình, tỉ lệ câu trả lời fallback.
3. Thu phản hồi người dùng (thumbs up/down) và theo dõi theo `agent_version`.
4. Quality gate trong CI (Mục 3) để chặn v1 trước khi deploy.

### 4.3 Debug bằng trace

**Trace lỗi nối với log**

- **Trace ID:** `b1690f5b1de428b931d087e9b0524637`
- **Tổng thời gian:** 118 ms (`POST /ask` → 503)
- **Span chậm nhất (dưới root):** `agent.run` 114 ms; trong đó `chat mock-llm-small` **90.6 ms (~77% tổng thời gian)** và là span lỗi; `agent.retrieve_context` 19.4 ms (~16%).
- **Log tìm bằng trace ID** (`benchmark-results/log_trace_link.txt`):

```json
{"ts": "2026-11-25T10:34:08.228092+00:00", "level": "INFO", "service": "observable-agent", "instance": "6c91be6962db", "event": "llm_error", "trace_id": "b1690f5b1de428b931d087e9b0524637", "span_id": "da6a0b077769afd5", "request_id": "262284eaed7c", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T10:34:08.228592+00:00", "level": "INFO", "service": "observable-agent", "instance": "6c91be6962db", "event": "http_request", "trace_id": "b1690f5b1de428b931d087e9b0524637", "span_id": "da6a0b077769afd5", "request_id": "262284eaed7c", "method": "POST", "route": "/ask", "status": 503, "ms": 117.0}
```

Log, trace và instance khớp nhau: cùng `trace_id`, cùng `instance=6c91be6962db` (= `service.instance.id` trong Jaeger), thời điểm log (17:34:08.228) = trace start (17:34:08.111) + 117 ms.

**Trace chậm**

- **Trace ID:** `cc260aa…` (lấy đầy đủ từ URL Jaeger)
- **Tổng thời gian:** 1.7 s
- **Span chậm nhất:** `chat mock-llm-small` 1.7 s (**~99.9%**); phần xử lý riêng của agent ~2 ms. → Nút thắt hoàn toàn ở LLM; giảm tail latency phải xử lý ở tầng LLM (timeout + retry, cache, streaming, model nhanh hơn).

---

## 5. Scaling benchmark (production, Locust headless, 100 users, ramp 10/s, 2 phút)

| Instances | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.68 | 190 | 260 | 1700 | 60 / 7061 (0.85%) |
| 3 | 59.56 | 190 | 260 | 1700 | 70 / 7098 (0.99%) |

File: `06-lab-complete/benchmark-observability/production/benchmark-results/scale_1_stats.csv`, `scale_3_stats.csv` (dòng `POST /ask`)

**Scale có cải thiện p95 không? Nút thắt ở đâu?** Không — RPS và mọi percentile gần như giống hệt nhau. Lý do: ở mức tải này hệ thống **chưa bão hoà**. Với 1 instance p95 mới 260 ms (dưới SLO), throughput bị giới hạn bởi bộ tạo tải (100 user Locust có thời gian nghỉ giữa request → ~60 req/s), không phải bởi agent. Latency bị chi phối bởi lời gọi LLM (~190 ms/lần; p99 ~1.7 s do request chậm giả lập) — thêm instance không làm LLM nhanh hơn. Panel LLM latency trên Grafana xác nhận nút thắt nằm ở LLM. Scale ngang chỉ có lợi khi agent đã bão hoà (như concurrency 100 ở Mục 2.1); muốn thấy lợi ích cần tăng tải (ví dụ `-u 500`).

---

## 6. Kết luận

### Ba bài học

1. **Avg nói dối, percentile nói thật.** 10% request chậm làm p95 tăng ~8 lần nhưng avg chỉ tăng ~1.85 lần và p50 không đổi. SLO và alert phải dựa trên p95/p99.
2. **Observability hạ tầng không đo được chất lượng.** Agent v1 nhanh hơn, rẻ hơn, error rate xanh nhưng trả lời sai 96% câu hỏi; thí nghiệm E không kích hoạt alert nào. Cần eval quality gate trong CI và giám sát tín hiệu chất lượng ở production.
3. **Đo trước khi scale.** Tăng từ 1 lên 3 instance không cải thiện gì vì nút thắt là LLM, không phải CPU của agent. Trace cho thấy ~77–99.9% thời gian nằm ở span LLM. Benchmark concurrency cho biết điểm bão hoà thật (~50–100 concurrent/instance).

### Metric và alert sẽ thêm trước khi chạy production thật

- **Chất lượng:** accuracy từ eval định kỳ (alert < 80%), retrieval hit ratio, tỉ lệ câu fallback, feedback người dùng theo `agent_version`.
- **Tầng load balancer / bên ngoài:** tỉ lệ 5xx/504 ở Nginx và synthetic check từ ngoài vào (bắt được lỗi như thí nghiệm D mà metric agent bỏ sót).
- **Bão hoà:** số request đang xử lý (in-flight) và độ dài hàng đợi per instance, CPU/memory container — để autoscale trước khi p95 vỡ.
- **LLM:** p99 latency và error rate theo model/provider, tỉ lệ timeout/retry, cost theo user/API key (kết hợp với cost guard ở Part 6) và alert cost burn rate theo ngày/tháng.
- **SLO burn-rate alert** (multi-window, ví dụ 1h và 6h) thay cho ngưỡng tĩnh để giảm báo động giả.

---

## Phụ lục: Câu hỏi thảo luận

1. **v2 error rate & latency tốt nhưng trả lời sai — observability hạ tầng có phát hiện được không?** Không (xem thí nghiệm E). Cần eval/quality metrics như Mục 4.2.
2. **Vì sao Prometheus dùng pull? Còn phù hợp với Cloud Run scale về 0?** Pull giúp Prometheus kiểm soát nhịp scrape, tự biết target nào chết (`up == 0`), không bị target spam. Với Cloud Run scale về 0, instance có thể không tồn tại lúc scrape và địa chỉ thay đổi liên tục → nên dùng push (OTLP tới collector / Pushgateway) hoặc Managed Prometheus của nền tảng.
3. **Thêm label `user_id` (100.000 user) vào `http_requests_total`?** Bùng nổ cardinality: mỗi tổ hợp label là một time series → hàng trăm nghìn series nhân với route/status, tốn RAM/disk, query chậm, có thể làm sập Prometheus. Thông tin per-user nên để trong log/trace.
4. **Trace mọi request có tốn không? Sampling 10% đánh đổi gì?** Có: tốn CPU, băng thông và lưu trữ. Sampling 10% giảm 90% chi phí nhưng có thể bỏ lỡ trace của request hiếm (lỗi, rất chậm). Nên dùng tail-based sampling: giữ 100% trace lỗi/chậm, sample phần còn lại.
5. **Alert `for: 1m`, đặt `0s` hoặc `30m`?** `for: 0s` báo ngay cả khi chỉ có spike thoáng qua → nhiều báo động giả, alert fatigue. `for: 30m` quá chậm: người dùng đã chịu sự cố 30 phút trước khi có người được báo. `for` cần cân bằng giữa độ nhạy và độ ổn định theo mức độ nghiêm trọng.
