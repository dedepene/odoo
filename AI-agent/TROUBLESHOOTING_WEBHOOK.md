# Telegram Webhook Troubleshooting Guide

## Problem
Messages sent to the Telegram bot are not triggering the webhook endpoint (no logs at line 335).

## Root Causes & Solutions

### 1. Webhook Not Registered with Telegram ⚠️ MOST LIKELY ISSUE

**Symptom**: No logs appear when sending messages to the bot.

**Diagnosis**:
```bash
# Check current webhook status
curl "https://api.telegram.org/bot7380958057:AAH-IBChijuEZLABGVq5YyXzbanCY1On3rU/getWebhookInfo"
```

**Solution**:
```bash
# Set webhook to your public URL (adjust port/domain as needed)
curl -X POST "https://api.telegram.org/bot7380958057:AAH-IBChijuEZLABGVq5YyXzbanCY1On3rU/setWebhook" \
  -d "url=https://dev.smarts4.homes:8080/telegram/webhook"

# Verify it was set
curl "https://api.telegram.org/bot7380958057:AAH-IBChijuEZLABGVq5YyXzbanCY1On3rU/getWebhookInfo"
```

Or use the helper script:
```bash
cd AI-agent
python check_webhook.py
```

### 2. Port Configuration

**Issue**: Docker exposes port 8080, but webhook might be configured for port 8000.

**docker-compose.poc.yml**:
```yaml
ports:
  - "8080:8000"  # Host:Container
```

**Webhook URL should be**: `https://dev.smarts4.homes:8080/telegram/webhook` (NOT port 8000)

**Verify service is accessible**:
```bash
# Test from host machine
curl http://localhost:8080/healthz
curl http://localhost:8080/webhook/test

# Test from public URL
curl https://dev.smarts4.homes:8080/healthz
curl https://dev.smarts4.homes:8080/webhook/test
```

### 3. Cloudflare Tunnel Configuration

Check `cloudflared-config.yml` to ensure it routes to the correct port:

```yaml
ingress:
  - hostname: dev.smarts4.homes
    service: http://localhost:8080  # Should match docker-compose host port
```

### 4. User Must Be Verified First

**Symptom**: Logs show webhook request received, but then 403 error.

**Code at line 344-348**:
```python
user = await fetch_user(session, telegram_id)
if not user or not user.verified_at:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not verified")
```

**Solution**: Register and verify the user first:

```bash
# 1. Send OTP
curl -X POST http://localhost:8080/register/send_otp \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": YOUR_TELEGRAM_ID,
    "phone": "+1234567890",
    "username": "your_username"
  }'

# 2. Check logs for OTP code, then verify
curl -X POST http://localhost:8080/register/verify \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": YOUR_TELEGRAM_ID,
    "otp": "123456",
    "role": "parent",
    "odoo_partner_id": 123,
    "player_ids": [456]
  }'
```

**Find your Telegram ID**:
- Send a message to your bot
- Check Telegram's `getUpdates` API:
```bash
curl "https://api.telegram.org/bot7380958057:AAH-IBChijuEZLABGVq5YyXzbanCY1On3rU/getUpdates"
```

### 5. SSL/HTTPS Requirements

Telegram webhooks REQUIRE:
- HTTPS (not HTTP)
- Valid SSL certificate (Cloudflare tunnel provides this)
- Port 443, 80, 88, or 8443

If using custom port (like 8080), ensure Cloudflare tunnel handles SSL termination.

## Step-by-Step Troubleshooting

### Step 1: Verify Service is Running
```bash
docker compose -f docker-compose.poc.yml ps
```

Expected output: `langchain-agent-1` should be running.

### Step 2: Check Service is Accessible Locally
```bash
curl http://localhost:8080/healthz
# Should return: {"status":"ok"}

curl http://localhost:8080/webhook/test
# Should return service info including telegram_bot_configured
```

### Step 3: Check Service is Accessible Publicly
```bash
curl https://dev.smarts4.homes:8080/healthz
curl https://dev.smarts4.homes:8080/webhook/test
```

If these fail, problem is with Cloudflare tunnel or network configuration.

### Step 4: Check Webhook Configuration
```bash
curl "https://api.telegram.org/bot7380958057:AAH-IBChijuEZLABGVq5YyXzbanCY1On3rU/getWebhookInfo"
```

Look for:
- `"url"`: Should be your webhook URL
- `"pending_update_count"`: Should be 0 (non-zero means delivery issues)
- `"last_error_message"`: Should not exist (if present, shows connection errors)

### Step 5: Set/Update Webhook
```bash
curl -X POST "https://api.telegram.org/bot7380958057:AAH-IBChijuEZLABGVq5YyXzbanCY1On3rU/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://dev.smarts4.homes:8080/telegram/webhook"}'
```

### Step 6: Test with Real Message
Send a message to your bot. Check logs:
```bash
docker compose -f docker-compose.poc.yml logs -f langchain-agent
```

You should now see:
```
INFO:     === TELEGRAM WEBHOOK HIT - Raw request received ===
INFO:     Full webhook payload: {...}
INFO:     Received Telegram webhook message: {...}
INFO:     Processing message from telegram_id: 123456789
```

### Step 7: If Still 403, Register User
Follow "User Must Be Verified First" section above.

## Enhanced Logging

The code has been updated with additional logging to help diagnose issues:

1. **Line 333**: Logs when webhook endpoint is hit
2. **Line 335**: Logs full webhook payload
3. **Line 341**: Logs extracted telegram_id
4. **Lines 344-349**: Logs user verification failures with specific reasons

## Rebuilt Container
After code changes, rebuild and restart:
```bash
docker compose -f docker-compose.poc.yml down
docker compose -f docker-compose.poc.yml up --build -d
docker compose -f docker-compose.poc.yml logs -f langchain-agent
```

## Common Issues Summary

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| No logs at all | Webhook not registered | Set webhook URL with Telegram API |
| Logs show webhook hit, then 403 | User not verified | Register user via OTP endpoints |
| Connection errors in getWebhookInfo | Service not publicly accessible | Check Cloudflare tunnel config |
| Service not responding | Wrong port | Use 8080 (host port) not 8000 |

## Quick Commands Reference

```bash
# Rebuild and restart
docker compose -f docker-compose.poc.yml up --build -d

# View logs
docker compose -f docker-compose.poc.yml logs -f langchain-agent

# Check webhook status
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"

# Set webhook
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://dev.smarts4.homes:8080/telegram/webhook"

# Test service locally
curl http://localhost:8080/healthz

# Test service publicly  
curl https://dev.smarts4.homes:8080/healthz
```
