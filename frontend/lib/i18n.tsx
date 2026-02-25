"use client"

import React, { createContext, useCallback, useContext, useEffect, useState } from "react"

export type Lang = "en" | "zh"

const STORAGE_KEY = "utrader_lang"

const translations: Record<string, { en: string; zh: string }> = {
  // Header
  "header.dashboard": { en: "Dashboard", zh: "儀表板" },
  "header.allCurrencies": { en: "All currencies", zh: "所有幣種" },
  "header.usd": { en: "USD", zh: "美元" },
  "header.proTrial": { en: "Pro Trial", zh: "專業試用" },
  "header.daysRemaining": { en: "days remaining", zh: "天剩餘" },
  "header.lendingLimit": { en: "Lending limit", zh: "出借限額" },
  "header.upgradeNow": { en: "Upgrade Now", zh: "立即升級" },
  "header.keepEarning": { en: "Keep earning interest -- subscribe now for unlimited lending and perks.", zh: "持續賺取利息——立即訂閱，享受無限出借與更多權益。" },
  "header.search": { en: "Search", zh: "搜尋" },
  "header.notifications": { en: "Notifications", zh: "通知" },
  "header.help": { en: "Help", zh: "說明" },
  "header.profile": { en: "Profile", zh: "個人資料" },
  "header.logout": { en: "Log out", zh: "登出" },
  "header.login": { en: "Log in", zh: "登入" },
  "header.langEn": { en: "EN", zh: "EN" },
  "header.langZh": { en: "中文", zh: "中文" },

  // Sidebar
  "sidebar.profitCenter": { en: "Profit Center", zh: "利潤中心" },
  "sidebar.liveStatus": { en: "Live Status", zh: "即時狀態" },
  "sidebar.trueRoi": { en: "True ROI", zh: "真實報酬率" },
  "sidebar.settings": { en: "Settings", zh: "設定" },
  "sidebar.logout": { en: "Logout", zh: "登出" },
  "sidebar.googleAccount": { en: "Google Account", zh: "Google 帳戶" },
  "sidebar.signIn": { en: "Sign in", zh: "登入" },

  // Settings
  "settings.title": { en: "Settings", zh: "設定" },
  "settings.accountMembership": { en: "Account & Membership", zh: "帳戶與會員" },
  "settings.accountMembershipDesc": { en: "Your current plan and account information", zh: "您目前的方案與帳戶資訊" },
  "settings.lendingLimit": { en: "Lending Limit", zh: "出借限額" },
  "settings.rebalancingFrequency": { en: "Rebalancing Frequency", zh: "再平衡頻率" },
  "settings.everyMinutes": { en: "Every {n} minutes", zh: "每 {n} 分鐘" },
  "settings.trialRemaining": { en: "Trial Remaining", zh: "試用剩餘" },
  "settings.days": { en: "days", zh: "天" },
  "settings.lendingUsage": { en: "Lending Usage", zh: "出借使用量" },
  "settings.tabs.lending": { en: "Lending", zh: "出借" },
  "settings.tabs.notifications": { en: "Notifications", zh: "通知" },
  "settings.tabs.apiKeys": { en: "API Keys", zh: "API 金鑰" },
  "settings.tabs.community": { en: "Community", zh: "社群" },

  // Login / Landing
  "login.signIn": { en: "Sign in", zh: "登入" },
  "login.continueWithGoogle": { en: "Continue with Google", zh: "使用 Google 繼續" },
  "login.freeToUse": { en: "Free to use", zh: "免費使用" },
  "login.secureOAuth": { en: "Secure OAuth", zh: "安全 OAuth" },
  "login.noDataStored": { en: "No data stored", zh: "不儲存資料" },
  "login.backToDashboard": { en: "Back to dashboard", zh: "返回儀表板" },

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
    const stored = localStorage.getItem(STORAGE_KEY) as Lang | null
    if (stored === "en" || stored === "zh") setLanguageState(stored)
    setMounted(true)
  }, [])

  const setLanguage = useCallback((lang: Lang) => {
    setLanguageState(lang)
    if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, lang)
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
