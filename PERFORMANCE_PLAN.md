# Home Automation Stack — Performance & Observability Improvement Plan

**Target System:** M1 Mac Mini, 8GB RAM, Docker Desktop
**Current Stack:** Mosquitto, Frigate NVR, Home Assistant, Music Assistant, Whisper STT, Piper TTS
**Status:** Memory oversubscribed (~7GB allocated on 8GB system), no centralized logging, no monitoring

---

## Executive Summary

This plan addresses three categories of improvements:

1. **Immediate Wins** (Remove Piper, reduce memory pressure, add database purging)
2. **Medium Complexity** (Safe health checks, observability)
3. **Future Work** (CoreML detection, centralized logging, reverse proxy)

**Total memory freed:** ~128MB (Piper) + potential Frigate reduction
**Time estimate:** 30 minutes (Quick Wins) + 1 hour (Health Checks + Observability)
**Risk profile:** LOW for removal/purging, MEDIUM for health checks, LOW for observability scripts

---

## 1. Remove Piper TTS (Unused Service)

**Status:** User has migrated to Google Translate TTS; Piper container no longer needed
**Risk Level:** LOW
**Time Estimate:** 5 minutes
**Memory Freed:** 128MB limit + ~64MB reservation = 192MB total

### Why Remove It?

- Not in use (Google Translate TTS handles all TTS needs)
- Frees 128MB memory limit (meaningful on 8GB system)
- Simplifies docker-compose.yml and reduces startup time
- Reduces storage footprint (piper-data volume)

### Steps

1. **Stop Piper container:**
   ```bash
   docker-compose stop piper
   ```

2. **Remove Piper from docker-compose.yml:**
   - Delete the entire `piper:` service block (lines 211–239)
   - Delete the `piper-data:` volume entry (line 254)

3. **Clean up the Docker volume:**
   ```bash
   docker volume rm home-automation_piper-data
   ```

4. **Verify removal and restart stack:**
   ```bash
   docker-compose up -d
   docker-compose ps
   # Should show 5 services, not 6
   ```

5. **Update Home Assistant's TTS configuration** (if any references exist):
   - Check `homeassistant/configuration.yaml` for any `tts:` entries pointing to Piper
   - If found, remove or comment out those sections
   - Restart Home Assistant: `docker-compose restart homeassistant`

### Validation

```bash
# Verify Piper is gone
docker ps | grep piper
# Should return nothing

# Check total memory allocation
docker stats --no-stream | awk '{print $6}' | tail -n +2 | paste -sd+ | bc
# Should be ~6.8GB instead of ~7GB
```

---

## 2. Implement Safe Health Checks

**Status:** Previous attempt failed (Mosquitto auth + blocking depends_on)
**Risk Level:** MEDIUM
**Time Estimate:** 45 minutes
**Goal:** Add health checks without blocking container startup

### The Problem

Health checks with `depends_on:condition:service_healthy` create a deadlock:
- Service A's health check fails (e.g., Mosquitto auth issue)
- Service B never starts because it's waiting for A to be healthy
- The whole stack hangs

### The Solution: Lenient Health Checks + service_started

Use `depends_on:condition:service_started` for the dependency chain, and let `restart:unless-stopped` handle recovery. Health checks run asynchronously to report status, not to block startup.

### Health Check Implementation Details

#### 2.1 Mosquitto Health Check

**Challenge:** Mosquitto requires authentication; `mosquitto_sub` alone fails without credentials.

**Solution:** Use mosquitto_sub with environment variables for credentials from the password file.

**Implementation:**

First, verify credentials in `/mosquitto/config/password_file`:
```bash
cat /sessions/stoic-busy-albattani/mnt/home-automation/mosquitto/config/password_file
```

Expected format (hashed):
```
frigate:$6$...hash...
homeassistant:$6$...hash...
```

Add to `mosquitto` service in docker-compose.yml:

```yaml
mosquitto:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "mosquitto_sub", "-h", "127.0.0.1", "-u", "homeassistant", "-P", "your_password_here", "-t", "$SYS/broker/version", "-W", "1"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

**Issue:** Password is hardcoded. Better approach: use environment variable or read from file.

**Recommended approach:** Create a health check script:

```bash
# File: ./mosquitto/health-check.sh
#!/bin/sh
mosquitto_sub -h 127.0.0.1 -u homeassistant -P "${MOSQUITTO_PASSWORD}" \
  -t '$SYS/broker/version' -W 1 >/dev/null 2>&1
