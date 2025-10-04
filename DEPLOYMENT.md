# Deployment Architecture

## Overview

This project uses **separate deployments** for frontend and backend, following modern microservices best practices.

## Architecture

```
User Browser
    ↓
Frontend (Vercel/Netlify)
    ↓ API calls
Backend API (Railway/Render)
    ↓
Database (Supabase/PostgreSQL)
```

## Frontend Deployment

### Platform: Vercel (Recommended)
- **Framework**: Next.js
- **Domain**: `askdrchaffee.com`
- **Build Command**: `npm run build`
- **Output Directory**: `.next`
- **Environment Variables**:
  - `NEXT_PUBLIC_API_URL=https://api.askdrchaffee.com`
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### Deployment Steps:
```bash
cd frontend
vercel --prod
```

### Auto-Deploy:
- Push to `main` → Auto-deploy to production
- Push to `develop` → Auto-deploy to preview
- Pull requests → Preview deployments

## Backend Deployment

### Platform: Railway (Recommended)
- **Framework**: Python FastAPI/Flask
- **Domain**: `api.askdrchaffee.com`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `DATABASE_URL`
  - `YOUTUBE_API_KEY`
  - `HUGGINGFACE_TOKEN`
  - `OPENAI_API_KEY`

### Deployment Steps:
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway up
```

### Auto-Deploy:
- Push to `main` → Auto-deploy backend
- Separate from frontend deployments

## Database

### Platform: Supabase (Recommended)
- **Type**: PostgreSQL
- **Connection**: Backend only (private)
- **Backups**: Automatic daily backups
- **Scaling**: Automatic

## CI/CD Pipeline

### GitHub Actions Workflows:

#### Frontend CI/CD
```yaml
name: Frontend Deploy
on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Vercel
        run: vercel --prod --token=${{ secrets.VERCEL_TOKEN }}
```

#### Backend CI/CD
```yaml
name: Backend Deploy
on:
  push:
    branches: [main]
    paths:
      - 'backend/**'
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Railway
        run: railway up
```

## Environment Variables

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=https://api.askdrchaffee.com
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### Backend (.env)
```bash
DATABASE_URL=postgresql://user:pass@host:5432/db
YOUTUBE_API_KEY=your-key
HUGGINGFACE_TOKEN=your-token
OPENAI_API_KEY=your-key
CORS_ORIGINS=https://askdrchaffee.com
```

## Monitoring

### Frontend
- **Vercel Analytics**: Built-in
- **Error Tracking**: Sentry (optional)

### Backend
- **Railway Metrics**: CPU, Memory, Network
- **Logging**: Railway logs
- **Error Tracking**: Sentry (optional)

## Rollback Strategy

### Frontend
```bash
# Rollback to previous deployment
vercel rollback
```

### Backend
```bash
# Rollback to previous deployment
railway rollback
```

## Cost Estimates

### Free Tier (Development)
- **Frontend**: Vercel Free (100GB bandwidth)
- **Backend**: Railway Free ($5 credit/month)
- **Database**: Supabase Free (500MB, 2GB bandwidth)
- **Total**: $0/month

### Production (Recommended)
- **Frontend**: Vercel Pro ($20/month)
- **Backend**: Railway Pro ($20/month)
- **Database**: Supabase Pro ($25/month)
- **Total**: ~$65/month

## Security

### Frontend
- ✅ HTTPS only (automatic)
- ✅ No secrets in client code
- ✅ CSP headers
- ✅ CORS configured

### Backend
- ✅ HTTPS only
- ✅ Environment secrets
- ✅ Database connection pooling
- ✅ Rate limiting
- ✅ CORS whitelist

## Testing Before Deploy

### Frontend
```bash
cd frontend
npm run build
npm run start  # Test production build locally
```

### Backend
```bash
cd backend
pytest tests/unit/
pytest tests/integration/
```

## Domain Setup

### DNS Configuration
```
askdrchaffee.com          → Vercel (Frontend)
api.askdrchaffee.com      → Railway (Backend)
www.askdrchaffee.com      → Redirect to askdrchaffee.com
```

### SSL Certificates
- Automatic via Vercel and Railway
- No manual configuration needed

## Deployment Checklist

### Initial Setup
- [ ] Create Vercel account and link GitHub repo
- [ ] Create Railway account and link GitHub repo
- [ ] Set up Supabase database
- [ ] Configure environment variables
- [ ] Set up custom domains
- [ ] Configure DNS records
- [ ] Test deployments

### Every Deploy
- [ ] Run tests locally
- [ ] Update CHANGELOG.md
- [ ] Create git tag for version
- [ ] Push to main branch
- [ ] Verify auto-deployment
- [ ] Test production URLs
- [ ] Monitor error logs

## Troubleshooting

### Frontend not updating?
- Clear Vercel cache: `vercel --force`
- Check build logs in Vercel dashboard

### Backend errors?
- Check Railway logs: `railway logs`
- Verify environment variables
- Check database connection

### CORS errors?
- Verify `CORS_ORIGINS` in backend
- Check API URL in frontend env

## Alternative Platforms

### Frontend Alternatives
- **Netlify**: Similar to Vercel
- **Cloudflare Pages**: Free, fast CDN
- **AWS Amplify**: AWS ecosystem

### Backend Alternatives
- **Render**: Similar to Railway
- **Fly.io**: Global edge deployment
- **AWS Lambda**: Serverless
- **Google Cloud Run**: Containerized

### Database Alternatives
- **Neon**: Serverless PostgreSQL
- **PlanetScale**: MySQL-compatible
- **AWS RDS**: Traditional managed DB
