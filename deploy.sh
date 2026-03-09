#!/bin/bash
cd /opt/utrader.io || exit

echo "📥 [1/4] 從 GitHub 抓取最新代碼..."
git fetch origin
git reset --hard origin/production
git clean -fd

echo "🐍 [2/4] 更新 Python 後端依賴..."
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "📦 [3/4] 更新前端 Node.js 依賴..."
# 進入 frontend 資料夾（如果有的話）
if [ -d "frontend" ]; then
    cd frontend
    # 安裝 package.json 裡的新套件
    npm install --quiet
    cd ..
fi

echo "🔄 [4/4] 重新啟動後端服務..."
pkill -f uvicorn
pkill -f arq
sleep 2
export PYTHONPATH=$PYTHONPATH:.
nohup /opt/utrader.io/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
nohup /opt/utrader.io/venv/bin/python -m arq worker.WorkerSettings > worker.log 2>&1 &

echo "✨ 全部部署完成！"