exit $?
```

Then in docker-compose.yml:
```yaml
mosquitto:
  # ... existing config ...
  volumes:
    - ./mosquitto/config:/mosquitto/config:ro
    - ./mosquitto/health-check.sh:/mosquitto/health-check.sh:ro
  environment:
    MOSQUITTO_PASSWORD: "read from secrets"
  healthcheck:
    test: ["CMD", "/mosquitto/health-check.sh"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

**Status:** Requires testing — verify `mosquitto_sub` is available in `eclipse-mosquitto:2` image.

---

#### 2.2 Frigate Health Check

**Challenge:** Frigate's web UI runs on port 8971 with HTTPS; curl must support HTTPS.

**Investigation needed:** Check if curl/wget is available in `ghcr.io/blakeblackshear/frigate:stable` image.

**Proposed health check:**

```yaml
frigate:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "curl", "-f", "--insecure", "https://localhost:8971/api/version"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s  # Longer startup: Frigate takes time to boot
```

**If curl is not available**, fallback to `wget`:
```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "--no-check-certificate", "https://localhost:8971/api/version"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**If neither is available**, use netcat (nc):
```yaml
healthcheck:
  test: ["CMD", "nc", "-z", "127.0.0.1", "8971"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**Status:** `nc` is most likely to be available; test all three before settling.

---

#### 2.3 Home Assistant Health Check

**Challenge:** HA's `/api/` endpoints require authentication token.

**Solution:** Use `/api/ping` if available (public), or create a simple health endpoint.

**Proposed health check:**

```yaml
homeassistant:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8123/api/ping"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 60s  # HA takes time to initialize
```

**Alternative:** Use `nc` to check port availability:
```yaml
healthcheck:
  test: ["CMD", "nc", "-z", "127.0.0.1", "8123"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

**Status:** `nc` is safest; test `/api/ping` endpoint availability first.

---

#### 2.4 Music Assistant Health Check

**Challenge:** Need to identify the correct health endpoint.

**Investigation:**
```bash
# Check Music Assistant logs for API docs
docker logs music-assistant 2>&1 | grep -i "health\|ping\|status"

# Try common endpoints
curl http://localhost:8095/api/health
curl http://localhost:8095/api/status
curl http://localhost:8095/ping
curl http://localhost:8095/
```

**Proposed health check (likely):**

```yaml
music-assistant:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "curl", "-f", "http://127.0.0.1:8095/"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
```

**Status:** Requires investigation; check Music Assistant docs or container logs.

---

#### 2.5 Whisper (Wyoming Protocol) Health Check

**Challenge:** Whisper uses the Wyoming protocol (not HTTP). Standard curl won't work.

**Solution:** Use netcat to verify the port is listening.

```yaml
whisper:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "nc", "-z", "127.0.0.1", "10300"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 15s  # Whisper boots quickly
```

**Better alternative:** Create a simple Wyoming protocol test script:

```bash
# File: ./whisper/health-check.sh
#!/bin/sh
# Test Wyoming protocol availability
exec 3<>/dev/tcp/127.0.0.1/10300 && echo "OK" && exec 3>&- && exec 3<&-
```

Then:
```yaml
whisper:
  # ... existing config ...
  volumes:
    - whisper-data:/data
    - ./whisper/health-check.sh:/health-check.sh:ro
  healthcheck:
    test: ["CMD", "/health-check.sh"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 15s
```

**Status:** `nc` is safer and more portable.

---

### 2.6 Safe depends_on Strategy

**Do NOT use `condition:service_healthy` with a blocking depends_on chain.**

Instead, use `service_started` and rely on `restart:unless-stopped`:

```yaml
services:
  frigate:
    depends_on:
      mosquitto:
        condition: service_started  # NOT service_healthy
    restart: unless-stopped
    # ... rest of config ...

  homeassistant:
    depends_on:
      mosquitto:
        condition: service_started
    restart: unless-stopped
    # ... rest of config ...

  music-assistant:
    # No dependencies needed (doesn't use MQTT)
    restart: unless-stopped
    # ... rest of config ...

  whisper:
    # No dependencies needed
    restart: unless-stopped
    # ... rest of config ...
```

**Benefit:**
- Containers start in order (Docker Compose respects `depends_on:service_started`)
- If a service fails, `restart:unless-stopped` will retry it indefinitely
- Health checks run asynchronously (informational only)
- No deadlock if a health check fails

---

### 2.7 Complete Revised docker-compose.yml Snippet

**Apply these changes to the full docker-compose.yml:**

```yaml
mosquitto:
  container_name: mosquitto
  image: eclipse-mosquitto:2
  platform: linux/arm64
  restart: unless-stopped
  security_opt:
    - no-new-privileges:true
  volumes:
    - ./mosquitto/config:/mosquitto/config:ro
  networks:
    - home-automation
  healthcheck:
    test: ["CMD", "mosquitto_sub", "-h", "127.0.0.1", "-u", "homeassistant", "-P", "placeholder", "-t", "$SYS/broker/version", "-W", "1"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
  # ... rest unchanged ...

frigate:
  container_name: frigate
  image: ghcr.io/blakeblackshear/frigate:stable
  platform: linux/arm64
  restart: unless-stopped
  # ... existing config ...
  depends_on:
    mosquitto:
      condition: service_started  # KEY CHANGE
  healthcheck:
    test: ["CMD", "nc", "-z", "127.0.0.1", "8971"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
  # ... rest unchanged ...

homeassistant:
  container_name: homeassistant
  image: ghcr.io/home-assistant/home-assistant:stable
  platform: linux/arm64
  restart: unless-stopped
  # ... existing config ...
  depends_on:
    mosquitto:
      condition: service_started  # KEY CHANGE
  healthcheck:
    test: ["CMD", "nc", "-z", "127.0.0.1", "8123"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 60s
  # ... rest unchanged ...

music-assistant:
  container_name: music-assistant
  image: ghcr.io/music-assistant/server:latest
  platform: linux/arm64
  restart: unless-stopped
  # ... existing config (no depends_on needed) ...
  healthcheck:
    test: ["CMD", "curl", "-f", "http://127.0.0.1:8095/"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s
  # ... rest unchanged ...

whisper:
  container_name: whisper
  image: rhasspy/wyoming-whisper:latest
  platform: linux/arm64
  restart: unless-stopped
  # ... existing config (no depends_on needed) ...
  healthcheck:
    test: ["CMD", "nc", "-z", "127.0.0.1", "10300"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 15s
  # ... rest unchanged ...
```

---

### 2.8 Testing & Validation

**After applying health checks:**

```bash
cd /sessions/stoic-busy-albattani/mnt/home-automation

# Bring stack down, up
docker-compose down
docker-compose up -d

# Wait 2-3 minutes for all services to boot
sleep 120

# Check health status
docker-compose ps
# Column STATUS should show "healthy" or "up" for each service

# Check individual container health
docker inspect mosquitto --format='{{.State.Health.Status}}'
docker inspect frigate --format='{{.State.Health.Status}}'
docker inspect homeassistant --format='{{.State.Health.Status}}'
docker inspect music-assistant --format='{{.State.Health.Status}}'
docker inspect whisper --format='{{.State.Health.Status}}'

# Check logs for any health check failures
docker-compose logs --tail=50 mosquitto | grep -i health
docker-compose logs --tail=50 frigate | grep -i health
```

**Expected outcome:**
- All containers reach "healthy" status within 1-2 minutes
- No error messages in logs related to health checks
- If any health check fails, logs will show the specific command that failed

---

## 3. Memory Optimization

**Status:** Current allocation is ~7GB on 8GB system (87.5% utilized)
**Risk Level:** LOW to MEDIUM
**Time Estimate:** 30 minutes (testing + validation)

### 3.1 Current Memory Allocation Breakdown

| Service | Limit | Reservation | Notes |
|---------|-------|-------------|-------|
| Mosquitto | 64MB | 16MB | Minimal; OK |
| Frigate | 3GB | 1GB | **HIGHEST** — 1 camera, CPU detection |
| Home Assistant | 1GB | 256MB | Baseline + integrations |
| Music Assistant | 768MB | 128MB | Playback + library caching |
| Whisper | 1GB | 256MB | Model in RAM |
| Piper (remove) | 128MB | 64MB | NOT USED |
| **Total** | **~6.8GB** | **~1.7GB** | **Oversubscribed** |

### 3.2 Frigate Memory Reduction

**Current config:**
- Memory limit: 3GB
- CPU cores: 4.0
- Detector: CPU-based (uses 3 threads)
- Shm_size: 256MB (shared memory for FFmpeg)
- Camera: 1 only

**Analysis:**
Frigate with 1 camera, CPU detection, and 5 FPS detection rate should require ~1.5-2GB max. The 3GB allocation has headroom for:
- Detection spike (concurrent person + car detection)
- Snapshot generation
- MQTT publishing overhead

**Recommendation:** Reduce to 2GB limit, keep 1GB reservation.

```yaml
frigate:
  # ... existing config ...
  deploy:
    resources:
      limits:
        memory: 2g          # REDUCED from 3g
        cpus: "4.0"
      reservations:
        memory: 1g          # UNCHANGED
```

**Memory freed:** 1GB (hard limit)

**Risk:** If Frigate hits 2GB during a detection spike, Docker may kill it and restart. Monitor for OOM kills:
```bash
docker inspect frigate | grep -i "oom\|memory"
docker-compose logs frigate | grep -i "memory\|oom"
```

**Fallback:** If OOM kills occur, revert to 2.5GB:
```yaml
memory: 2500m
```

---

### 3.3 Whisper Memory Review

**Current:** 1GB limit, 256MB reservation
**Assessment:** Whisper (tiny.en model) uses ~400-500MB in RAM at runtime. 1GB is adequate with headroom.

**Recommendation:** Keep as-is. Whisper is CPU-intensive but not memory-intensive.

---

### 3.4 Home Assistant Memory Review

**Current:** 1GB limit, 256MB reservation
**Assessment:** HA with typical integrations (MQTT, Frigate, Music Assistant) uses ~600-800MB.

**Recommendation:** Keep as-is. Only reduce if you monitor and confirm it stays <800MB consistently.

---

### 3.5 Music Assistant Memory Review

**Current:** 768MB limit, 128MB reservation
**Assessment:** MASS library indexing (author/artist/album) can spike to 500MB+. 768MB is appropriate.

**Recommendation:** Keep as-is.

---

### 3.6 Total Memory After Optimization

| Service | Limit | Notes |
|---------|-------|-------|
| Mosquitto | 64MB | |
| Frigate | 2GB | REDUCED |
| Home Assistant | 1GB | |
| Music Assistant | 768MB | |
| Whisper | 1GB | |
| **Total** | **~4.8GB** | **~60% utilized** ✓ |

**Benefit:** Frees 2GB, reduces swap usage, improves overall system stability.

---

### 3.7 Validation

```bash
# Monitor memory usage in real-time
docker stats --no-stream | awk 'NR==1 || /[a-z]/ {print $1, $6}'

# Example output:
# CONTAINER        MEM USAGE / LIMIT
# mosquitto        15.2MiB / 64MiB
# frigate          1.8GiB / 2GiB
# homeassistant    720MiB / 1GiB
# music-assistant  450MiB / 768MiB
# whisper          380MiB / 1GiB
```

---

## 4. Whisper Port Security (Wyoming Protocol)

**Status:** Port 10300 currently exposed to host; should be internal-only
**Risk Level:** LOW
**Time Estimate:** 15 minutes (+ verification)
**Dependency:** Must verify Home Assistant's Wyoming integration configuration first

### 4.1 Security Concern

Whisper's Wyoming protocol (port 10300) is currently exposed to the host network:

```yaml
whisper:
  ports:
    - "10300:10300"  # Exposed to 0.0.0.0:10300
```

This allows external access to Whisper if your network is compromised. Since Home Assistant and Whisper are on the same Docker network (`home-automation`), the port can be internal-only.

### 4.2 Pre-Change: Verify Home Assistant Configuration

**Home Assistant MUST use the container name (`whisper:10300`), NOT the host IP (`127.0.0.1:10300`), for this to work.**

**Steps to verify:**

1. Open Home Assistant UI: http://localhost:8123
2. Go to **Settings** → **Devices & Services** → **Integrations**
3. Search for "Wyoming" or "Whisper"
4. Click on the integration
5. Check the host/URL setting

**Expected:** Should show `http://whisper:10300` or similar (using container name)

**If it shows `http://127.0.0.1:10300` or `http://192.168.1.70:10300`:**
- You MUST change it to `http://whisper:10300` before modifying the port mapping
- This requires editing the integration in HA's UI or YAML

**How to change in HA UI:**
1. Go to the Wyoming integration settings
2. Edit the host field
3. Change from `127.0.0.1:10300` to `whisper:10300`
4. Save

**How to change in YAML** (if not using UI):
In `homeassistant/configuration.yaml` or `homeassistant/integrations/wyoming.yaml`:

```yaml
stt:
  - platform: wyoming
    host: whisper  # CHANGE from 127.0.0.1 to whisper (container name)
    port: 10300
```

Then restart Home Assistant:
```bash
docker-compose restart homeassistant
```

---

### 4.3 Apply Port Change

**Once verified Home Assistant uses container name, change the docker-compose.yml:**

```yaml
whisper:
  container_name: whisper
  image: rhasspy/wyoming-whisper:latest
  platform: linux/arm64
  restart: unless-stopped
  security_opt:
    - no-new-privileges:true
  # CHANGE: Replace "ports:" with "expose:"
  expose:
    - "10300"           # Internal-only; Docker network can still access
  # OLD (REMOVE THIS):
  # ports:
  #   - "10300:10300"
  volumes:
    - whisper-data:/data
  # ... rest unchanged ...
```

**Difference:**
- `ports: ["10300:10300"]` → Container port 10300 exposed to host (0.0.0.0:10300)
- `expose: ["10300"]` → Container port 10300 only accessible within Docker network

---

### 4.4 Validation

```bash
# Restart stack
docker-compose down
docker-compose up -d

# Verify Whisper is running
docker ps | grep whisper

# Attempt to connect from host (should fail)
nc -z 127.0.0.1 10300
# Expected: connection timeout or refused

# Verify HA can still reach Whisper (should work)
docker-compose exec homeassistant nc -z whisper 10300
# Expected: connection successful

# Check HA logs for Wyoming connection
docker-compose logs homeassistant | grep -i "wyoming\|whisper" | tail -20
```

**Expected result:**
- Whisper is running
- Connections from host fail (port not exposed)
- HA can still connect (uses Docker network)
- HA logs show successful Wyoming connection

---

## 5. Database Purging Configuration

**Status:** Currently no automatic purging (database grows indefinitely)
**Risk Level:** LOW
**Time Estimate:** 5 minutes
**Impact:** Reduces Home Assistant's database size + improves startup time

### 5.1 Why Purge?

Home Assistant's `recorder` integration stores:
- State changes (every attribute change)
- Events (automations, scripts, etc.)
- Statistics

Over time, the database (`homeassistant/home-assistant_v2.db`) grows to gigabytes, causing:
- Slower HA startup
- Slower UI when viewing history
- Wasted disk space

### 5.2 Configuration

Add to `homeassistant/configuration.yaml`:

```yaml
# ── Database Retention ─────────────────────────────────────────────────
recorder:
  purge_keep_days: 30        # Keep last 30 days of data
  commit_interval: 1         # Commit changes every 1 second (safer)
  auto_purge: true           # Automatic purge enabled (default)
  auto_purge_delay: 0        # Purge immediately after retention reached
```

**Explanation:**
- `purge_keep_days: 30` → Only keep data from the last 30 days
- `commit_interval: 1` → Commit DB changes every 1 second (safer for Raspberry Pi-level hardware)
- `auto_purge: true` → Run purge job daily
- `auto_purge_delay: 0` → No delay; purge as soon as retention window is exceeded

### 5.3 Alternative (More Aggressive)

If disk space is critical, reduce to 14 days:

```yaml
recorder:
  purge_keep_days: 14
  commit_interval: 1
```

---

### 5.4 Apply Configuration

```bash
# Edit configuration.yaml
# Add the recorder section above (or uncomment if it exists)

# Verify YAML syntax
docker-compose exec homeassistant python3 -c "
import yaml
with open('/config/configuration.yaml') as f:
    yaml.safe_load(f)
print('✓ YAML syntax OK')
"

# Restart Home Assistant
docker-compose restart homeassistant

# Check logs for recorder initialization
docker-compose logs homeassistant | grep -i "recorder" | head -10
```

**Expected log output:**
```
homeassistant  | 2026-03-09 22:30:00.123 INFO (Recorder) [homeassistant.components.recorder]
homeassistant  | Database recorder configured to purge data every 30 days
```

---

### 5.5 Manual Purge (Optional)

If you want to manually purge old data immediately:

```bash
# Access HA service
docker-compose exec homeassistant python3 << 'EOF'
from homeassistant.components.recorder import purge
import asyncio
asyncio.run(purge.purge_old_data(hass, 30, repack=False))
print("✓ Manual purge complete")
EOF
```

Or use the Home Assistant UI:
1. Settings → Developer Tools → Statistics
2. Click "Purge" button

---

## 6. Observability Quick Wins

**Status:** No centralized monitoring or logging
**Risk Level:** LOW
**Time Estimate:** 30 minutes
**Goal:** Simple health checks without adding heavy services (Prometheus, Grafana, Loki)

### 6.1 Simple Docker Health Check Script

Create a shell script that monitors container health and displays output:

**File:** `./monitoring/health-check.sh`

```bash
#!/bin/bash
# Simple health check script for home automation stack
# Run via cron: */5 * * * * /path/to/health-check.sh >> /tmp/ha-health.log 2>&1

set -e
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "=== Health Check: $TIMESTAMP ==="

# Check if Docker daemon is accessible
if ! docker ps >/dev/null 2>&1; then
    echo "ERROR: Docker daemon not accessible"
    exit 1
fi

# Define services to monitor
SERVICES=("mosquitto" "frigate" "homeassistant" "music-assistant" "whisper")

# Array to track failed services
FAILED=()

for service in "${SERVICES[@]}"; do
    # Get container status
    STATUS=$(docker inspect "$service" --format='{{.State.Status}}' 2>/dev/null || echo "missing")

    if [ "$STATUS" == "running" ]; then
        # Check health status (if health check is configured)
        HEALTH=$(docker inspect "$service" --format='{{.State.Health.Status}}' 2>/dev/null || echo "none")

        if [ "$HEALTH" == "healthy" ] || [ "$HEALTH" == "none" ]; then
            echo "✓ $service: running ($HEALTH)"
        else
            echo "⚠ $service: running but unhealthy ($HEALTH)"
            FAILED+=("$service")
        fi
    else
        echo "✗ $service: $STATUS"
        FAILED+=("$service")
    fi
done

# Check system resources
DOCKER_MEMORY=$(docker stats --no-stream --format "table {{.MemUsage}}" | tail -n +2 | paste -sd+ | bc 2>/dev/null || echo "N/A")
echo ""
echo "System Resources:"
echo "  Docker Total Memory: $DOCKER_MEMORY"

# Check Frigate disk usage (recording storage)
FRIGATE_DISK=$(docker exec frigate du -sh /media/frigate 2>/dev/null | awk '{print $1}' || echo "N/A")
echo "  Frigate Storage: $FRIGATE_DISK"

# Report
echo ""
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "✓ All services healthy"
    exit 0
else
    echo "✗ Failed services: ${FAILED[@]}"
    exit 1
fi
```

**Usage:**

```bash
# Make executable
chmod +x ./monitoring/health-check.sh

# Run manually
./monitoring/health-check.sh

# Add to cron for automatic monitoring every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * cd /sessions/stoic-busy-albattani/mnt/home-automation && ./monitoring/health-check.sh") | crontab -

# View recent health checks
tail -50 /tmp/ha-health.log
```

---

### 6.2 Real-Time Event Monitoring

Use `docker events` to watch container lifecycle events:

```bash
# Watch all Docker events for your home automation stack
docker events --filter 'network=home-automation' --format '{{.Time|json}} {{.Type}} {{.Action}} {{.Actor.Attributes.name}}'

# Example output:
# 2026-03-09T22:30:15.123456789Z container start mosquitto
# 2026-03-09T22:30:20.987654321Z container health_status: healthy
```

**Useful filters:**
```bash
# Only container events
docker events --filter type=container

# Only failed health checks
docker events --filter 'event=health_status' | grep unhealthy

# Only specific service
docker events --filter 'container=frigate'
```

---

### 6.3 Home Assistant Built-In System Monitor

Home Assistant has a built-in **System Monitor** integration that tracks Docker resource usage.

**Enable in Home Assistant:**

1. Go to **Settings** → **Devices & Services** → **Integrations**
2. Search for "System Monitor"
3. Click "Create Integration"
4. It should auto-detect your system

**Exposed sensors:**
- CPU usage %
- Memory available / used
- Disk available / used
- Network in/out

**Display on Dashboard:**
Add a card to visualize these metrics:

```yaml
type: grid
cards:
  - type: gauge
    entity: sensor.processor_use
    min: 0
    max: 100
  - type: gauge
    entity: sensor.memory_use_percent
    min: 0
    max: 100
  - type: entity
    entity: sensor.disk_use_percent
```

---

### 6.4 Frigate-Specific Monitoring

Frigate exposes Prometheus metrics on port 8971:

```bash
# Get Frigate metrics (requires authentication if HA is configured)
curl -s http://localhost:8971/api/stats | jq .

# Example output:
# {
#   "front_window": {
#     "camera_fps": 5.0,
#     "detection_fps": 2.5,
#     "process_fps": 3.0,
#     "skipped_fps": 0.0,
#     "objects": {
#       "person": 0,
#       "car": 0
#     }
#   }
# }
```

**Add to Home Assistant** via REST Sensor:

```yaml
# In homeassistant/configuration.yaml or separate file
rest:
  - resource: http://frigate:8971/api/stats
    scan_interval: 30
    sensor:
      - name: "Frigate CPU Usage"
        value_template: "{{ value_json['front_window'].process_fps }}"
        unit_of_measurement: "FPS"
```

---

### 6.5 Disk Usage Monitoring (Critical for Frigate)

Create a cron job to monitor Frigate's recording storage (currently 217GB):

**File:** `./monitoring/frigate-disk-check.sh`

```bash
#!/bin/bash
# Monitor Frigate disk usage and alert if near capacity

FRIGATE_PATH="./frigate/storage"
THRESHOLD_PERCENT=85
THRESHOLD_GB=50

# Get disk usage
USAGE=$(du -sh "$FRIGATE_PATH" | awk '{print $1}')
USAGE_BYTES=$(du -sb "$FRIGATE_PATH" | awk '{print $1}')

# Get total filesystem size
TOTAL=$(df -h "$FRIGATE_PATH" | tail -1 | awk '{print $2}')
TOTAL_BYTES=$(df -B1 "$FRIGATE_PATH" | tail -1 | awk '{print $2}')

# Calculate percentage
PERCENT=$((USAGE_BYTES * 100 / TOTAL_BYTES))

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$PERCENT" -ge "$THRESHOLD_PERCENT" ]; then
    echo "[$TIMESTAMP] ALERT: Frigate disk usage at ${PERCENT}% ($USAGE / $TOTAL)"
    # Optional: send notification to Home Assistant, email, etc.
elif [ "${USAGE_BYTES##*[!0-9]}" -ge "$((THRESHOLD_GB * 1024 * 1024 * 1024))" ]; then
    echo "[$TIMESTAMP] WARNING: Frigate storage exceeds ${THRESHOLD_GB}GB ($USAGE)"
else
    echo "[$TIMESTAMP] OK: Frigate disk usage at ${PERCENT}% ($USAGE / $TOTAL)"
fi
```

**Add to cron (daily):**

```bash
chmod +x ./monitoring/frigate-disk-check.sh

# Run at 06:00 AM daily
(crontab -l 2>/dev/null; echo "0 6 * * * cd /sessions/stoic-busy-albattani/mnt/home-automation && ./monitoring/frigate-disk-check.sh") | crontab -
```

---

### 6.6 Centralized Logging (Optional)

Currently, each container logs to `json-file` driver with log rotation:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "50m"
    max-file: "5"
```

**Access logs:**

```bash
# View logs from all services
docker-compose logs --follow

# View logs from specific service
docker-compose logs frigate --tail 50

# Follow Mosquitto logs in real-time
docker-compose logs mosquitto -f

# Search logs
docker-compose logs | grep "ERROR\|WARNING"
```

**If you want centralized logging (future):**
- **Simple:** Use `docker logs` aggregation (above) with shell scripts
- **Medium:** Add Loki + Promtail (similar to Prometheus but for logs)
- **Advanced:** Use ELK stack (Elasticsearch, Logstash, Kibana) — overkill for single M1 Mac

---

## 7. Whisper/Piper Port Security — Detailed Walkthrough

**Consolidated with Section 4 above.** Key points:

1. Verify HA's Wyoming config uses container name (`whisper:10300`)
2. Change `ports: ["10300:10300"]` to `expose: ["10300"]`
3. Test internal connectivity
4. External access to Whisper will be blocked (only HA can access)

---

## 8. Music Assistant Hardcoded IP Issue

**Status:** MASS_BASE_URL hardcoded to `192.168.1.70:8095`
**Risk Level:** MEDIUM
**Impact:** If your IP address changes, Music Assistant breaks

### 8.1 The Problem

In `docker-compose.yml`:
```yaml
environment:
  MASS_BASE_URL: http://192.168.1.70:8095
```

In `music-assistant/settings.json`:
```json
{
  "base_url": "http://192.168.1.70:8095",
  "publish_ip": "192.168.1.70"
}
```

If the M1 Mac's IP changes (e.g., DHCP reassignment), Music Assistant will become unreachable.

### 8.2 Solution

**Option 1: Use Docker DNS (Recommended)**

Change MASS_BASE_URL to use Docker internal DNS:

```yaml
music-assistant:
  # ... existing config ...
  environment:
    TZ: America/New_York
    MASS_BASE_URL: http://music-assistant:8095  # Use container name, not IP
```

**Issue:** External players (Spotify Connect, etc.) still need a valid IP/hostname.

**Option 2: Use a Fixed Local Hostname**

Set up a local `.local` mDNS hostname:

1. On your Mac, configure Avahi or Bonjour: `home-automation.local`
2. Update MASS_BASE_URL:
   ```yaml
   environment:
     MASS_BASE_URL: http://home-automation.local:8095
   ```

**Issue:** Requires local network configuration; fragile across network changes.

**Option 3: Bind to All Interfaces + Use Bridge Network IP**

This is complex; not recommended for simplicity.

### 8.3 Recommended Action

**For now:** Keep the hardcoded IP but document it in a README:

```markdown
# Network Configuration

Music Assistant is configured with a static IP: `192.168.1.70`

If your M1 Mac's IP changes:
1. Update `MASS_BASE_URL` in docker-compose.yml
2. Update `base_url` and `publish_ip` in `music-assistant/settings.json`
3. Restart: `docker-compose restart music-assistant`
```

**Future improvement:** Use Docker DNS or mDNS hostname resolution when Music Assistant supports it.

---

## 8. Voice Pipeline Optimization (Completed 2026-03-17)

**Status:** ✅ Implemented and verified. Ongoing monitoring via voice-bench.

---

### 8.1 Background & Root Cause

The ESPHome Voice PE satellite uses VAD (Voice Activity Detection) to decide when the user has finished speaking. It records until it detects silence. If there is ambient noise in the room (TV, speaker bleed, HVAC), the VAD window extends far beyond the user's speech — resulting in Whisper receiving 15–60 seconds of audio instead of 2–3 seconds.

**Key insight from log analysis:** Music commands were always fast (~3s) while general queries were slow (15–60s). The difference: music commands trigger Music Assistant's auto-pause, which mutes the amp. With the speaker muted, the mic hears silence → short VAD window → fast STT. Non-music commands left the amp live.

**Conclusion:** Always mute the amp on wake word, regardless of whether music is playing.

**TV noise caveat:** The in-room TV is a separate physical audio source. Amp mute has no effect on TV audio. TV must be muted/off during voice commands for best performance.

---

### 8.2 STT Model: distil-whisper-large-v3

Previous model: `mlx-community/whisper-large-v3-turbo`
Current model: `mlx-community/distil-whisper-large-v3`

`distil-whisper-large-v3` is a distilled version of Whisper large-v3 that runs ~2× faster with minimal accuracy loss for short home-automation commands. It is specified in the LaunchAgent plist at `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist`.

**Models tested and rejected:**
- `whisper-small.en` — too inaccurate for short/ambiguous commands (2026-03-15)
- `whisper-large-v3-turbo` — acceptable, superseded by distil-large-v3

---

### 8.3 Voice Pipeline Automations (`homeassistant/automations.yaml`)

Four automations manage the amp and Music Assistant around each voice command:

| # | ID | Trigger | Action |
|---|---|---|---|
| 1 | `voice_pause_media_on_wake` | Satellite `idle → listening` | Always mute amp. If MA was playing: pause it + set `input_boolean.voice_paused_music`. |
| 2 | `voice_unmute_after_listening` | Satellite leaves `listening` | Unmute amp. Safe window: mic is done, TTS hasn't started yet. |
| 3 | `voice_resume_media_on_done` | Satellite → `idle` | Belt-and-suspenders unmute. If `voice_paused_music` is on and MA is still paused: resume after 1s delay. |
| 4 | `voice_premute_when_idle` | MA → idle/paused/off **or** amp becomes unmuted | Re-mute amp if no music playing and no voice command in progress. Eliminates the cold-start slow path after automation reloads. |

**Why the unmute fires on `from: "listening"`** rather than `to: "idle"`: the `idle` state fires *after* TTS completes. If we wait until then to unmute, TTS audio is silenced. Unmuting when the satellite leaves `listening` gives a clean window: mic is done recording, HA is processing, TTS hasn't started yet.

**Cold-start problem and fix:** HA automation triggers only fire on state *transitions*, not on the current state at load time. After an automation reload, if the amp was already unmuted and MA was already stopped, automation #4 would never fire — leaving the amp unmuted for the first command. The fix (automation #4's second trigger) watches for the amp's `is_volume_muted` attribute transitioning to `false` and immediately re-mutes if conditions are met.

---

### 8.4 Intent Scripts (`homeassistant/configuration.yaml`)

All 12 music-playing intent scripts follow this pattern to handle Music Assistant being unavailable after HA restart (MA takes ~1m45s to become ready):

```yaml
action:
  # Wait up to 5s for MA to become available
  - wait_template: "{{ states('media_player.naboo_media_player') not in ['unknown', 'unavailable'] }}"
    timeout:
      seconds: 5
    continue_on_timeout: true
  # Explicitly unmute before playing (belt-and-suspenders)
  - action: media_player.volume_mute
    target:
      entity_id: media_player.home_assistant_voice_0a3a76_media_player
    data:
      is_volume_muted: false
  - action: music_assistant.play_media
    ...
```

The explicit unmute before `play_media` handles the edge case where the user's "play music" command fires during the brief period between automation #1 (mute) and automation #2 (unmute-after-listening), or after the pre-mute automation re-muted the amp.

---

### 8.5 Measured Performance (2026-03-17, distil-whisper-large-v3, TV off)

| Command | Before | After |
|---|---|---|
| "What time is it?" | 8–60s | **2.85s** |
| "What's the weather?" | 40–60s | **3.8s** |
| "What time is it?" after music | 23s | **5.2s** |
| Radio/music commands | 3–13s | **3.0–3.3s** |

All timings verified from `wyoming-mlx-whisper/log/whisper.err` (`took X.XXX seconds` entries).

---

### 8.6 Voice-Bench: Continuous Performance Monitoring

A lightweight benchmarking daemon (`voice-bench/`) logs every voice command's per-hop timing to a CSV file and serves a dashboard at `http://localhost:7700`.

**Architecture:**
- Python async daemon (~500 lines, ~2MB RAM idle, zero CPU when idle)
- Subscribes to HA WebSocket for satellite state transitions (`idle → listening → processing → responding → idle`)
- Tails `wyoming-mlx-whisper/log/whisper.err` for STT duration and transcribed text
- Correlates both event streams into a single row per command
- Serves dashboard via aiohttp (built-in HTTP server, no external dependencies beyond pip packages)

**Data captured per command:**

| Column | Source | Notes |
|---|---|---|
| `listening_ms` | HA satellite state | Full recording + STT window (satellite in "listening") |
| `stt_ms` | whisper.err | Pure wyoming handler time (audio receipt + transcription) |
| `processing_ms` | HA satellite state | HA intent processing ("processing" state duration) |
| `responding_ms` | HA satellite state | TTS playback ("responding" state duration) |
| `total_ms` | Computed | listening_start to pipeline_end |
| `amp_muted_at_wake` | HA entity snapshot | Whether amp was already muted when wake word fired |
| `music_was_playing` | HA entity snapshot | Whether MA was playing at wake time |
| `config_tag` | `config.yaml` | Manual label for A/B comparison (e.g. "baseline-v1") |
| `whisper_model` | LaunchAgent plist | Auto-detected from `--model` argument |

**Dashboard features:**
- Pipeline bar chart: Recording (blue) → STT (amber) → Processing (orange) → Response (green) — widths proportional to time
- Speed color coding: green < 4s, amber < 8s, red ≥ 8s
- Filter by command type: time, weather, radio, music, home, other
- ⚠ warning badge when amp was unmuted at wake (ambient noise risk)
- Per-entry star rating (1–5), persisted to `data/ratings.json`
- Auto-refreshes every 10 seconds
- Stats summary: count, avg total, avg STT, fast %, slow %

**Files:**

```
voice-bench/
  voice_bench.py       # Main daemon (HA websocket + log tailer + HTTP server)
  index.html           # Dashboard frontend
  config.yaml          # HA token, entity IDs, whisper paths, config tag
  requirements.txt     # websockets, aiohttp, pyyaml
  run.sh               # Creates venv, installs deps, starts daemon
  seed_from_log.py     # One-time import of whisper.err history into CSV
  data/
    voice_bench.csv    # Append-only log, one row per command
    ratings.json       # Star ratings keyed by entry ID
  log/
    bench.log
    bench.err
~/Library/LaunchAgents/com.voice-bench.plist  # Auto-start on login
```

**Setup:**

```bash
# 1. Add HA long-lived access token to voice-bench/config.yaml
#    (HA → profile → Security → Long-Lived Access Tokens)

# 2. (Optional) Seed historical data from existing whisper.err
python3 voice-bench/seed_from_log.py

# 3. Test run
./voice-bench/run.sh

# 4. Install as LaunchAgent
launchctl load ~/Library/LaunchAgents/com.voice-bench.plist
```

**A/B testing workflow:** Before changing a setting, update `tag:` in `voice-bench/config.yaml` to a descriptive label (e.g. `"turbo-model"`). After testing, change the tag again. Filter or group by `config_tag` in the CSV to compare.

---

## 9. Future Considerations (Lower Priority)

### 9.1 Frigate CoreML Detection

**Status:** Currently commented out (CPU detection in use)
**Benefit:** Faster person/car detection using Apple Neural Engine
**Risk:** May require CoreML model optimization

**Implementation (when ready):**

```yaml
# In frigate/config.yml
detectors:
  cpu1:
    type: cpu
    num_threads: 1        # Reduce CPU threads if CoreML is enabled
  apple:
    type: coreml
    model:
      path: /models/yolov8n-coreml/model.mlmodel
```

**Research needed:**
- Verify CoreML model compatibility with M1 Mac Docker
- Test performance improvement vs. CPU-only detection
- Measure power/thermal impact

---

### 9.2 Centralized Logging with Loki

**Status:** Not implemented (json-file driver currently in use)
**Benefit:** Search, filter, and visualize logs from all services in one place
**Trade-off:** Adds complexity + storage overhead

**When to implement:**
- If you need to search logs across services
- If you want historical log retention beyond 5 files
- If you're scaling to multiple machines

**Alternative (simpler):**
Continue using `docker logs` CLI with shell scripts (Section 6).

---

### 9.3 Reverse Proxy with TLS

**Status:** Not implemented; services accessible over HTTP
**Benefit:** Single entry point, HTTPS encryption, cleaner URLs
**Trade-off:** Adds Nginx/Traefik container, more configuration

**When to implement:**
- If you expose your home automation to the internet
- If you want to use automatic HTTPS (Let's Encrypt)
- If you want to combine all services under one domain

**Simple option:** Nginx Reverse Proxy
```yaml
nginx:
  image: nginx:latest
  ports:
    - "443:443"
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - ./certs:/etc/nginx/certs:ro
```

---

## 10. Implementation Checklist

### Phase 1: Quick Wins (30 minutes)

- [ ] **Remove Piper**
  - [ ] Delete Piper service from docker-compose.yml
  - [ ] Delete piper-data volume reference
  - [ ] Run `docker volume rm home-automation_piper-data`
  - [ ] Restart stack: `docker-compose up -d`
  - [ ] Verify only 5 services running

- [ ] **Add Database Purging**
  - [ ] Add `recorder:` section to homeassistant/configuration.yaml
  - [ ] Set `purge_keep_days: 30`
  - [ ] Restart Home Assistant
  - [ ] Verify in logs: "Database recorder configured..."

- [ ] **Reduce Frigate Memory**
  - [ ] Change Frigate memory limit from 3g to 2g
  - [ ] Restart stack
  - [ ] Monitor for OOM: `docker-compose logs frigate | grep -i "oom\|memory"`
  - [ ] If OOM occurs, revert to 2.5g

### Phase 2: Health Checks & Monitoring (1 hour)

- [ ] **Implement Health Checks**
  - [ ] Test health check commands in each container
  - [ ] Add health checks to docker-compose.yml
  - [ ] Update depends_on to use `service_started` (not `service_healthy`)
  - [ ] Restart stack and verify all containers reach "healthy" status
  - [ ] Check logs for any health check failures

- [ ] **Whisper Port Security**
  - [ ] Verify HA's Wyoming integration uses `whisper:10300` (container name)
  - [ ] If not, update it in HA UI
  - [ ] Change whisper `ports:` to `expose:`
  - [ ] Restart stack
  - [ ] Verify external access fails: `nc -z 127.0.0.1 10300`
  - [ ] Verify HA can connect: `docker-compose exec homeassistant nc -z whisper 10300`

- [ ] **Add Observability Scripts**
  - [ ] Create `./monitoring/health-check.sh`
  - [ ] Create `./monitoring/frigate-disk-check.sh`
  - [ ] Add cron jobs for automatic monitoring
  - [ ] Test scripts manually
  - [ ] Verify cron entries: `crontab -l`

### Phase 3: Validation & Monitoring (ongoing)

- [ ] Monitor memory usage: `docker stats --no-stream`
- [ ] Check for OOM kills: `docker-compose logs | grep -i "oom"`
- [ ] Monitor disk usage: `./monitoring/frigate-disk-check.sh`
- [ ] Review health check logs: `tail /tmp/ha-health.log`
- [ ] Verify no service restarts: `docker-compose logs | grep "Restarting\|exited with code"`

---

## 11. Rollback Procedures

### If Health Checks Cause Issues

**Symptom:** Services get stuck in "unhealthy" state or never start

**Solution:** Temporarily disable health checks:

```yaml
service:
  healthcheck:
    disable: true  # Add this
```

Then investigate the health check command in container logs.

### If Memory Reduction Causes OOM Kills

**Symptom:** Services restart unexpectedly with "exit 137" or OOM messages

**Solution:** Increase the limit:

```yaml
frigate:
  deploy:
    resources:
      limits:
        memory: 2500m  # Increase from 2g
```

### If Port Security Breaks HA

**Symptom:** Home Assistant can't connect to Whisper; logs show connection refused

**Solution:** Revert to exposed port:

```yaml
whisper:
  ports:
    - "10300:10300"  # Revert to this
  # expose: ...    # Comment out
```

---

## 12. Success Criteria

After implementing all changes, verify:

1. **Memory:** `docker stats` shows < 70% total memory utilization
2. **Health:** All containers report "healthy" or "up"
3. **Restarts:** No unintended service restarts in the past hour
4. **Performance:** HA UI loads in < 2 seconds, Frigate detects at >= 2 FPS
5. **Storage:** Frigate storage increases at expected rate (not runaway growth)
6. **Logs:** No ERROR-level messages from any service (WARN is OK)
7. **Security:** Whisper port not accessible from host (`nc -z 127.0.0.1 10300` fails)

---

## Appendix: Quick Command Reference

```bash
# Health checks
docker-compose ps
docker inspect frigate --format='{{.State.Health.Status}}'

# Logs
docker-compose logs --follow frigate
docker-compose logs --tail=50 homeassistant

# Resource usage
docker stats --no-stream
docker inspect frigate --format='{{.HostConfig.Memory}}'

# Database
docker exec homeassistant du -sh /config/home-assistant_v2.db

# Disk usage
docker exec frigate du -sh /media/frigate

# Restart
docker-compose restart frigate
docker-compose down && docker-compose up -d

# Clean up
docker volume rm home-automation_piper-data
docker system prune -a --volumes  # WARNING: removes all unused images/volumes
```

---

## Document Metadata

**Created:** 2026-03-09
**Target System:** M1 Mac Mini, 8GB RAM, Docker Desktop
**Stack Version:** Current (as of March 2026)
**Status:** SECTIONS 1–8 IMPLEMENTED. Sections 9+ are future/lower priority.
**Last Updated:** 2026-03-28 — Added Section 9 (STT Backend Benchmarking + model switch)

---

## 9. STT Backend Benchmarking (2026-03-28)

### Background

voice-bench data (67 live sessions) showed STT averaging ~9.3s with `whisper-large-v3-turbo-q4` via `wyoming-mlx-whisper`. STT was consuming ~56% of total pipeline time.

### Benchmarking Tool

Installed `mac-whisper-speedtest` at `home-automation/mac-whisper-speedtest/`. Races 9 Whisper implementations on local Apple Silicon hardware with a real audio recording. Run with:

```bash
cd ~/containers/home-automation/mac-whisper-speedtest
.venv/bin/mac-whisper-speedtest --model small --num-runs 3
```

### Results (M1 Mac Mini, small model, 3 runs each)

| Implementation | Avg Time | Notes |
|---|---|---|
| **WhisperKit** | **0.85s** | Swift bridge, Apple Silicon native. Best output quality. |
| mlx-whisper 4-bit | 1.29s | Current backend with new model — warmed up ~0.66s |
| whisper.cpp | 1.39s | Running without CoreML (coreml=False) — could be faster |
| insanely-fast-whisper | 2.21s | MPS, float16 |
| parakeet-mlx | 2.23s | NVIDIA's model via MLX — misspells proper nouns |
| lightning-whisper-mlx | 2.67s | |
| faster-whisper | 2.94s | CPU only |
| whisper-mps | ~31s | Terrible cold start; skip |
| fluidaudio-coreml | timeout | M1 incompatible |

For `large-v3-turbo` model: whisper.cpp was fastest at 5.5s; MLX-based implementations errored (model name mismatch).

### Change Made

Switched `wyoming-mlx-whisper` model from `mlx-community/whisper-large-v3-turbo-q4` → `mlx-community/whisper-small-mlx-4bit` in `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist`. Benchmark showed small model transcribes all typical home-automation commands accurately at ~1.3s. voice-bench tag updated to `small-mlx-4bit-silero-vad` to track before/after.

Also fixed a correlation bug in `voice_bench.py`: the small model is fast enough to produce empty STT hits from ambient noise that previously beat the real transcription in the time-proximity matching. Fixed to prefer non-empty transcriptions.

### Next Step: WhisperKit

WhisperKit benchmarked at **0.85s avg / 0.52s warmed up** — fastest of all implementations, with the best transcription output quality (proper capitalisation and punctuation). Requires a Wyoming protocol wrapper to integrate with Home Assistant. Investigate `wyoming-whisperkit` as a drop-in replacement for `wyoming-mlx-whisper`.

---

**Next Steps:**
1. Review this plan with the user
2. Test Phase 1 (Piper removal + memory reduction) in a non-critical time window
3. Validate Phase 2 (health checks) in a test compose file before applying to production
4. Deploy Phase 3 (observability) with cron jobs
5. Monitor for 1 week before declaring "stable"
