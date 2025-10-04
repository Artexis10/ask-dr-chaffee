# Simple Single-Instance Deployment

**For solo developers who want simplicity over scalability.**

## Architecture

```
Single Server (Railway)
├── Next.js Frontend (Port 3000)
├── Python Backend (Port 8000)
└── PostgreSQL Database (Port 5432)
```

One deployment, one server, one command.

## Quick Setup (5 minutes)

### 1. Install Railway CLI
```bash
npm install -g @railway/cli
railway login
```

### 2. Initialize Project
```bash
railway init
railway link
```

### 3. Add Database
```bash
railway add --database postgresql
```

### 4. Deploy
```bash
railway up
```

Done! Your app is live.

## Project Structure

```
ask-dr-chaffee/
├── frontend/          # Next.js app
├── backend/           # Python API
├── Procfile          # Tells Railway what to run
└── railway.json      # Railway configuration
```

## Configuration Files

### `Procfile` (Root)
```
web: npm run start:all
```

### `package.json` (Root)
```json
{
  "scripts": {
    "start:all": "concurrently \"npm run start:frontend\" \"npm run start:backend\"",
    "start:frontend": "cd frontend && npm start",
    "start:backend": "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT"
  },
  "devDependencies": {
    "concurrently": "^8.0.0"
  }
}
```

### `railway.json`
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "npm run start:all",
    "healthcheckPath": "/api/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

## Environment Variables

Set once in Railway dashboard:

```bash
DATABASE_URL=postgresql://...  # Auto-set by Railway
YOUTUBE_API_KEY=your-key
HUGGINGFACE_TOKEN=your-token
OPENAI_API_KEY=your-key
NODE_ENV=production
```

## Development Workflow

### Local Development
```bash
# Terminal 1: Frontend
cd frontend
npm run dev

# Terminal 2: Backend
cd backend
python -m uvicorn main:app --reload
```

### Deploy Changes
```bash
git add .
git commit -m "Update feature"
git push origin main
# Railway auto-deploys!
```

## Cost Breakdown

### Free Tier (Hobby)
- **Railway**: $5 credit/month (enough for small projects)
- **Database**: Included in Railway
- **Total**: $0/month (with credits)

### Paid Tier (Production)
- **Railway Pro**: $20/month
- **Database**: Included
- **Total**: $20/month

Compare to separate deployments: $65/month

## Monitoring

### Railway Dashboard
- View logs: `railway logs`
- Check metrics: CPU, Memory, Network
- Restart: `railway restart`

### Health Check
```bash
curl https://your-app.railway.app/api/health
```

## Backup Strategy

### Database Backups
```bash
# Railway auto-backups daily
# Manual backup:
railway run pg_dump $DATABASE_URL > backup.sql
```

### Code Backups
- Git is your backup
- Push to GitHub regularly

## Scaling (When You Need It)

If your app grows:

1. **Vertical Scaling** (Easier)
   - Upgrade Railway plan
   - More CPU/RAM on same instance

2. **Horizontal Scaling** (Later)
   - Split into separate deployments
   - Use the full DEPLOYMENT.md guide

## Advantages of Single Instance

✅ **Simplicity**
- One deployment
- One configuration
- One server to manage

✅ **Cost**
- $20/month vs $65/month
- No separate frontend hosting

✅ **Speed**
- No network latency between frontend/backend
- Faster API calls (localhost)

✅ **Development**
- Easier to debug
- Simpler CI/CD
- Faster iterations

## Disadvantages (Accept These Trade-offs)

❌ **No Independent Scaling**
- Frontend and backend scale together
- Fine for solo projects

❌ **Single Point of Failure**
- If server goes down, everything goes down
- Railway has 99.9% uptime, good enough

❌ **Slower Deployments**
- Deploy everything even for small changes
- Still only ~2 minutes, acceptable

❌ **No CDN for Frontend**
- Frontend served from one location
- Fine if users are in one region

## When to Switch to Separate Deployments

Consider splitting when:
- Traffic > 10,000 users/day
- Need global CDN
- Frontend and backend need different scaling
- Team grows beyond solo developer
- Need zero-downtime deployments

Until then, **keep it simple!**

## Troubleshooting

### App won't start?
```bash
railway logs
# Check for errors
```

### Database connection issues?
```bash
railway variables
# Verify DATABASE_URL is set
```

### Want to rollback?
```bash
railway rollback
```

## Alternative: Docker Compose (Self-Hosted)

If you want even more control:

```yaml
# docker-compose.yml
version: '3.8'
services:
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
  
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://db:5432/askdrchaffee
  
  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=askdrchaffee

volumes:
  postgres_data:
```

Deploy to any VPS (DigitalOcean, Linode, etc.) for $5-10/month.

## Summary

**For solo developers:**
- ✅ Use single-instance deployment
- ✅ Railway or Render
- ✅ Keep it simple
- ✅ Scale later if needed

**Don't over-engineer early!**
