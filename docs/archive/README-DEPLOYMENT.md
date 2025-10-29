# Engagic Deployment Guide

This guide covers the most critical improvements and deployment options for engagic.

## 🔧 Recent Critical Improvements

### Security & Reliability
- ✅ **Rate limiting**: 30 requests per minute per IP
- ✅ **Input validation**: Sanitization against injection attacks
- ✅ **Environment configuration**: All settings configurable via environment variables
- ✅ **Health monitoring**: `/api/health` and `/api/metrics` endpoints
- ✅ **Error handling**: Comprehensive logging and error responses

### Configuration Management
All configuration is now handled via environment variables or `.env` file:

```bash
# Copy and edit configuration
cp .env.example .env
# Edit .env to set your ANTHROPIC_API_KEY and other settings
```

## 🚀 Deployment Options

### Option 1: Simple Server Deployment (Recommended for now)

```bash
# Make deploy script executable
chmod +x deploy.sh

# Deploy API server
./deploy.sh deploy    # Full setup
./deploy.sh status    # Check status
./deploy.sh logs      # View logs
./deploy.sh restart   # Restart service

# Deploy background processor (separate service)
sudo systemctl enable /root/engagic/app/engagic-daemon.service
sudo systemctl start engagic-daemon
sudo systemctl status engagic-daemon
```

### Option 2: Docker Deployment (Future scaling)

```bash
# Build and run with Docker Compose
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f engagic-api

# Stop
docker-compose down
```

### Option 3: Manual Setup

```bash
cd app/
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your_key_here"
python app.py
```

## 📊 Monitoring

### Health Checks
- **Health**: `GET /api/health` - Service health status
- **Metrics**: `GET /api/metrics` - System metrics
- **Stats**: `GET /api/stats` - Business metrics

### Log Monitoring
```bash
# API Server logs
journalctl -u engagic -f          # systemd
tail -f /tmp/engagic.log           # script deployment

# Background Processor logs  
journalctl -u engagic-daemon -f   # background service
tail -f /root/engagic/app/engagic.log  # direct file

# Docker logs
docker-compose logs -f engagic-api
```

## ⚙️ Configuration Options

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGAGIC_PORT` | `8000` | API server port |
| `ENGAGIC_HOST` | `0.0.0.0` | API server host |
| `ENGAGIC_DEBUG` | `false` | Debug mode |
| `ENGAGIC_RATE_LIMIT_REQUESTS` | `30` | Rate limit requests per window |
| `ENGAGIC_RATE_LIMIT_WINDOW` | `60` | Rate limit window (seconds) |
| `ANTHROPIC_API_KEY` | *required* | AI processing API key |
| `ENGAGIC_DB_PATH` | `/root/engagic/app/meetings.db` | Database file path |
| `ENGAGIC_LOG_LEVEL` | `INFO` | Logging level |

## 🔒 Security Notes

1. **Rate Limiting**: 30 requests/minute per IP prevents abuse
2. **Input Validation**: All user input is sanitized
3. **CORS**: Configured for your domains only
4. **No Authentication**: Currently public API (suitable for read-only civic data)

## 🚨 Production Readiness Checklist

For production deployment, consider:

- [ ] Set up SSL/TLS (nginx reverse proxy)
- [ ] Configure firewall (allow only 80, 443, 22)
- [ ] Set up automated backups of database
- [ ] Monitor disk space and API performance
- [ ] Set up log rotation
- [ ] Consider rate limiting at nginx level
- [ ] Set up monitoring/alerting (Uptime Robot, etc.)

## 🐛 Troubleshooting

### API won't start
```bash
# Check configuration
./deploy.sh status

# Check logs
./deploy.sh logs

# Common issues:
# 1. Missing ANTHROPIC_API_KEY in .env
# 2. Port 8000 already in use
# 3. Database permissions
```

### High CPU/Memory usage
```bash
# Check resource usage
htop

# Check API metrics
curl http://localhost:8000/api/metrics

# Restart if needed
./deploy.sh restart
```

### Database issues
```bash
# Check database file
ls -la /root/engagic/app/meetings.db

# View database contents
python app/db_viewer.py
```

## 📈 Scaling Considerations

For future growth:
1. Move to PostgreSQL from SQLite
2. Add Redis for rate limiting and caching
3. Implement horizontal scaling with load balancer
4. Add authentication for admin endpoints
5. Set up CI/CD pipeline
6. Add comprehensive monitoring (Prometheus/Grafana)

## 🆘 Support

- Check logs first: `./deploy.sh logs`
- Test API health: `curl http://localhost:8000/api/health`
- View metrics: `curl http://localhost:8000/api/metrics`
- GitHub Issues: Create issue with logs and error details