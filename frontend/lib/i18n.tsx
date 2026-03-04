"use client"

import React, { createContext, useCallback, useContext, useEffect, useState } from "react"

export type Lang = "en" | "zh" | "ko" | "ru" | "de" | "pt" | "fil" | "id" | "ja"

/** Order: English first, Chinese second, then by prevalence (Google/lang usage). */
export const SUPPORTED_LOCALES: Lang[] = ["en", "zh", "pt", "id", "ja", "ru", "de", "ko", "fil"]

function isLang(s: string): s is Lang {
  return SUPPORTED_LOCALES.includes(s as Lang)
}

const STORAGE_KEY = "utrader_lang"
const COOKIE_NAME = "utrader_lang"

type TranslationEntry = { en: string; zh?: string; ko?: string; ru?: string; de?: string; pt?: string; fil?: string; id?: string; ja?: string }

const translations: Record<string, TranslationEntry> = {
  // Header
  "header.dashboard": { en: "Dashboard", zh: "儀表板", ko: "대시보드", ru: "Панель", de: "Dashboard" },
  "header.allCurrencies": { en: "All currencies", zh: "所有幣種", ko: "모든 통화", ru: "Все валюты", de: "Alle Währungen" },
  "header.usd": { en: "USD", zh: "美元", ko: "USD", ru: "USD", de: "USD" },
  "header.proTrial": { en: "Pro Trial", zh: "專業試用", ko: "프로 체험", ru: "Pro пробный", de: "Pro-Testversion" },
  "header.daysRemaining": { en: "days remaining", zh: "天剩餘", ko: "일 남음", ru: "дней осталось", de: "Tage verbleibend" },
  "header.upgradeNow": { en: "Upgrade Now", zh: "立即升級", ko: "지금 업그레이드", ru: "Обновить сейчас", de: "Jetzt upgraden" },
  "header.keepEarning": { en: "Keep earning interest -- subscribe now for unlimited lending and perks.", zh: "持續賺取利息——立即訂閱，享受無限出借與更多權益。", ko: "이자 수익을 유지하세요. 지금 구독하여 무제한 대출과 혜택을 받으세요.", ru: "Продолжайте получать проценты — подпишитесь для неограниченного кредитования.", de: "Zinsen weiter verdienen — jetzt abonnieren für unbegrenztes Lending." },
  "header.dataCached": { en: "Cached", zh: "快取", ko: "캐시됨", ru: "Кэш", de: "Gecacht" },
  "header.rateLimited": { en: "Rate limited — try again in 1 min", zh: "請求過於頻繁，請 1 分鐘後再試", ko: "요청 제한 — 1분 후 다시 시도하세요.", ru: "Лимит запросов — попробуйте через 1 мин.", de: "Ratenlimit — in 1 Min. erneut versuchen." },
  "header.tokensRemaining": { en: "tokens", zh: "代幣", ko: "토큰", ru: "токены", de: "Tokens" },
  "header.tokenLowRefill": { en: "Token is low, please refill", zh: "代幣不足，請充值", ko: "토큰이 부족합니다. 충전해 주세요.", ru: "Токенов мало, пополните баланс.", de: "Token niedrig, bitte aufladen." },
  "header.search": { en: "Search", zh: "搜尋", ko: "검색", ru: "Поиск", de: "Suchen" },
  "header.notifications": { en: "Notifications", zh: "通知", ko: "알림", ru: "Уведомления", de: "Benachrichtigungen" },
  "header.help": { en: "Help", zh: "說明", ko: "도움말", ru: "Помощь", de: "Hilfe" },
  "header.profile": { en: "Profile", zh: "個人資料", ko: "프로필", ru: "Профиль", de: "Profil" },
  "header.logout": { en: "Log out", zh: "登出", ko: "로그아웃", ru: "Выйти", de: "Abmelden" },
  "header.login": { en: "Log in", zh: "登入", ko: "로그인", ru: "Войти", de: "Anmelden" },
  "header.theme": { en: "Theme", zh: "主題", ko: "테마", ru: "Тема", de: "Design" },
  "header.themeLight": { en: "Switch to light theme", zh: "切換至淺色主題", ko: "라이트 테마로 전환", ru: "Переключить на светлую тему", de: "Zum hellen Design wechseln" },
  "header.themeDark": { en: "Switch to dark theme", zh: "切換至深色主題", ko: "다크 테마로 전환", ru: "Переключить на тёмную тему", de: "Zum dunklen Design wechseln" },
  "header.installApp": { en: "Install app", zh: "安裝應用", ko: "앱 설치", ru: "Установить приложение", de: "App installieren" },
  "header.installAppTitle": { en: "Create a shortcut or install the app", zh: "建立捷徑或安裝應用程式", ko: "바로가기 만들기 또는 앱 설치", ru: "Создать ярлык или установить приложение", de: "Verknüpfung erstellen oder App installieren" },
  "header.installAppShortcut": { en: "Create desktop shortcut", zh: "建立桌面捷徑", ko: "바탕화면 바로가기 만들기", ru: "Создать ярлык на рабочем столе", de: "Desktop-Verknüpfung erstellen" },
  "header.installAppChromeHint": { en: "In Chrome you can add this site as an app or shortcut:", zh: "在 Chrome 中可將此網站新增為應用程式或捷徑：", ko: "Chrome에서 이 사이트를 앱 또는 바로가기로 추가할 수 있습니다.", ru: "В Chrome можно добавить этот сайт как приложение или ярлык:", de: "In Chrome können Sie diese Seite als App oder Verknüpfung hinzufügen:" },
  "header.installAppChromeSteps": { en: "Click the menu (⋮) → More tools → Create shortcut. Check \"Open as window\" for an app-like experience.", zh: "點選選單 (⋮) → 更多工具 → 建立捷徑。勾選「以視窗開啟」可獲得類似應用程式的體驗。", ko: "메뉴(⋮) → 더보기 도구 → 바로가기 만들기. \"창으로 열기\"를 선택하면 앱처럼 사용할 수 있습니다.", ru: "Меню (⋮) → Дополнительные инструменты → Создать ярлык. Включите «Открыть как окно» для режима приложения.", de: "Menü (⋮) → Weitere Tools → Verknüpfung erstellen. „Als Fenster öffnen“ für App-Erlebnis aktivieren." },
  "header.langEn": { en: "EN", zh: "EN", ko: "EN", ru: "EN", de: "EN" },
  "header.langZh": { en: "中文", zh: "中文", ko: "중문", ru: "Кит.", de: "Chin." },

  // Sidebar
  "sidebar.profitCenter": { en: "Profit Center", zh: "利潤中心", ko: "수익 센터", ru: "Центр прибыли", de: "Profit-Center" },
  "sidebar.liveStatus": { en: "Live Status", zh: "即時狀態", ko: "실시간 상태", ru: "Статус в реальном времени", de: "Live-Status" },
  "sidebar.trueRoi": { en: "True ROI", zh: "真實報酬率", ko: "실질 수익률", ru: "Истинная доходность", de: "Echter ROI" },
  "sidebar.subscription": { en: "Subscription", zh: "訂閱方案", ko: "구독", ru: "Подписка", de: "Abonnement" },
  "sidebar.referralUsdt": { en: "Referral & USDT", zh: "推薦與 USDT", ko: "추천 및 USDT", ru: "Рефералы и USDT", de: "Empfehlung & USDT" },
  "sidebar.ranking": { en: "Ranking", zh: "排行榜", ko: "순위", ru: "Рейтинг", de: "Rangliste" },
  "sidebar.leaderboard": { en: "Leaderboard", zh: "排行榜", ko: "리더보드", ru: "Таблица лидеров", de: "Bestenliste" },
  "sidebar.terminal": { en: "Terminal", zh: "終端機", ko: "터미널", ru: "Терминал", de: "Terminal" },
  "sidebar.settings": { en: "Settings", zh: "設定", ko: "설정", ru: "Настройки", de: "Einstellungen" },
  "sidebar.logout": { en: "Logout", zh: "登出", ko: "로그아웃", ru: "Выйти", de: "Abmelden" },
  "sidebar.googleAccount": { en: "Google Account", zh: "Google 帳戶", ko: "Google 계정", ru: "Аккаунт Google", de: "Google-Konto" },
  "sidebar.signIn": { en: "Sign in", zh: "登入", ko: "로그인", ru: "Войти", de: "Anmelden" },

  // Settings
  "settings.title": { en: "Settings", zh: "設定" },
  "settings.accountMembership": { en: "Account & Membership", zh: "帳戶與會員" },
  "settings.accountMembershipDesc": { en: "Your current plan and account information", zh: "您目前的方案與帳戶資訊" },
  "settings.rebalancingFrequency": { en: "Rebalancing Frequency", zh: "再平衡頻率" },
  "settings.everyMinutes": { en: "Every {n} minutes", zh: "每 {n} 分鐘" },
  "settings.trialRemaining": { en: "Trial Remaining", zh: "試用剩餘" },
  "settings.tokensRemaining": { en: "Tokens remaining", zh: "剩餘代幣" },
  "settings.tokenUsage": { en: "Token usage", zh: "代幣使用量" },
  "settings.tokenUsageExplanation": { en: "Tokens remaining = total added − total deducted. Added: registration, deposit, subscription, admin. Deducted: usage (1 USD gross = {multiplier} token(s)).", zh: "剩餘代幣 = 總添加 − 總扣除。添加：註冊、儲值、訂閱、管理員。扣除：使用量（1 美元毛利 = {multiplier} 代幣）。" },
  "settings.days": { en: "days", zh: "天" },
  "settings.lendingUsage": { en: "Lending Usage", zh: "出借使用量" },
  "settings.tokenUsageSection": { en: "Token Usage", zh: "代幣使用量" },
  "settings.tokenAddedHistory": { en: "Token added history", zh: "代幣添加記錄" },
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
  "settings.tabs.tokenActivity": { en: "Token activity", zh: "代幣記錄" },
  "settings.tokenActivityTitle": { en: "Token add & deduction log", zh: "代幣添加與扣減記錄" },
  "settings.tokenAddLog": { en: "Token add log", zh: "代幣添加記錄" },
  "settings.tokenDeductionLog": { en: "Token deduction log", zh: "代幣扣減記錄" },
  "settings.noTokenAddHistory": { en: "No token add history yet.", zh: "尚無代幣添加記錄。" },
  "settings.noDeductionHistory": { en: "No deduction history yet.", zh: "尚無扣減記錄。" },

  // Login / Landing
  "login.signIn": { en: "Sign in", zh: "登入", ko: "로그인", ru: "Войти", de: "Anmelden" },
  "login.signInWithGoogle": { en: "Sign in with Google", zh: "使用 Google 登入", ko: "Google로 로그인", ru: "Войти через Google", de: "Mit Google anmelden" },
  "login.continueWithGoogle": { en: "Continue with Google", zh: "使用 Google 繼續", ko: "Google로 계속", ru: "Продолжить с Google", de: "Mit Google fortfahren" },
  "login.freeToUse": { en: "Free to use", zh: "免費使用", ko: "무료 사용", ru: "Бесплатно", de: "Kostenlos" },
  "login.secureOAuth": { en: "Secure OAuth", zh: "安全 OAuth", ko: "보안 OAuth", ru: "Безопасный OAuth", de: "Sicheres OAuth" },
  "login.noDataStored": { en: "No data stored", zh: "不儲存資料", ko: "데이터 저장 안 함", ru: "Данные не сохраняются", de: "Keine Datenspeicherung" },
  "login.backToDashboard": { en: "Back to dashboard", zh: "返回儀表板", ko: "대시보드로 돌아가기", ru: "Назад к панели", de: "Zurück zum Dashboard" },
  "login.onlyGmail": { en: "Only @gmail.com accounts are allowed.", zh: "僅允許 @gmail.com 帳戶登入。", ko: "@gmail.com 계정만 사용 가능합니다.", ru: "Разрешены только аккаунты @gmail.com.", de: "Nur @gmail.com-Konten erlaubt." },

  // Mobile nav
  "nav.profit": { en: "Profit", zh: "利潤", ko: "수익", ru: "Прибыль", de: "Gewinn" },
  "nav.live": { en: "Live", zh: "即時", ko: "실시간", ru: "В реальном времени", de: "Live" },
  "nav.roi": { en: "ROI", zh: "報酬率", ko: "수익률", ru: "Доходность", de: "ROI" },
  "nav.settings": { en: "Settings", zh: "設定", ko: "설정", ru: "Настройки", de: "Einstellungen" },

  // Landing
  "landing.heroTitle": { en: "Professional AI-Powered Bitfinex Funding Bot", zh: "專業 AI 驅動 Bitfinex 資金機器人", ko: "AI 기반 Bitfinex 펀딩 봇", ru: "Профессиональный AI Bitfinex Funding Bot", de: "Professioneller KI-gestützter Bitfinex Funding Bot" },
  "landing.heroSubtitle": { en: "Increase Returns by 40%+", zh: "收益提升 40% 以上", ko: "수익 40% 이상 증대", ru: "Рост доходности на 40%+", de: "Rendite um 40%+ steigern" },
  "landing.heroDesc": { en: "Professional Bitfinex lending bot that automatically optimizes your P2P lending strategy 24/7. Average users see 15-40% higher returns with zero manual effort.", zh: "專業 Bitfinex 出借機器人，24/7 自動優化您的 P2P 出借策略。平均用戶可獲得 15–40% 更高收益，無需手動操作。", ko: "24/7 P2P 대출 전략을 자동 최적화하는 Bitfinex 대출 봇. 평균 15–40% 높은 수익.", ru: "Профессиональный бот Bitfinex для автоматической оптимизации P2P-кредитования 24/7.", de: "Professioneller Bitfinex Lending Bot, optimiert Ihre P2P-Strategie 24/7 automatisch." },
  "landing.startFreeTrial": { en: "Start Free Trial", zh: "開始免費試用", ko: "무료 체험 시작", ru: "Начать бесплатный период", de: "Kostenlose Testversion starten" },
  "landing.login": { en: "Log in", zh: "登入", ko: "로그인", ru: "Войти", de: "Anmelden" },
  "landing.heroBadge": { en: "Professional Bitfinex Lending Bot", zh: "專業 Bitfinex 出借機器人", ko: "전문 Bitfinex 대출 봇", ru: "Профессиональный бот Bitfinex Lending", de: "Professioneller Bitfinex Lending Bot" },
  "landing.feature1Title": { en: "Live profit tracking", zh: "即時利潤追蹤", ko: "실시간 수익 추적", ru: "Отслеживание прибыли в реальном времени", de: "Live-Gewinnverfolgung" },
  "landing.feature1Desc": { en: "Real-time analytics and performance data", zh: "即時分析與績效數據", ko: "실시간 분석 및 성과 데이터", ru: "Аналитика и данные в реальном времени", de: "Echtzeit-Analysen und Leistungsdaten" },
  "landing.feature2Title": { en: "Secure Access", zh: "安全存取", ko: "보안 액세스", ru: "Безопасный доступ", de: "Sicherer Zugriff" },
  "landing.feature2Desc": { en: "Google OAuth — your keys stay secure", zh: "Google OAuth — 您的金鑰安全無虞", ko: "Google OAuth — 키 보안 유지", ru: "Google OAuth — ваши ключи в безопасности", de: "Google OAuth — Ihre Schlüssel bleiben sicher" },
  "landing.feature3Title": { en: "ROI Optimization", zh: "報酬率優化", ko: "수익률 최적화", ru: "Оптимизация доходности", de: "ROI-Optimierung" },
  "landing.feature3Desc": { en: "Smart insights and automated rebalancing", zh: "智慧洞察與自動再平衡", ko: "스마트 인사이트 및 자동 재조정", ru: "Умная аналитика и авторебалансировка", de: "Smarte Einblicke und automatisches Rebalancing" },
  "landing.ctaText": { en: "Join thousands of traders using bifinexbot.com to maximize their Bitfinex lending returns.", zh: "加入數千名使用 bifinexbot.com 最大化 Bitfinex 出借收益的交易者。", ko: "bifinexbot.com으로 Bitfinex 대출 수익을 극대화하는 수천 명의 트레이더와 함께하세요.", ru: "Присоединяйтесь к тысячам трейдеров на bifinexbot.com.", de: "Tausende Trader nutzen bifinexbot.com für maximale Bitfinex Lending-Renditen." },
  "landing.footerLogin": { en: "Login", zh: "登入", ko: "로그인", ru: "Войти", de: "Anmelden" },
  "landing.footerDashboard": { en: "Dashboard", zh: "儀表板", ko: "대시보드", ru: "Панель", de: "Dashboard" },
  "sidebar.expandSidebar": { en: "Expand sidebar", zh: "展開側邊欄", ko: "사이드바 펼치기", ru: "Развернуть панель", de: "Seitenleiste erweitern" },
  "sidebar.collapseSidebar": { en: "Collapse sidebar", zh: "收合側邊欄", ko: "사이드바 접기", ru: "Свернуть панель", de: "Seitenleiste einklappen" },
  "liveStatus.realtimeLending": { en: "Real-time lending volume and rate tracking", zh: "即時出借量與利率追蹤", ko: "실시간 대출량 및 금리 추적", ru: "Объём и ставки в реальном времени", de: "Echtzeit-Lending-Volumen und Zinssätze" },

  // Dashboard (from messages)
  "dashboard.profitCenter": { en: "Profit Center", zh: "利潤中心", ko: "수익 센터", ru: "Центр прибыли", de: "Profit-Center" },
  "dashboard.profitCenterDesc": { en: "Track your lending profits, fees, and net earnings in real time.", zh: "即時追蹤您的出借利潤、手續費與淨收益。", ko: "대출 수익, 수수료, 순수익을 실시간으로 추적하세요.", ru: "Прибыль, комиссии и чистый доход в реальном времени.", de: "Lending-Gewinn, Gebühren und Nettoeinnahmen in Echtzeit verfolgen." },
  "dashboard.tokenCredit": { en: "Token credit", zh: "代幣額度" },
  "dashboard.tokenUsageRule": { en: "1 USD gross profit = {multiplier} token(s) used. Deducted daily.", zh: "1 美元毛利 = {multiplier} 代幣使用，每日扣減。" },
  "dashboard.totalTokensAdded": { en: "total added", zh: "總計已添加" },
  "dashboard.tokenBreakdown": { en: "Allocation breakdown", zh: "配置明細" },
  "dashboard.tokensRemaining": { en: "Remaining", zh: "剩餘" },
  "dashboard.tokensUsed": { en: "Used", zh: "已使用" },
  "dashboard.dailyProfit": { en: "Daily Profit", zh: "每日利潤", ko: "일일 수익", ru: "Дневная прибыль", de: "Tagesgewinn" },
  "dashboard.grossProfit": { en: "Gross Profit", zh: "毛利", ko: "총이익", ru: "Валовая прибыль", de: "Bruttogewinn" },
  "dashboard.netEarnings": { en: "Net Earnings", zh: "淨收益", ko: "순수익", ru: "Чистый доход", de: "Nettoeinnahmen" },
  "dashboard.overview": { en: "Overview", zh: "總覽", ko: "개요", ru: "Обзор", de: "Übersicht" },
  "dashboard.dateRange": { en: "Date Range", zh: "日期範圍", ko: "날짜 범위", ru: "Период", de: "Datumsbereich" },
  "dashboard.refresh": { en: "Refresh Data", zh: "重新整理", ko: "새로고침", ru: "Обновить", de: "Aktualisieren" },
  "dashboard.trueRoiTitle": { en: "Performance & True ROI", zh: "績效與真實報酬率", ko: "성과 및 실질 수익률", ru: "Результаты и истинная доходность", de: "Performance & echter ROI" },
  "dashboard.trueRoiDesc": { en: "Institutional-grade accounting separated from capital flows.", zh: "機構級會計，與資本流動分離。", ko: "자본 흐름과 분리된 기관급 회계.", ru: "Учёт институционального уровня.", de: "Institutionelle Buchhaltung getrennt von Kapitalflüssen." },
  "dashboard.nav": { en: "Net Asset Value (NAV)", zh: "淨資產價值 (NAV)", ko: "순자산가치 (NAV)", ru: "Чистая стоимость активов (NAV)", de: "Nettoinventarwert (NAV)" },
  "dashboard.capitalFlow": { en: "Net Capital Flow", zh: "淨資本流動", ko: "순 자본 흐름", ru: "Чистый поток капитала", de: "Nettokapitalfluss" },
  "dashboard.navPerUnit": { en: "Current value per unit", zh: "每單位現值", ko: "단위당 현재 가치", ru: "Текущая стоимость за единицу", de: "Aktueller Wert pro Einheit" },
  "dashboard.trueRoi": { en: "True ROI", zh: "真實報酬率", ko: "실질 수익률", ru: "Истинная доходность", de: "Echter ROI" },
  "dashboard.pureYieldInception": { en: "Pure yield since inception", zh: "自成立以來的純收益", ko: "시작 이후 순수 수익", ru: "Чистая доходность с начала", de: "Reine Rendite seit Start" },
  "dashboard.depositsWithdrawals": { en: "Total Deposits - Withdrawals", zh: "總存入 - 提領", ko: "총 입금 - 출금", ru: "Всего депозиты − выводы", de: "Einlagen gesamt − Abhebungen" },
  "dashboard.navVsCapitalTitle": { en: "NAV vs Capital Flow History", zh: "NAV 與資本流動歷史", ko: "NAV 대 자본 흐름 기록", ru: "NAV и история потоков капитала", de: "NAV vs. Kapitalfluss-Verlauf" },
  "dashboard.navVsCapitalDesc": { en: "Visualizing pure yield independently from your total capital size.", zh: "獨立於總資本規模呈現純收益。", ko: "총 자본 규모와 무관하게 순수 수익 시각화.", ru: "Чистая доходность независимо от размера капитала.", de: "Reine Rendite unabhängig von der Kapitalgröße." },
  "dashboard.capitalLedger": { en: "Capital Ledger", zh: "資本帳簿", ko: "자본 원장", ru: "Реестр капитала", de: "Kapitalbuch" },
  "dashboard.capitalLedgerDesc": { en: "History of deposits and withdrawals affecting your unit allocation.", zh: "影響您單位分配的存入與提領歷史。", ko: "단위 배분에 영향을 주는 입출금 내역.", ru: "История депозитов и выводов.", de: "Historie von Ein- und Auszahlungen." },
  "dashboard.noCapitalTransactions": { en: "No capital transactions recorded in this period.", zh: "此期間無資本交易記錄。", ko: "이 기간에 자본 거래 기록이 없습니다.", ru: "В этом периоде записей нет.", de: "In diesem Zeitraum keine Kapitaltransaktionen." },
  "dashboard.totalInterestThisPeriod": { en: "Total interest earned this period", zh: "本期間總利息收入", ko: "이 기간 총 이자 수익", ru: "Общий процент за период", de: "Gesamtzinsen in diesem Zeitraum" },
  "dashboard.grossProfitSinceRegistration": { en: "Gross profit from Bitfinex lending since registration", zh: "自註冊以來 Bitfinex 出借總利潤", ko: "가입 후 Bitfinex 대출 총이익", ru: "Валовая прибыль Bitfinex с регистрации", de: "Bruttogewinn aus Bitfinex Lending seit Registrierung" },
  "dashboard.netProfitSinceRegistration": { en: "After Bitfinex fee (15%), before platform charge — since registration", zh: "自註冊以來，扣除 Bitfinex 手續費 (15%)、平台收費前淨收益", ko: "Bitfinex 수수료(15%) 차감 후, 플랫폼 수수료 전 — 가입 이후", ru: "После комиссии Bitfinex (15%), до платформы — с регистрации", de: "Nach Bitfinex-Gebühr (15%), vor Plattformgebühr — seit Registrierung" },
  "dashboard.displayOnly": { en: "Display only", zh: "僅供顯示", ko: "표시 전용", ru: "Только отображение", de: "Nur Anzeige" },
  "dashboard.visualFeeBreakdown": { en: "Visual fee breakdown (not deducted)", zh: "手續費視覺化（未實際扣除）", ko: "수수료 시각화 (실제 차감 아님)", ru: "Визуализация комиссий (не списывается)", de: "Gebührenaufschlüsselung (nicht abgezogen)" },
  "dashboard.takeHomeIncome": { en: "Your take-home lending income", zh: "您的出借淨收入", ko: "귀하의 대출 순수익", ru: "Ваш чистый доход от кредитования", de: "Ihr Netto-Lending-Einkommen" },
  "dashboard.proTrialCard": { en: "7-Day Pro Trial", zh: "7 天專業試用", ko: "7일 프로 체험", ru: "7-дневный пробный Pro", de: "7-Tage-Pro-Test" },
  "dashboard.expertPlanFeatures": { en: "Expert Plan features included", zh: "含專家方案功能", ko: "전문가 플랜 기능 포함", ru: "Функции Expert включены", de: "Expert-Plan-Funktionen inklusive" },
  "dashboard.daysRemainingShort": { en: "days remaining", zh: "天剩餘", ko: "일 남음", ru: "дней осталось", de: "Tage verbleibend" },
  "dashboard.lendingVolume24h": { en: "24h Lending Volume", zh: "24 小時出借量", ko: "24시간 대출량", ru: "Объём за 24 ч", de: "24h-Lending-Volumen" },
  "dashboard.lendingVolumeDesc": { en: "Daily lending volume over the past week", zh: "過去一週每日出借量", ko: "지난 주 일별 대출량", ru: "Ежедневный объём за неделю", de: "Tägliches Lending-Volumen der letzten Woche" },
  "dashboard.interestEarned": { en: "Interest Earned", zh: "利息收入", ko: "이자 수익", ru: "Полученные проценты", de: "Verdiente Zinsen" },
  "dashboard.interestEarnedDesc": { en: "Daily interest earnings breakdown", zh: "每日利息收入明細", ko: "일별 이자 수익 내역", ru: "Ежедневная разбивка процентов", de: "Tägliche Zinsaufschlüsselung" },
  "dashboard.unableToLoadProfit": { en: "Unable to load live profit data.", zh: "無法載入即時利潤資料。", ko: "실시간 수익 데이터를 불러올 수 없습니다.", ru: "Не удалось загрузить данные прибыли.", de: "Live-Gewinndaten konnten nicht geladen werden." },
  "dashboard.noDataYet": { en: "No data yet", zh: "尚無資料", ko: "아직 데이터 없음", ru: "Пока нет данных", de: "Noch keine Daten" },
  "dashboard.apiUnreachable": { en: "Cannot reach the API server. Make sure the backend is running.", zh: "無法連線至 API 伺服器，請確認後端已啟動。", ko: "API 서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.", ru: "Сервер API недоступен. Проверьте, что бэкенд запущен.", de: "API-Server nicht erreichbar. Backend prüfen." },
  "dashboard.dataCached": { en: "Cached", zh: "快取", ko: "캐시됨", ru: "Кэш", de: "Gecacht" },
  "dashboard.rateLimited": { en: "Rate limited — try again in 1 min", zh: "請求過於頻繁，請 1 分鐘後再試", ko: "요청 제한 — 1분 후 다시 시도하세요.", ru: "Лимит запросов — попробуйте через 1 мин.", de: "Ratenlimit — in 1 Min. erneut versuchen." },
  "dashboard.terminalDesc": { en: "Trading box terminal output. Whales AI plan shows live logs.", zh: "交易盒終端輸出。Whales AI 方案可查看即時日誌。" },
  "dashboard.terminalBox": { en: "Trading terminal", zh: "交易終端" },
  "dashboard.terminalPlaceholder": { en: "When you save API keys, the bot starts automatically. Output appears here within ~15 seconds (refreshes every 10s).\n\nIf you see this for more than 20 seconds, start the ARQ worker from the project root:\n  python scripts/run_worker.py\n(Requires Redis running.)", zh: "儲存 API 金鑰後，機器人會自動啟動。約 15 秒內會在此顯示輸出（每 10 秒更新）。\n\n若超過 20 秒仍無輸出，請在專案根目錄執行：\n  python scripts/run_worker.py\n（需先啟動 Redis。）" },
  "dashboard.terminalCopy": { en: "Copy", zh: "複製" },
  "dashboard.terminalCopied": { en: "Copied", zh: "已複製" },
  "dashboard.terminalScrollToBottom": { en: "Scroll to bottom", zh: "捲動至底部" },
  "dashboard.terminalWhalesOnly": { en: "Upgrade to Whales AI to see the live trading terminal.", zh: "升級至 Whales AI 方案以查看即時交易終端。" },
  "dashboard.trueRoiWhalesOnly": { en: "True ROI is available on Whales plan.", zh: "True ROI 僅在 Whales 方案中提供。" },
  "liveStatus.dataCached": { en: "Cached", zh: "快取" },
  "liveStatus.rateLimited": { en: "Rate limited — try again in 1 min", zh: "請求過於頻繁，請 1 分鐘後再試" },
  "liveStatus.refreshIn": { en: "Refresh in {n}s", zh: "{n} 秒後可重新整理" },
  "dashboard.platformFee": { en: "Platform Fee (20%)", zh: "平台手續費 (20%)" },
  "dashboard.trialProgress": { en: "Trial Progress", zh: "試用進度" },
  "dashboard.dayXofY": { en: "Day {n} of {total}", zh: "第 {n} / {total} 天" },
  "dashboard.upgradeToPro": { en: "Upgrade to Pro", zh: "升級專業版" },
  "dashboard.upgradeToAiUltra": { en: "Upgrade to AI Ultra", zh: "升級 AI Ultra" },
  "dashboard.upgradeToWhalesAi": { en: "Upgrade to Whales AI", zh: "升級 Whales AI" },
  "subscription.title": { en: "Plan & tokens", zh: "方案與代幣" },
  "subscription.subtitle": { en: "Manage your balance and subscription. Upgrade or add tokens to keep the bot running.", zh: "管理您的餘額與訂閱。升級或加購代幣以持續運行機器人。" },
  "subscription.balanceRemaining": { en: "Tokens remaining", zh: "剩餘代幣" },
  "subscription.usedOfTotal": { en: "{used} used of {total} total", zh: "已用 {used} / 總計 {total}" },
  "subscription.howItWorks": { en: "How tokens work", zh: "代幣說明" },
  "subscription.howItWorksLead": { en: "Tokens power your lending bot. You earn them when you join or pay; we deduct them daily based on your margin funding profit so usage stays fair and transparent.", zh: "代幣驅動您的出借機器人。註冊或付費時獲得；我們依您的保證金收益每日扣除，使用透明公平。" },
  "subscription.howEarnTitle": { en: "Earning tokens", zh: "如何獲得代幣" },
  "subscription.howEarnBody": { en: "Sign-up bonus, subscription plan credits (Pro, AI Ultra, Whales), and Pay As You Go top-ups. 1 USD = 100 tokens when you deposit.", zh: "註冊贈送、訂閱方案額度（Pro / AI Ultra / Whales）及隨用隨付加購。儲值 1 美元 = 100 代幣。" },
  "subscription.howUseTitle": { en: "Daily usage", zh: "每日使用方式" },
  "subscription.howUseBody": { en: "We deduct {multiplier} token(s) per 1 USD of your daily gross profit from margin funding (e.g. 10:30 UTC). No profit that day = no deduction. View full history in Settings → Token activity.", zh: "每日依您的保證金毛利 1 美元扣 {multiplier} 代幣（約 10:30 UTC）。當日無收益則不扣。完整記錄請至 設定 → 代幣記錄 查看。" },
  "subscription.howItWorksFooter": { en: "Your balance is shown above. Top up anytime with a plan or Pay As You Go to keep the bot running.", zh: "餘額顯示於上方。可隨時以方案或隨用隨付加購，維持機器人運作。" },
  "subscription.howItWorksIntro": { en: "Tokens power your bot. They are added when you sign up, renew a plan, or deposit; they are deducted daily based on your gross profit.", zh: "代幣用於驅動機器人。註冊、方案續訂或儲值時增加；每日依毛利扣除。" },
  "subscription.howAdded": { en: "Added: sign-up bonus, plan renewal credits, and Pay As You Go deposits.", zh: "增加：註冊贈送、方案續訂額度、按量付費儲值。" },
  "subscription.howDeducted": { en: "Deducted: 1 USD gross profit = {multiplier} token(s), applied daily (e.g. 10:30 UTC). Credits refresh on plan renewal.", zh: "扣除：1 美元毛利 = {multiplier} 代幣，每日結算（如 10:30 UTC）。方案續訂時額度重置。" },
  "subscription.plansSection": { en: "Subscription plans", zh: "訂閱方案" },
  "subscription.addTokensPreview": { en: "You get {n} tokens", zh: "可獲得 {n} 代幣" },
  "subscription.securelyByStripe": { en: "Secured by Stripe", zh: "由 Stripe 保障" },
  "subscription.bypassPaymentDev": { en: "Bypass payment (dev)", zh: "略過付款（開發用）" },
  "subscription.faqTitle": { en: "Frequently asked questions", zh: "常見問題" },
  "subscription.faqDeduct": { en: "How are tokens deducted?", zh: "代幣如何扣除？" },
  "subscription.faqDeductA": { en: "Each day we deduct {multiplier} token(s) per 1 USD of your gross profit from margin funding (e.g. at 10:30 UTC). No profit that day means no deduction.", zh: "每日依您的保證金毛利 1 美元扣 {multiplier} 代幣（例如 10:30 UTC）。當日無收益則不扣。" },
  "subscription.faqRefresh": { en: "When do my plan credits refresh?", zh: "方案額度何時重置？" },
  "subscription.faqRefreshA": { en: "Your plan’s token credit is refilled when your subscription renews (monthly or yearly, depending on your plan).", zh: "訂閱續訂時（依方案月付或年付）會重新填入該方案的代幣額度。" },
  "subscription.faqRefund": { en: "Can I get a refund?", zh: "可以退款嗎？" },
  "subscription.faqRefundA": { en: "Refund policy depends on your plan and payment method. Contact support for specific cases.", zh: "退款依方案與付款方式而定，具體情況請聯絡客服。" },
  "subscription.validUsd": { en: "Please enter a valid USD amount", zh: "請輸入有效的 USD 金額" },
  "subscription.minDeposit": { en: "Minimum deposit is $1", zh: "最低儲值 $1" },
  "subscription.calculatingTokens": { en: "Calculating tokens...", zh: "計算代幣中…" },
  "subscription.monthly": { en: "Monthly", zh: "月付" },
  "subscription.yearly": { en: "Yearly", zh: "年付" },
  "subscription.save10": { en: "Save 10%", zh: "省 10%" },
  "subscription.proPlan": { en: "Pro Plan", zh: "專業方案" },
  "subscription.proAudience": { en: "Perfect for individual traders", zh: "適合個人交易者" },
  "subscription.expertPlan": { en: "Expert Plan", zh: "專家方案" },
  "subscription.expertAudience": { en: "For professional traders", zh: "適合專業交易者" },
  "subscription.mostPopular": { en: "Most Popular", zh: "最受歡迎" },
  "subscription.perMonth": { en: "/month", zh: "/月" },
  "subscription.perYear": { en: "/year", zh: "/年" },
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
  "subscription.featureGeneralSupport": { en: "General support", zh: "一般支援" },
  "subscription.featurePrioritySupport": { en: "Priority support", zh: "優先支援" },
  "subscription.featureTrueRoi": { en: "True ROI", zh: "真實報酬率" },
  "subscription.featureCustomStrategies": { en: "Custom strategies", zh: "自訂策略" },
  "subscription.featureRiskMgmt": { en: "Advanced risk management", zh: "進階風險管理" },
  "subscription.tokensRemaining": { en: "{n} tokens remaining", zh: "剩餘 {n} 代幣" },
  "subscription.tokenUsageRule": { en: "1 USD gross profit = {multiplier} token(s) used. Credits refresh on plan renewal.", zh: "1 美元毛利 = {multiplier} 代幣消耗。方案續訂時重置額度。" },
  "subscription.usageBar": { en: "Token usage", zh: "代幣使用量" },
  "subscription.runningLow": { en: "Running low on tokens. Upgrade or add tokens to keep the bot running.", zh: "代幣即將用盡。請升級或加購代幣以持續運行機器人。" },
  "subscription.addTokens": { en: "Pay As You Go", zh: "按量付費" },
  "subscription.addTokensDesc": { en: "Top up anytime. 1 USD = 100 tokens.", zh: "隨時加值。1 USD = 100 代幣。" },
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
  "subscription.comparePlans": { en: "Compare plans", zh: "方案比較" },
  "subscription.featureColumn": { en: "Feature", zh: "功能" },
  "subscription.featureRebalance": { en: "Rebalance interval", zh: "再平衡間隔" },
  "subscription.featureTokenCredit": { en: "Token credit", zh: "代幣額度" },
  "Common.user": { en: "User", zh: "用戶" },

  // Live Status
  "liveStatus.title": { en: "Live Status", zh: "即時狀態", ko: "실시간 상태", ru: "Статус в реальном времени", de: "Live-Status" },
  "liveStatus.refresh": { en: "Refresh", zh: "重新整理", ko: "새로고침", ru: "Обновить", de: "Aktualisieren" },
  "liveStatus.startBot": { en: "Start Bot", zh: "啟動機器人", ko: "봇 시작", ru: "Запустить бота", de: "Bot starten" },
  "liveStatus.stopBot": { en: "Stop Bot", zh: "停止機器人", ko: "봇 중지", ru: "Остановить бота", de: "Bot stoppen" },
  "liveStatus.waitBeforeAction": { en: "Please wait {n}s", zh: "請等待 {n} 秒", ko: "{n}초 기다려 주세요.", ru: "Подождите {n} с.", de: "Bitte {n}s warten." },
  "liveStatus.startBotTitle": { en: "Start the lending bot", zh: "啟動出借機器人", ko: "대출 봇 시작", ru: "Запустить бота кредитования", de: "Lending-Bot starten" },
  "liveStatus.stopBotTitle": { en: "Stop the lending bot", zh: "停止出借機器人", ko: "대출 봇 중지", ru: "Остановить бота кредитования", de: "Lending-Bot stoppen" },
  "liveStatus.startFailed": { en: "Start failed. Upgrade or add tokens if balance is below 0.1.", zh: "啟動失敗。若餘額低於 0.1 請升級或加購代幣。", ko: "시작 실패. 잔액이 0.1 미만이면 업그레이드하거나 토큰을 충전하세요.", ru: "Запуск не удался. При балансе ниже 0.1 обновите план или пополните токены.", de: "Start fehlgeschlagen. Bei Guthaben unter 0.1 upgraden oder Tokens aufladen." },
  "liveStatus.starting": { en: "Starting...", zh: "啟動中…", ko: "시작 중…", ru: "Запуск…", de: "Starte…" },
  "liveStatus.stopping": { en: "Stopping...", zh: "停止中…", ko: "중지 중…", ru: "Остановка…", de: "Stoppe…" },
  "liveStatus.statusUnknown": { en: "Status Unknown", zh: "狀態未知", ko: "상태 알 수 없음", ru: "Статус неизвестен", de: "Status unbekannt" },
  "liveStatus.checkingStatus": { en: "Checking…", zh: "檢查中…" },
  "liveStatus.loadingStatus": { en: "Loading Status", zh: "載入狀態" },
  "liveStatus.tooManyStartStop": { en: "Too many start/stop requests. Please wait before trying again.", zh: "啟動/停止請求過於頻繁，請稍後再試。" },
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
    const fromStorage = localStorage.getItem(STORAGE_KEY)
    const fromCookie = document.cookie.match(new RegExp(`(^| )${COOKIE_NAME}=([^;]+)`))?.[2]
    const stored = fromStorage ?? fromCookie
    if (stored && isLang(stored)) {
      setLanguageState(stored)
    } else {
      const pathname = window.location.pathname
      const localeMatch = pathname.match(/^\/(en|zh|ko|ru|de|pt|fil|id|ja)(\/|$)/)
      const localeFromPath = localeMatch?.[1]
      if (localeFromPath && isLang(localeFromPath)) {
        setLanguageState(localeFromPath)
        localStorage.setItem(STORAGE_KEY, localeFromPath)
        document.cookie = `${COOKIE_NAME}=${localeFromPath};path=/;max-age=31536000;SameSite=Lax`
      }
    }
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
      const text = (entry[language] ?? entry.en) as string
      if (params) {
        return Object.entries(params).reduce(
          (acc, [k, v]) => acc.replace(new RegExp(`\\{${k}\\}`, "g"), String(v)),
          text
        )
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
