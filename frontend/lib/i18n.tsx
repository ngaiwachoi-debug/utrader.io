"use client"

import React, { createContext, useCallback, useContext, useEffect, useState } from "react"

export type Lang = "en" | "zh"

const STORAGE_KEY = "utrader_lang"
const COOKIE_NAME = "utrader_lang"

const translations: Record<string, { en: string; zh: string }> = {
  // Header
  "header.dashboard": { en: "Dashboard", zh: "儀表板" },
  "header.allCurrencies": { en: "All currencies", zh: "所有幣種" },
  "header.usd": { en: "USD", zh: "美元" },
  "header.proTrial": { en: "Pro Trial", zh: "專業試用" },
  "header.daysRemaining": { en: "days remaining", zh: "天剩餘" },
  "header.upgradeNow": { en: "Upgrade Now", zh: "立即升級" },
  "header.keepEarning": { en: "Keep earning interest -- subscribe now for unlimited lending and perks.", zh: "持續賺取利息——立即訂閱，享受無限出借與更多權益。" },
  "header.dataCached": { en: "Cached", zh: "快取" },
  "header.rateLimited": { en: "Rate limited — try again in 1 min", zh: "請求過於頻繁，請 1 分鐘後再試" },
  "header.tokensRemaining": { en: "tokens", zh: "代幣" },
  "header.tokenLowRefill": { en: "Token is low, please refill", zh: "代幣不足，請充值" },
  "header.search": { en: "Search", zh: "搜尋" },
  "header.notifications": { en: "Notifications", zh: "通知" },
  "header.help": { en: "Help", zh: "說明" },
  "header.profile": { en: "Profile", zh: "個人資料" },
  "header.logout": { en: "Log out", zh: "登出" },
  "header.login": { en: "Log in", zh: "登入" },
  "header.themeLight": { en: "Switch to light theme", zh: "切換至淺色主題" },
  "header.themeDark": { en: "Switch to dark theme", zh: "切換至深色主題" },
  "header.langEn": { en: "EN", zh: "EN" },
  "header.langZh": { en: "中文", zh: "中文" },

  // Sidebar
  "sidebar.profitCenter": { en: "Profit Center", zh: "利潤中心" },
  "sidebar.liveStatus": { en: "Live Status", zh: "即時狀態" },
  "sidebar.trueRoi": { en: "True ROI", zh: "真實報酬率" },
  "sidebar.subscription": { en: "Subscription", zh: "訂閱方案" },
  "sidebar.referralUsdt": { en: "Referral & USDT", zh: "推薦與 USDT" },
  "sidebar.terminal": { en: "Terminal", zh: "終端機" },
  "sidebar.settings": { en: "Settings", zh: "設定" },
  "sidebar.logout": { en: "Logout", zh: "登出" },
  "sidebar.googleAccount": { en: "Google Account", zh: "Google 帳戶" },
  "sidebar.signIn": { en: "Sign in", zh: "登入" },

  // Settings
  "settings.title": { en: "Settings", zh: "設定" },
  "settings.accountMembership": { en: "Account & Membership", zh: "帳戶與會員" },
  "settings.accountMembershipDesc": { en: "Your current plan and account information", zh: "您目前的方案與帳戶資訊" },
  "settings.rebalancingFrequency": { en: "Rebalancing Frequency", zh: "再平衡頻率" },
  "settings.everyMinutes": { en: "Every {n} minutes", zh: "每 {n} 分鐘" },
  "settings.trialRemaining": { en: "Trial Remaining", zh: "試用剩餘" },
  "settings.tokensRemaining": { en: "Tokens remaining", zh: "剩餘代幣" },
  "settings.tokenUsage": { en: "Token usage", zh: "代幣使用量" },
  "settings.tokenUsageExplanation": { en: "Tokens remaining = total added − total deducted. Added: registration, deposit, subscription, admin. Deducted: usage (0.1 USD gross = 1 token).", zh: "剩餘代幣 = 總添加 − 總扣除。添加：註冊、儲值、訂閱、管理員。扣除：使用量（0.1 美元毛利 = 1 代幣）。" },
  "settings.days": { en: "days", zh: "天" },
  "settings.lendingUsage": { en: "Lending Usage", zh: "出借使用量" },
  "settings.tokenUsageSection": { en: "Token Usage", zh: "代幣使用量" },
  "settings.tabs.lending": { en: "Lending", zh: "出借" },
  "settings.tabs.general": { en: "General", zh: "一般" },
  "settings.noTokensAvailable": { en: "No tokens available", zh: "無可用代幣" },
  "settings.tokenUsageFailed": { en: "Failed to load token usage data", zh: "無法載入代幣使用量資料" },
  "settings.tokensUsedRemaining": { en: "Tokens Used: {used} | Remaining: {remaining}", zh: "已使用：{used} | 剩餘：{remaining}" },
  "settings.totalBudget": { en: "Total Budget: {total}", zh: "總預算：{total}" },
  "settings.every30Minutes": { en: "Every 30 minutes", zh: "每 30 分鐘" },
  "settings.noRenewalDate": { en: "No renewal date (Free Plan)", zh: "無續訂日期（免費方案）" },
  "settings.rateLimitToken": { en: "Too many requests – please try again in 1 minute", zh: "請求過於頻繁，請 1 分鐘後再試" },
  "settings.tokenDataContactSupport": { en: "Failed to load token data – contact support", zh: "無法載入代幣資料，請聯絡客服" },
  "settings.tabs.notifications": { en: "Notifications", zh: "通知" },
  "settings.tabs.apiKeys": { en: "API Keys", zh: "API 金鑰" },
  "settings.tabs.community": { en: "Community", zh: "社群" },

  // Login / Landing
  "login.signIn": { en: "Sign in", zh: "登入" },
  "login.signInWithGoogle": { en: "Sign in with Google", zh: "使用 Google 登入" },
  "login.continueWithGoogle": { en: "Continue with Google", zh: "使用 Google 繼續" },
  "login.freeToUse": { en: "Free to use", zh: "免費使用" },
  "login.secureOAuth": { en: "Secure OAuth", zh: "安全 OAuth" },
  "login.noDataStored": { en: "No data stored", zh: "不儲存資料" },
  "login.backToDashboard": { en: "Back to dashboard", zh: "返回儀表板" },
  "login.onlyGmail": { en: "Only @gmail.com accounts are allowed.", zh: "僅允許 @gmail.com 帳戶登入。" },

  // Mobile nav
  "nav.profit": { en: "Profit", zh: "利潤" },
  "nav.live": { en: "Live", zh: "即時" },
  "nav.roi": { en: "ROI", zh: "報酬率" },
  "nav.settings": { en: "Settings", zh: "設定" },

  // Landing
  "landing.heroTitle": { en: "Professional AI-Powered Bitfinex Funding Bot", zh: "專業 AI 驅動 Bitfinex 資金機器人" },
  "landing.heroSubtitle": { en: "Increase Returns by 40%+", zh: "收益提升 40% 以上" },
  "landing.heroDesc": { en: "Professional Bitfinex lending bot that automatically optimizes your P2P lending strategy 24/7. Average users see 15-40% higher returns with zero manual effort.", zh: "專業 Bitfinex 出借機器人，24/7 自動優化您的 P2P 出借策略。平均用戶可獲得 15–40% 更高收益，無需手動操作。" },
  "landing.startFreeTrial": { en: "Start Free Trial", zh: "開始免費試用" },
  "landing.login": { en: "Log in", zh: "登入" },
  "landing.heroBadge": { en: "Professional Bitfinex Lending Bot", zh: "專業 Bitfinex 出借機器人" },
  "landing.feature1Title": { en: "Live profit tracking", zh: "即時利潤追蹤" },
  "landing.feature1Desc": { en: "Real-time analytics and performance data", zh: "即時分析與績效數據" },
  "landing.feature2Title": { en: "Secure Access", zh: "安全存取" },
  "landing.feature2Desc": { en: "Google OAuth — your keys stay secure", zh: "Google OAuth — 您的金鑰安全無虞" },
  "landing.feature3Title": { en: "ROI Optimization", zh: "報酬率優化" },
  "landing.feature3Desc": { en: "Smart insights and automated rebalancing", zh: "智慧洞察與自動再平衡" },
  "landing.ctaText": { en: "Join thousands of traders using uTrader.io to maximize their Bitfinex lending returns.", zh: "加入數千名使用 uTrader.io 最大化 Bitfinex 出借收益的交易者。" },
  "landing.footerLogin": { en: "Login", zh: "登入" },
  "landing.footerDashboard": { en: "Dashboard", zh: "儀表板" },
  "sidebar.expandSidebar": { en: "Expand sidebar", zh: "展開側邊欄" },
  "sidebar.collapseSidebar": { en: "Collapse sidebar", zh: "收合側邊欄" },
  "liveStatus.realtimeLending": { en: "Real-time lending volume and rate tracking", zh: "即時出借量與利率追蹤" },

  // Dashboard (from messages)
  "dashboard.profitCenter": { en: "Profit Center", zh: "利潤中心" },
  "dashboard.profitCenterDesc": { en: "Track your lending profits, fees, and net earnings in real time.", zh: "即時追蹤您的出借利潤、手續費與淨收益。" },
  "dashboard.dailyProfit": { en: "Daily Profit", zh: "每日利潤" },
  "dashboard.grossProfit": { en: "Gross Profit", zh: "毛利" },
  "dashboard.netEarnings": { en: "Net Earnings", zh: "淨收益" },
  "dashboard.overview": { en: "Overview", zh: "總覽" },
  "dashboard.dateRange": { en: "Date Range", zh: "日期範圍" },
  "dashboard.refresh": { en: "Refresh Data", zh: "重新整理" },
  "dashboard.trueRoiTitle": { en: "Performance & True ROI", zh: "績效與真實報酬率" },
  "dashboard.trueRoiDesc": { en: "Institutional-grade accounting separated from capital flows.", zh: "機構級會計，與資本流動分離。" },
  "dashboard.nav": { en: "Net Asset Value (NAV)", zh: "淨資產價值 (NAV)" },
  "dashboard.capitalFlow": { en: "Net Capital Flow", zh: "淨資本流動" },
  "dashboard.navPerUnit": { en: "Current value per unit", zh: "每單位現值" },
  "dashboard.trueRoi": { en: "True ROI", zh: "真實報酬率" },
  "dashboard.pureYieldInception": { en: "Pure yield since inception", zh: "自成立以來的純收益" },
  "dashboard.depositsWithdrawals": { en: "Total Deposits - Withdrawals", zh: "總存入 - 提領" },
  "dashboard.navVsCapitalTitle": { en: "NAV vs Capital Flow History", zh: "NAV 與資本流動歷史" },
  "dashboard.navVsCapitalDesc": { en: "Visualizing pure yield independently from your total capital size.", zh: "獨立於總資本規模呈現純收益。" },
  "dashboard.capitalLedger": { en: "Capital Ledger", zh: "資本帳簿" },
  "dashboard.capitalLedgerDesc": { en: "History of deposits and withdrawals affecting your unit allocation.", zh: "影響您單位分配的存入與提領歷史。" },
  "dashboard.noCapitalTransactions": { en: "No capital transactions recorded in this period.", zh: "此期間無資本交易記錄。" },
  "dashboard.totalInterestThisPeriod": { en: "Total interest earned this period", zh: "本期間總利息收入" },
  "dashboard.grossProfitSinceRegistration": { en: "Gross profit from Bitfinex lending since registration", zh: "自註冊以來 Bitfinex 出借總利潤" },
  "dashboard.netProfitSinceRegistration": { en: "After Bitfinex fee (15%), before platform charge — since registration", zh: "自註冊以來，扣除 Bitfinex 手續費 (15%)、平台收費前淨收益" },
  "dashboard.displayOnly": { en: "Display only", zh: "僅供顯示" },
  "dashboard.visualFeeBreakdown": { en: "Visual fee breakdown (not deducted)", zh: "手續費視覺化（未實際扣除）" },
  "dashboard.takeHomeIncome": { en: "Your take-home lending income", zh: "您的出借淨收入" },
  "dashboard.proTrialCard": { en: "7-Day Pro Trial", zh: "7 天專業試用" },
  "dashboard.expertPlanFeatures": { en: "Expert Plan features included", zh: "含專家方案功能" },
  "dashboard.daysRemainingShort": { en: "days remaining", zh: "天剩餘" },
  "dashboard.lendingVolume24h": { en: "24h Lending Volume", zh: "24 小時出借量" },
  "dashboard.lendingVolumeDesc": { en: "Daily lending volume over the past week", zh: "過去一週每日出借量" },
  "dashboard.interestEarned": { en: "Interest Earned", zh: "利息收入" },
  "dashboard.interestEarnedDesc": { en: "Daily interest earnings breakdown", zh: "每日利息收入明細" },
  "dashboard.unableToLoadProfit": { en: "Unable to load live profit data.", zh: "無法載入即時利潤資料。" },
  "dashboard.noDataYet": { en: "No data yet", zh: "尚無資料" },
  "dashboard.apiUnreachable": { en: "Cannot reach the API server. Make sure the backend is running.", zh: "無法連線至 API 伺服器，請確認後端已啟動。" },
  "dashboard.dataCached": { en: "Cached", zh: "快取" },
  "dashboard.rateLimited": { en: "Rate limited — try again in 1 min", zh: "請求過於頻繁，請 1 分鐘後再試" },
  "dashboard.terminalDesc": { en: "Trading box terminal output. Whales AI plan shows live logs.", zh: "交易盒終端輸出。Whales AI 方案可查看即時日誌。" },
  "dashboard.terminalBox": { en: "Trading terminal", zh: "交易終端" },
  "dashboard.terminalPlaceholder": { en: "When you save API keys, the bot starts automatically. Output appears here within ~15 seconds (refreshes every 10s).\n\nIf you see this for more than 20 seconds, start the ARQ worker from the project root:\n  python scripts/run_worker.py\n(Requires Redis running.)", zh: "儲存 API 金鑰後，機器人會自動啟動。約 15 秒內會在此顯示輸出（每 10 秒更新）。\n\n若超過 20 秒仍無輸出，請在專案根目錄執行：\n  python scripts/run_worker.py\n（需先啟動 Redis。）" },
  "dashboard.terminalWhalesOnly": { en: "Upgrade to Whales AI to see the live trading terminal.", zh: "升級至 Whales AI 方案以查看即時交易終端。" },
  "dashboard.trueRoiWhalesOnly": { en: "True ROI is available on Whales plan.", zh: "True ROI 僅在 Whales 方案中提供。" },
  "liveStatus.dataCached": { en: "Cached", zh: "快取" },
  "liveStatus.rateLimited": { en: "Rate limited — try again in 1 min", zh: "請求過於頻繁，請 1 分鐘後再試" },
  "liveStatus.refreshIn": { en: "Refresh in {n}s", zh: "{n} 秒後可重新整理" },
  "dashboard.platformFee": { en: "Platform Fee (20%)", zh: "平台手續費 (20%)" },
  "dashboard.trialProgress": { en: "Trial Progress", zh: "試用進度" },
  "dashboard.dayXofY": { en: "Day {n} of {total}", zh: "第 {n} / {total} 天" },
  "dashboard.upgradeToPro": { en: "Upgrade to Pro", zh: "升級專業版" },
  "subscription.title": { en: "Choose Your Plan", zh: "選擇方案" },
  "subscription.subtitle": { en: "Upgrade from your trial to continue enjoying unlimited lending features", zh: "從試用升級，持續享受無限出借功能" },
  "subscription.monthly": { en: "Monthly", zh: "月付" },
  "subscription.yearly": { en: "Yearly", zh: "年付" },
  "subscription.save10": { en: "Save 10%", zh: "省 10%" },
  "subscription.proPlan": { en: "Pro Plan", zh: "專業方案" },
  "subscription.proAudience": { en: "Perfect for individual traders", zh: "適合個人交易者" },
  "subscription.expertPlan": { en: "Expert Plan", zh: "專家方案" },
  "subscription.expertAudience": { en: "For professional traders", zh: "適合專業交易者" },
  "subscription.mostPopular": { en: "Most Popular", zh: "最受歡迎" },
  "subscription.perMonth": { en: "/month", zh: "/月" },
  "subscription.billedYearly": { en: "Billed {amount} yearly", zh: "年付 {amount}" },
  "subscription.subscribePro": { en: "Subscribe to Pro", zh: "訂閱專業版" },
  "subscription.subscribeExpert": { en: "Subscribe to Expert", zh: "訂閱專家版" },
  "subscription.terms": { en: "By subscribing, you agree to our Terms of Service and Privacy Policy.", zh: "訂閱即表示您同意我們的服務條款與隱私政策。" },
  "subscription.cancelAnytime": { en: "Cancel anytime", zh: "隨時取消" },
  "subscription.securePayment": { en: "Secure payment with Stripe", zh: "由 Stripe 安全付款" },
  "subscription.daysLeft": { en: "{n} days left", zh: "剩餘 {n} 天" },
  "subscription.featureLimit50": { en: "Up to $50,000 lending limit", zh: "最高 $50,000 出借限額" },
  "subscription.featureLimit250": { en: "Up to $250,000 lending limit", zh: "最高 $250,000 出借限額" },
  "subscription.featureRebalance30": { en: "30-minute rebalancing", zh: "30 分鐘再平衡" },
  "subscription.featureRebalance3": { en: "3-minute rebalancing", zh: "3 分鐘再平衡" },
  "subscription.featureAnalytics": { en: "Advanced analytics", zh: "進階分析" },
  "subscription.featureAllAnalytics": { en: "All analytics features", zh: "完整分析功能" },
  "subscription.featureEmailNotif": { en: "Email notifications", zh: "電子郵件通知" },
  "subscription.featureRealtimeNotif": { en: "Real-time notifications", zh: "即時通知" },
  "subscription.featurePrioritySupport": { en: "Priority support", zh: "優先支援" },
  "subscription.featureCustomStrategies": { en: "Custom strategies", zh: "自訂策略" },
  "subscription.featureRiskMgmt": { en: "Advanced risk management", zh: "進階風險管理" },
  "subscription.tokensRemaining": { en: "{n} tokens remaining", zh: "剩餘 {n} 代幣" },
  "subscription.tokenUsageRule": { en: "0.1 USD gross profit = 1 token used. Credits refresh on plan renewal.", zh: "0.1 USD 毛利 = 1 代幣消耗。方案續訂時重置額度。" },
  "subscription.usageBar": { en: "Token usage", zh: "代幣使用量" },
  "subscription.runningLow": { en: "Running low on tokens. Upgrade or add tokens to keep the bot running.", zh: "代幣即將用盡。請升級或加購代幣以持續運行機器人。" },
  "subscription.addTokens": { en: "Add tokens", zh: "加購代幣" },
  "subscription.addTokensDesc": { en: "Deposit USD to get tokens: 1 USD = 100 tokens.", zh: "存入 USD 換取代幣：1 USD = 100 代幣。" },
  "subscription.amountUsd": { en: "Amount (USD)", zh: "金額 (USD)" },
  "subscription.purchaseTokens": { en: "Purchase tokens", zh: "購買代幣" },
  "subscription.aiUltraPlan": { en: "AI Ultra", zh: "AI Ultra" },
  "subscription.whalesPlan": { en: "Whales AI", zh: "Whales AI" },
  "subscription.aiUltraAudience": { en: "3-min rebalancing, Gemini AI", zh: "3 分鐘再平衡、Gemini AI" },
  "subscription.whalesAudience": { en: "1-min rebalancing, Gemini AI, terminal", zh: "1 分鐘再平衡、Gemini AI、終端" },
  "subscription.featureTokens": { en: "{n} token credit", zh: "{n} 代幣額度" },
  "subscription.featureRebalance1": { en: "1-minute rebalancing", zh: "1 分鐘再平衡" },
  "subscription.featureGemini": { en: "Use Gemini AI", zh: "使用 Gemini AI" },
  "subscription.featureTerminal": { en: "Trading terminal view", zh: "交易終端檢視" },
  "subscription.subscribeAiUltra": { en: "Subscribe to AI Ultra", zh: "訂閱 AI Ultra" },
  "subscription.subscribeWhales": { en: "Subscribe to Whales AI", zh: "訂閱 Whales AI" },
  "Common.user": { en: "User", zh: "用戶" },

  // Live Status
  "liveStatus.title": { en: "Live Status", zh: "即時狀態" },
  "liveStatus.refresh": { en: "Refresh", zh: "重新整理" },
  "liveStatus.startBot": { en: "Start Bot", zh: "啟動機器人" },
  "liveStatus.stopBot": { en: "Stop Bot", zh: "停止機器人" },
  "liveStatus.waitBeforeAction": { en: "Please wait {n}s", zh: "請等待 {n} 秒" },
  "liveStatus.startBotTitle": { en: "Start the lending bot", zh: "啟動出借機器人" },
  "liveStatus.stopBotTitle": { en: "Stop the lending bot", zh: "停止出借機器人" },
  "liveStatus.startFailed": { en: "Start failed. Upgrade or add tokens if balance is below 0.1.", zh: "啟動失敗。若餘額低於 0.1 請升級或加購代幣。" },
  "liveStatus.starting": { en: "Starting...", zh: "啟動中…" },
  "liveStatus.stopping": { en: "Stopping...", zh: "停止中…" },
  "liveStatus.statusUnknown": { en: "Status Unknown", zh: "狀態未知" },
  "liveStatus.botActive": { en: "Bot Active", zh: "機器人運行中" },
  "liveStatus.botStopped": { en: "Bot Stopped", zh: "機器人已停止" },
  "liveStatus.total": { en: "Total", zh: "總計" },
  "liveStatus.assets": { en: "ASSETS", zh: "資產" },
  "liveStatus.allCurrencies": { en: "All currencies (Bitfinex)", zh: "所有幣種 (Bitfinex)" },
  "liveStatus.loaned": { en: "LOANED", zh: "已出借" },
  "liveStatus.currentlyLoaned": { en: "Currently loaned", zh: "當前已出借" },
  "liveStatus.currentlyLentOut": { en: "Currently Lent Out", zh: "各幣種已出借" },
  "liveStatus.totalUsdValue": { en: "Total USD value across funding wallet.", zh: "資金錢包總 USD 價值。" },
  "liveStatus.loading": { en: "Loading…", zh: "載入中…" },
  "liveStatus.connectApiKeys": { en: "Connect API keys in Settings to see assets.", zh: "請在設定中連接 API 金鑰以查看資產。" },
  "liveStatus.dataIncomplete": { en: "Data temporarily unavailable; try again shortly.", zh: "資料暫時無法取得，請稍後再試。" },
  "liveStatus.unableToLoad": { en: "Unable to load live status.", zh: "無法載入即時狀態。" },
  "liveStatus.marketOverview": { en: "Market Overview", zh: "市場概覽" },
  "liveStatus.rate": { en: "Rate", zh: "利率" },
  "liveStatus.volume": { en: "Volume", zh: "成交量" },
  "liveStatus.bitfinexLendingLedger": { en: "Bitfinex Lending Ledger", zh: "Bitfinex 出借帳簿" },
  "liveStatus.lendingLedgerDesc": { en: "Hourly high-low rate range and lending history", zh: "每小時高低利率區間與出借歷史" },
  "liveStatus.currentAnnualRate": { en: "Current Annual Rate:", zh: "當前年利率：" },
  "liveStatus.dailyRate": { en: "Daily rate:", zh: "日利率：" },
  "liveStatus.time": { en: "Time", zh: "時間" },
  "liveStatus.rateRange": { en: "Rate Range", zh: "利率區間" },
  "liveStatus.maxDays": { en: "Max Days", zh: "最長天數" },
  "liveStatus.cumulative": { en: "Cumulative", zh: "累計" },
  "liveStatus.amount": { en: "Amount", zh: "金額" },
  "liveStatus.count": { en: "Count", zh: "筆數" },
  "liveStatus.totalCol": { en: "Total", zh: "總計" },
  "liveStatus.portfolioAllocation": { en: "Portfolio Allocation", zh: "投資組合配置" },
  "liveStatus.capitalDeploymentOverview": { en: "Capital deployment overview", zh: "資金部署概覽" },
  "liveStatus.allocationBreakdown": { en: "Allocation Breakdown", zh: "配置明細" },
  "liveStatus.earning": { en: "Earning", zh: "收益中" },
  "liveStatus.deploying": { en: "Deploying", zh: "部署中" },
  "liveStatus.activelyEarning": { en: "Actively Earning", zh: "積極收益中" },
  "liveStatus.generatingReturns": { en: "Generating returns", zh: "產生收益" },
  "liveStatus.pendingDeployment": { en: "Pending Deployment", zh: "待部署" },
  "liveStatus.awaitingOpportunities": { en: "Awaiting opportunities", zh: "等待機會" },
  "liveStatus.inOrderBook": { en: "In Order Book", zh: "掛單中" },
  "liveStatus.idleFunds": { en: "Idle Funds", zh: "閒置資金" },
  "liveStatus.cashDrag": { en: "Cash drag — not yet placed by bot", zh: "現金拖累 — 尚未由機器人掛單" },
  "liveStatus.returnGenerating": { en: "Return generating", zh: "產生收益" },
  "liveStatus.notDeployed": { en: "Not currently deployed", zh: "目前未部署" },
  "liveStatus.performance": { en: "Performance", zh: "績效" },
  "liveStatus.keyMetrics": { en: "Key metrics", zh: "關鍵指標" },
  "liveStatus.estDailyEarnings": { en: "Est. Daily Earnings", zh: "預估每日收益" },
  "liveStatus.basedOnCurrentRates": { en: "Based on current rates", zh: "依當前利率" },
  "liveStatus.weightedAvgApr": { en: "Weighted Avg APR", zh: "加權平均年利率" },
  "liveStatus.acrossAllActiveLending": { en: "Across all active lending", zh: "所有活躍出借" },
  "liveStatus.activeOrders": { en: "Active Orders", zh: "活躍訂單" },
  "liveStatus.activeLendingPositions": { en: "Active lending positions", zh: "活躍出借筆數" },
  "liveStatus.takenOrders": { en: "Taken orders", zh: "已成交訂單" },
  "liveStatus.takenOrdersDesc": { en: "Active lending positions (filled orders)", zh: "活躍出借筆數（已成交）" },
  "liveStatus.totalLendedOutOrders": { en: "Total lended out", zh: "總出借筆數" },
  "liveStatus.totalLendedOutOrdersDesc": { en: "Total capital currently lent out", zh: "目前出借總金額" },
  "liveStatus.ordersNotTaken": { en: "Orders not taken", zh: "未成交訂單" },
  "liveStatus.ordersNotTakenDesc": { en: "Still listing on Bitfinex lending", zh: "仍在 Bitfinex 出借掛單中" },
  "liveStatus.yieldOverTotal": { en: "Yield / Total Wallet", zh: "收益／總錢包" },
  "liveStatus.yieldOverTotalDesc": { en: "Weighted yield applied to total wallet", zh: "加權收益佔總錢包比" },
  "liveStatus.personalLendingLedger": { en: "Personal Lending Ledger", zh: "個人出借帳簿" },
  "liveStatus.personalLendingLedgerDesc": { en: "Your active lending positions (10 per page)", zh: "您的活躍出借部位（每頁 10 筆）" },
  "liveStatus.pendingExecution": { en: "Pending execution", zh: "待執行" },
  "sidebar.marketStatus": { en: "Market Status", zh: "市場狀態" },
  "marketStatus.title": { en: "Market Status", zh: "市場狀態" },
  "marketStatus.subtitle": { en: "Bitfinex lending rates and volume", zh: "Bitfinex 出借利率與成交量" },
  "marketStatus.lendingLedger": { en: "Lending Ledger", zh: "出借帳簿" },
  "marketStatus.selectCurrency": { en: "Select currency", zh: "選擇幣種" },
  "settings.apiKeysCreated": { en: "Created", zh: "建立時間" },
  "settings.notTested": { en: "Not Tested", zh: "未測試" },
  "settings.testedOn": { en: "Tested on {date}", zh: "測試於 {date}" },
  "settings.testApiKeys": { en: "Test API Keys", zh: "測試 API 金鑰" },
  "settings.removeKey": { en: "Remove API key", zh: "移除 API 金鑰" },
  "settings.updateApiKeys": { en: "Update API Keys", zh: "更新 API 金鑰" },
  "settings.apiKeyTestResult": { en: "API Keys Test Result", zh: "API 金鑰測試結果" },
  "settings.keysWorkingCorrectly": { en: "Your API keys are working correctly!", zh: "您的 API 金鑰運作正常！" },
  "settings.connectionSuccessful": { en: "Connection Successful", zh: "連線成功" },
  "settings.keysVerifiedReady": { en: "API keys verified and ready to use", zh: "API 金鑰已驗證，可使用" },
  "settings.fundingWalletAvailable": { en: "Funding Wallet: {amount} Available", zh: "資金錢包：{amount} 可用" },
  "settings.joinTelegram": { en: "Join Telegram Group", zh: "加入 Telegram 群組" },
  "settings.close": { en: "Close", zh: "關閉" },
  "settings.verified": { en: "Verified", zh: "已驗證" },
}

