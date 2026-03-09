#!/bin/bash
PROJECT_ROOT="/opt/utrader.io"
cd $PROJECT_ROOT || exit

echo "📥 [1/4] 從 GitHub 抓取最新代碼..."
git fetch origin
git reset --hard origin/production

# --- 🛡️ 保護環境變數檔案 ---
echo "🛡️  正在保護 .env 檔案..."
[ -f ".env" ] && cp .env .env.bak
[ -f "frontend/.env" ] && cp frontend/.env frontend/.env.bak

# 執行大掃除（清理掉所有 Git 未追蹤的雜物）
git clean -fd

# --- 🔄 還原環境變數檔案 ---
[ -f ".env.bak" ] && mv .env.bak .env
[ -f "frontend/.env.bak" ] && mv frontend/.env.bak frontend/.env
# ----------------------

echo "🐍 [2/4] 更新 Python 後端依賴與重啟..."
source venv/bin/activate
pip install -r requirements.txt --quiet

# 強力清理舊進程（使用 fuser 確保端口被釋放）
fuser -k 8000/tcp > /dev/null 2>&1
pkill -9 -f uvicorn
pkill -9 -f arq
sleep 1

export PYTHONPATH=$PYTHONPATH:.
nohup $PROJECT_ROOT/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
nohup $PROJECT_ROOT/venv/bin/python -m arq worker.WorkerSettings > worker.log 2>&1 &

echo "📦 [3/4] 處理前端 Next.js (編譯與重啟)..."
if [ -d "frontend" ]; then
    cd frontend
    npm install --quiet
    
    # 🔥 關鍵：刪除舊快取，強制重新讀取 .env
    echo "🧹 清理前端舊快取..."
    rm -rf .next
    
    echo "🏗️  正在執行 npm run build..."
    npm run build
    
    echo "🔄 正在重啟 Next.js 服務..."
    fuser -k 3000/tcp > /dev/null 2>&1
    pkill -9 -f next-server
    nohup npm run start -- -p 3000 > frontend.log 2>&1 &
    cd ..
else
    echo "⚠️ 未發現 frontend 資料夾。"
fi

echo "--------------------------------------"
echo "🔍 [4/4] 狀態檢查..."
sleep 2
echo "後端 (8000): $(netstat -tulpn | grep :8000 > /dev/null && echo '✅ 運行中' || echo '❌ 失敗')"
echo "前端 (3000): $(netstat -tulpn | grep :3000 > /dev/null && echo '✅ 運行中' || echo '❌ 失敗')"
echo "--------------------------------------"
echo "✨ 全部部署完成！請按 Ctrl+F5 刷新網頁。"