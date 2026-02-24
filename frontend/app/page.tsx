"use client";
import React, { useState, useEffect } from 'react';
import { Activity, ShieldCheck, Cpu, ArrowUpRight, Globe, Layers } from 'lucide-react';

export default function UTraderDashboard() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8000/bot-stats/1');
        const result = await response.json();
        if (result.active) setData(result);
      } catch (e) { console.error("utrader.io uplink error:", e); }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-slate-300 font-sans selection:bg-emerald-500/30">
      {/* Institutional Top Bar */}
      <nav className="border-b border-white/5 bg-[#0a0a0b]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex justify-between items-center">
          <div className="flex items-center gap-8">
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <div className="w-6 h-6 bg-emerald-500 rounded-sm flex items-center justify-center">
                <div className="w-2 h-2 bg-black rotate-45" />
              </div>
              utrader<span className="text-emerald-500">.io</span>
            </h1>
            <div className="hidden md:flex gap-6 text-xs font-medium text-slate-500 uppercase tracking-widest">
              <span className="text-emerald-500 border-b border-emerald-500 pb-5 mt-5">Terminal</span>
              <span className="hover:text-slate-300 cursor-pointer">Security</span>
              <span className="hover:text-slate-300 cursor-pointer">API</span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-[10px] font-mono">
            <div className="flex items-center gap-2 px-3 py-1 bg-white/5 rounded-full border border-white/10">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-slate-400">NODE_B_01: ACTIVE</span>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto p-6 lg:p-10">
        {/* Core Metrics: The "Decision Clarity" Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
          <MetricBlock 
            label="Avg. Yield (WAROC)" 
            value={data?.engines[0]?.waroc || "0.00%"} 
            sub="365D Projected" 
            icon={<Activity size={16} className="text-emerald-500" />}
          />
          <MetricBlock 
            label="Capital Deployed" 
            value={`$${data?.total_loaned || "0.00"}`} 
            sub="Live Exchange Exposure" 
            icon={<Layers size={16} className="text-blue-500" />}
          />
          <MetricBlock 
            label="Vault Efficiency" 
            value={data?.engines[0]?.utilization || "0.0%"} 
            sub="Current Utilization" 
            icon={<Cpu size={16} className="text-purple-500" />}
          />
        </div>

        {/* Engine Details */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-[#111113] border border-white/5 rounded-xl p-8">
              <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-2 uppercase tracking-wider">
                Active Provisioning Engines
              </h3>
              <div className="space-y-4">
                {data?.engines.map((e: any, i: number) => (
                  <EngineRow key={i} asset={e.asset} apr={e.waroc} market={e.market_apr} />
                ))}
              </div>
            </div>
          </div>

          {/* Security & System Info */}
          <div className="space-y-6">
            <div className="bg-[#111113] border border-white/5 rounded-xl p-6">
              <div className="flex items-center gap-2 text-white mb-4">
                <ShieldCheck size={18} className="text-emerald-500" />
                <h4 className="text-sm font-bold uppercase tracking-tight">System Integrity</h4>
              </div>
              <div className="space-y-3 text-[11px] font-mono text-slate-500">
                <div className="flex justify-between border-b border-white/5 pb-2">
                  <span>ENCRYPTION</span>
                  <span className="text-white">AES-256-GCM</span>
                </div>
                <div className="flex justify-between border-b border-white/5 pb-2">
                  <span>STORAGE</span>
                  <span className="text-white">NEON_POSTGRES</span>
                </div>
                <div className="flex justify-between border-b border-white/5 pb-2">
                  <span>LATENCY</span>
                  <span className="text-white">~14ms</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function MetricBlock({ label, value, sub, icon }: any) {
  return (
    <div className="bg-[#111113] border border-white/5 p-8 rounded-xl relative overflow-hidden group hover:border-white/10 transition-all">
      <div className="flex justify-between items-start mb-4">
        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em]">{label}</span>
        {icon}
      </div>
      <div className="text-4xl font-bold text-white tracking-tight mb-2">{value}</div>
      <div className="text-xs text-slate-600">{sub}</div>
    </div>
  );
}

function EngineRow({ asset, apr, market }: any) {
  return (
    <div className="flex items-center justify-between p-5 bg-black/20 rounded-lg border border-white/5 hover:bg-black/40 transition-all">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 bg-emerald-500/10 rounded flex items-center justify-center font-bold text-emerald-500">
          {asset[0]}
        </div>
        <div>
          <div className="text-white font-bold">{asset}_OMNI_V2</div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">Predator Matrix Mode</div>
        </div>
      </div>
      <div className="text-right">
        <div className="text-xl font-bold text-white">{apr} <span className="text-[10px] text-slate-500">APR</span></div>
        <div className="text-[10px] text-emerald-500/80 font-mono">Market FRR: {market}</div>
      </div>
    </div>
  );
}