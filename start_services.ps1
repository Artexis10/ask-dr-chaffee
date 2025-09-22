# Start Dr. Chaffee Application Services
# This script starts both the RAG service and Next.js frontend

Write-Host "🚀 Starting Dr. Chaffee Application Services..." -ForegroundColor Green

# Check if Python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python not found. Please install Python first." -ForegroundColor Red
    exit 1
}

# Check if Node.js is available  
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Node.js not found. Please install Node.js first." -ForegroundColor Red
    exit 1
}

# Check environment variables
if (-not $env:OPENAI_API_KEY) {
    Write-Host "⚠️ Warning: OPENAI_API_KEY not set. RAG service may not work." -ForegroundColor Yellow
}

if (-not $env:DATABASE_URL) {
    Write-Host "⚠️ Warning: DATABASE_URL not set. Services may not connect to database." -ForegroundColor Yellow
}

# Function to start RAG service
function Start-RAGService {
    Write-Host "🔍 Starting RAG API service on port 5001..." -ForegroundColor Cyan
    
    try {
        # Start RAG service in background
        $ragProcess = Start-Process python -ArgumentList "backend/scripts/rag_api_service.py", "--port", "5001" -PassThru -NoNewWindow
        
        # Wait a moment for service to start
        Start-Sleep -Seconds 3
        
        # Test if service is responding
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:5001/health" -TimeoutSec 5
            Write-Host "✅ RAG service started successfully" -ForegroundColor Green
            return $ragProcess
        }
        catch {
            Write-Host "❌ RAG service failed to start properly" -ForegroundColor Red
            if ($ragProcess -and !$ragProcess.HasExited) {
                Stop-Process -Id $ragProcess.Id -Force
            }
            return $null
        }
    }
    catch {
        Write-Host "❌ Failed to start RAG service: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

# Function to start frontend
function Start-Frontend {
    Write-Host "🖥️ Starting Next.js frontend on port 3000..." -ForegroundColor Cyan
    
    try {
        # Change to frontend directory and start
        Set-Location frontend
        
        # Check if node_modules exists
        if (-not (Test-Path "node_modules")) {
            Write-Host "📦 Installing frontend dependencies..." -ForegroundColor Yellow
            npm install
        }
        
        # Start frontend in background
        $frontendProcess = Start-Process npm -ArgumentList "run", "dev" -PassThru -NoNewWindow
        
        # Wait for frontend to start
        Start-Sleep -Seconds 5
        
        # Test if frontend is responding
        $retries = 0
        do {
            Start-Sleep -Seconds 2
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 5 -UseBasicParsing
                if ($response.StatusCode -eq 200) {
                    Write-Host "✅ Frontend started successfully" -ForegroundColor Green
                    return $frontendProcess
                }
            }
            catch {
                $retries++
            }
        } while ($retries -lt 10)
        
        Write-Host "❌ Frontend failed to start properly" -ForegroundColor Red
        if ($frontendProcess -and !$frontendProcess.HasExited) {
            Stop-Process -Id $frontendProcess.Id -Force
        }
        return $null
    }
    catch {
        Write-Host "❌ Failed to start frontend: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
    finally {
        # Return to root directory
        Set-Location ..
    }
}

# Main execution
Write-Host ""
Write-Host "==================================" -ForegroundColor Blue
Write-Host "  Dr. Chaffee Application Stack   " -ForegroundColor Blue  
Write-Host "==================================" -ForegroundColor Blue
Write-Host ""

# Start services
$ragProcess = Start-RAGService
$frontendProcess = Start-Frontend

# Check results
$servicesStarted = 0
if ($ragProcess) { $servicesStarted++ }
if ($frontendProcess) { $servicesStarted++ }

Write-Host ""
Write-Host "==================================" -ForegroundColor Blue
Write-Host "         SERVICE STATUS           " -ForegroundColor Blue
Write-Host "==================================" -ForegroundColor Blue

if ($ragProcess) {
    Write-Host "🔍 RAG Service:     ✅ Running (PID: $($ragProcess.Id))" -ForegroundColor Green
    Write-Host "   URL: http://localhost:5001" -ForegroundColor Cyan
} else {
    Write-Host "🔍 RAG Service:     ❌ Failed" -ForegroundColor Red
}

if ($frontendProcess) {
    Write-Host "🖥️ Frontend:        ✅ Running (PID: $($frontendProcess.Id))" -ForegroundColor Green
    Write-Host "   URL: http://localhost:3000" -ForegroundColor Cyan
} else {
    Write-Host "🖥️ Frontend:        ❌ Failed" -ForegroundColor Red
}

Write-Host ""

if ($servicesStarted -eq 2) {
    Write-Host "🎉 All services started successfully!" -ForegroundColor Green
    Write-Host "📱 Open http://localhost:3000 to use the application" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "💡 The frontend will automatically use the RAG service for enhanced answers" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Gray
    
    # Keep script running and monitor processes
    try {
        while ($true) {
            Start-Sleep -Seconds 5
            
            # Check if processes are still running
            if ($ragProcess -and $ragProcess.HasExited) {
                Write-Host "⚠️ RAG service stopped unexpectedly" -ForegroundColor Red
                break
            }
            
            if ($frontendProcess -and $frontendProcess.HasExited) {
                Write-Host "⚠️ Frontend stopped unexpectedly" -ForegroundColor Red
                break
            }
        }
    }
    catch {
        Write-Host "`n🛑 Stopping services..." -ForegroundColor Yellow
    }
    finally {
        # Cleanup processes
        if ($ragProcess -and !$ragProcess.HasExited) {
            Write-Host "🔄 Stopping RAG service..." -ForegroundColor Yellow
            Stop-Process -Id $ragProcess.Id -Force
        }
        
        if ($frontendProcess -and !$frontendProcess.HasExited) {
            Write-Host "🔄 Stopping frontend..." -ForegroundColor Yellow
            Stop-Process -Id $frontendProcess.Id -Force
        }
        
        Write-Host "✅ All services stopped" -ForegroundColor Green
    }
    
} else {
    Write-Host "❌ Some services failed to start. Check the errors above." -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 You can start services individually:" -ForegroundColor Yellow
    Write-Host "   RAG Service: python backend/scripts/rag_api_service.py" -ForegroundColor Gray
    Write-Host "   Frontend: cd frontend && npm run dev" -ForegroundColor Gray
    
    # Cleanup any started processes
    if ($ragProcess -and !$ragProcess.HasExited) {
        Stop-Process -Id $ragProcess.Id -Force
    }
    if ($frontendProcess -and !$frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force
    }
    
    exit 1
}