type LanguageContextValue = {
  language: Lang
  setLanguage: (lang: Lang) => void
  t: (key: string, params?: Record<string, string | number>) => string
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Lang>("en")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    if (typeof window === "undefined") {
      setMounted(true)
      return
    }
    const fromStorage = localStorage.getItem(STORAGE_KEY) as Lang | null
    const fromCookie = document.cookie.match(new RegExp(`(^| )${COOKIE_NAME}=([^;]+)`))?.[2] as Lang | null
    const stored = fromStorage ?? fromCookie
    if (stored === "en" || stored === "zh") setLanguageState(stored)
    setMounted(true)
  }, [])

  const setLanguage = useCallback((lang: Lang) => {
    setLanguageState(lang)
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, lang)
      document.cookie = `${COOKIE_NAME}=${lang};path=/;max-age=31536000;SameSite=Lax`
    }
  }, [])

  const t = useCallback(
    (key: string, params?: Record<string, string | number>): string => {
      const entry = translations[key]
      if (!entry) return key
      let text = language === "zh" ? entry.zh : entry.en
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v))
        })
      }
      return text
    },
    [language]
  )

  if (!mounted) {
    return (
      <LanguageContext.Provider value={{ language: "en", setLanguage, t }}>
        {children}
      </LanguageContext.Provider>
    )
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) return { language: "en" as Lang, setLanguage: () => {}, t: (k: string) => k }
  return ctx
}

export function useT() {
  const ctx = useContext(LanguageContext)
  return useCallback(
    (key: string, params?: Record<string, string | number>) => {
      if (!ctx) return key
      return ctx.t(key, params)
    },
    [ctx]
  )
}
