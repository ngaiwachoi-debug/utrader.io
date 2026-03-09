#!/bin/bash
cd /opt/utrader.io || exit
echo "📥 [1/3] 從 GitHub 抓取最新代碼..."
git fetch origin
git reset --hard origin/production
git clean -fd
echo "🐍 [2/3] 進入虛擬環境並安裝依賴..."
source venv/bin/activate
pip install -r requirements.txt --quiet
echo "🔄 [3/3] 重新啟動服務..."
pkill -f uvicorn
pkill -f arq
sleep 2
export PYTHONPATH=$PYTHONPATH:.
nohup /opt/utrader.io/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
nohup /opt/utrader.io/venv/bin/python -m arq worker.WorkerSettings > worker.log 2>&1 &
echo "✨ 部署成功！"