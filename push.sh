#!/bin/bash

# 1. 提交本地代碼並推送到 GitHub
echo "📤 [1/2] 正在提交本地代碼並推送到 GitHub..."
git add .
# 自動加上時間戳記，這樣你就知道是哪天幾點部署的
git commit -m "🚀 Production Deploy: $(date +'%Y-%m-%d %H:%M:%S')"
git push origin production --force

echo "--------------------------------------"

# 2. 通知伺服器執行部署
echo "🌐 [2/2] 正在連線伺服器執行部署..."
# 注意：這裡我們直接呼叫伺服器上的 deploy.sh
# 提示：如果你已經設定了 SSH Key，這裡就不會問你密碼
ssh root@47.83.246.120 "cd /opt/utrader.io && ./deploy.sh"

echo "--------------------------------------"
echo "✅ 全部完成！你的更新已在線運作。"