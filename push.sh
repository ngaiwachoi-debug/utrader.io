#!/bin/bash
echo "📤 正在提交本地代碼並推送到 GitHub..."
git add .
git commit -m "Production Update: $(date +'%Y-%m-%d %H:%M:%S')"
git push origin production --force

echo "🌐 正在連線伺服器執行部署 (請在提示時輸入密碼)..."
# 這裡會連到你的伺服器並執行剛才寫好的 deploy.sh
ssh root@47.83.246.120 "cd /opt/utrader.io && ./deploy.sh"

echo "🚀 全部完成！"