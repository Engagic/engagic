import React from 'react';

const MunicipalPipelineDiagram = () => {
  const vendors = [
    // Granicus family (5)
    { name: 'Legistar', owner: 'granicus', cities: ['NYC', 'Seattle', 'Boston'], more: 142, level: 'matter' },
    { name: 'PrimeGov', owner: 'granicus', cities: ['Los Angeles', 'Houston', 'Palo Alto'], more: 69, level: 'matter' },
    { name: 'Granicus', owner: 'granicus', cities: ['Redwood City'], more: 412, level: 'item' },
    { name: 'NovusAgenda', owner: 'granicus', cities: ['Plano', 'Hagerstown'], more: 63, level: 'item' },
    { name: 'IQM2', owner: 'granicus', cities: ['Buffalo', 'Miami', 'Atlanta'], more: 8, level: 'matter' },
    // CivicPlus family (2)
    { name: 'CivicPlus', owner: 'civicplus', cities: ['Ithaca', 'Provo'], more: 91, level: 'meeting' },
    { name: 'CivicClerk', owner: 'civicplus', cities: ['St. Louis', 'Sugar Land'], more: 17, level: 'matter' },
    // Independent (3)
    { name: 'eScribe', owner: 'other', cities: ['Raleigh', 'Detroit'], more: 4, level: 'matter' },
    { name: 'OnBase', owner: 'other', cities: ['San Diego', 'Tampa', 'Frisco'], more: 3, level: 'item' },
    { name: 'Municode', owner: 'other', cities: ['Columbus GA', 'Cedar Park'], more: 3, level: 'item' },
    // Custom (3)
    { name: 'Chicago', owner: 'custom', cities: ['Chicago'], more: 0, level: 'matter' },
    { name: 'Berkeley', owner: 'custom', cities: ['Berkeley'], more: 0, level: 'matter' },
    { name: 'Menlo Park', owner: 'custom', cities: ['Menlo Park'], more: 0, level: 'matter' },
  ];

  const ownerColors = {
    granicus: { line: '#a78bfa', bg: 'rgba(167, 139, 250, 0.08)', border: 'rgba(167, 139, 250, 0.3)' },
    civicplus: { line: '#60a5fa', bg: 'rgba(96, 165, 250, 0.08)', border: 'rgba(96, 165, 250, 0.3)' },
    other: { line: '#94a3b8', bg: 'rgba(148, 163, 184, 0.06)', border: 'rgba(148, 163, 184, 0.25)' },
    custom: { line: '#fbbf24', bg: 'rgba(251, 191, 36, 0.08)', border: 'rgba(251, 191, 36, 0.3)' },
  };

  const levelBadge = {
    matter: { label: 'M', color: '#10b981', title: 'Matter-level' },
    item: { label: 'I', color: '#3b82f6', title: 'Item-level' },
    meeting: { label: 'P', color: '#f59e0b', title: 'Packet-level' },
  };

  const ROW_HEIGHT = 40;
  const TOTAL_HEIGHT = ROW_HEIGHT * vendors.length;

  return (
    <div className="bg-slate-950 p-8 min-h-screen" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* Title */}
      <div className="text-center mb-10">
        <h1 className="text-2xl font-semibold text-white tracking-tight">
          13 Adapters. 2 Companies. 841 Cities.
        </h1>
        <p className="text-slate-500 text-sm mt-2">
          A universal integration layer for municipal government platforms
        </p>
      </div>

      {/* Main diagram */}
      <div className="flex items-start justify-center">

        {/* Cities column */}
        <div className="flex flex-col">
          <div className="text-slate-600 text-[10px] uppercase tracking-widest mb-3 h-4 text-right pr-3">
            Sources
          </div>
          {vendors.map((v) => (
            <div
              key={v.name}
              className="flex items-center justify-end pr-3"
              style={{ height: ROW_HEIGHT }}
            >
              <div className="text-right">
                <div className="text-slate-400 text-[11px] leading-snug">
                  {v.cities.join(', ')}
                </div>
                {v.more > 0 && (
                  <div className="text-slate-600 text-[10px]">
                    +{v.more} more
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Connector: Cities to Adapters */}
        <div className="flex flex-col">
          <div className="h-4 mb-3" />
          {vendors.map((v) => (
            <div key={v.name} className="flex items-center" style={{ height: ROW_HEIGHT }}>
              <svg width="32" height={ROW_HEIGHT}>
                <line
                  x1="0" y1={ROW_HEIGHT / 2}
                  x2="32" y2={ROW_HEIGHT / 2}
                  stroke={ownerColors[v.owner].line}
                  strokeWidth="1"
                  opacity="0.5"
                />
                <circle
                  cx="32" cy={ROW_HEIGHT / 2} r="2"
                  fill={ownerColors[v.owner].line}
                  opacity="0.6"
                />
              </svg>
            </div>
          ))}
        </div>

        {/* Adapters column */}
        <div className="flex flex-col">
          <div className="text-slate-600 text-[10px] uppercase tracking-widest mb-3 h-4 text-center">
            Adapters
          </div>
          {vendors.map((v) => {
            const colors = ownerColors[v.owner];
            const badge = levelBadge[v.level];
            return (
              <div key={v.name} className="flex items-center" style={{ height: ROW_HEIGHT }}>
                <div
                  className="relative flex items-center justify-center text-[11px] font-medium px-3 py-1 rounded-sm"
                  style={{
                    minWidth: 90,
                    color: colors.line,
                    backgroundColor: colors.bg,
                    border: `1px solid ${colors.border}`,
                  }}
                >
                  {v.name}
                  <span
                    className="absolute -right-1 -top-1 w-3.5 h-3.5 rounded-full text-[7px] font-bold flex items-center justify-center"
                    style={{ backgroundColor: badge.color, color: '#0f172a' }}
                    title={badge.title}
                  >
                    {badge.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Connector: Adapters to Brace */}
        <div className="flex flex-col">
          <div className="h-4 mb-3" />
          {vendors.map((v) => (
            <div key={v.name} className="flex items-center" style={{ height: ROW_HEIGHT }}>
              <svg width="16" height={ROW_HEIGHT}>
                <line
                  x1="0" y1={ROW_HEIGHT / 2}
                  x2="16" y2={ROW_HEIGHT / 2}
                  stroke="#334155"
                  strokeWidth="1"
                />
              </svg>
            </div>
          ))}
        </div>

        {/* Curly brace */}
        <div className="flex flex-col">
          <div className="h-4 mb-3" />
          <svg width="20" height={TOTAL_HEIGHT} className="overflow-visible">
            <path
              d={`
                M 2 4
                C 10 4, 10 ${TOTAL_HEIGHT / 2 - 20}, 10 ${TOTAL_HEIGHT / 2 - 8}
                L 10 ${TOTAL_HEIGHT / 2 - 4}
                C 10 ${TOTAL_HEIGHT / 2}, 14 ${TOTAL_HEIGHT / 2}, 18 ${TOTAL_HEIGHT / 2}
                C 14 ${TOTAL_HEIGHT / 2}, 10 ${TOTAL_HEIGHT / 2}, 10 ${TOTAL_HEIGHT / 2 + 4}
                L 10 ${TOTAL_HEIGHT / 2 + 8}
                C 10 ${TOTAL_HEIGHT / 2 + 20}, 10 ${TOTAL_HEIGHT - 4}, 2 ${TOTAL_HEIGHT - 4}
              `}
              stroke="#10b981"
              strokeWidth="2"
              fill="none"
              strokeLinecap="round"
            />
          </svg>
        </div>

        {/* Arrow to unified model */}
        <div className="flex items-center" style={{ height: TOTAL_HEIGHT, marginTop: 28 }}>
          <svg width="36" height="20" className="mx-1">
            <line x1="0" y1="10" x2="24" y2="10" stroke="#10b981" strokeWidth="2" />
            <path d="M20 5 L28 10 L20 15" stroke="#10b981" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* Unified Model box */}
        <div className="flex items-center" style={{ height: TOTAL_HEIGHT, marginTop: 28 }}>
          <div className="border border-emerald-700/50 bg-emerald-950/30 rounded px-5 py-4">
            <div className="text-emerald-500 text-[10px] uppercase tracking-widest mb-3 text-center font-medium">
              Unified Model
            </div>
            <div className="space-y-2">
              {[
                { label: 'Cities', value: '841' },
                { label: 'Meetings', value: '5,781' },
                { label: 'Items', value: '58,263' },
                { label: 'Matters', value: '24,195' },
              ].map((stat) => (
                <div key={stat.label} className="flex justify-between items-baseline gap-6">
                  <span className="text-slate-500 text-[11px]">{stat.label}</span>
                  <span className="text-white text-sm font-semibold tabular-nums">{stat.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Arrow to output */}
        <div className="flex items-center" style={{ height: TOTAL_HEIGHT, marginTop: 28 }}>
          <svg width="36" height="20" className="mx-1">
            <line x1="0" y1="10" x2="24" y2="10" stroke="#6366f1" strokeWidth="2" />
            <path d="M20 5 L28 10 L20 15" stroke="#6366f1" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* Output box */}
        <div className="flex items-center" style={{ height: TOTAL_HEIGHT, marginTop: 28 }}>
          <div className="border border-indigo-600/40 bg-indigo-950/20 rounded px-5 py-4">
            <div className="text-indigo-400 text-[10px] uppercase tracking-widest mb-3 text-center font-medium">
              API + Frontend
            </div>
            <div className="text-center">
              <div className="text-white text-sm font-semibold leading-tight">
                Municipal<br />Intelligence
              </div>
              <div className="text-slate-500 text-[10px] mt-2 leading-relaxed">
                Structured legislative<br />data at civic scale
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex justify-center gap-5 mt-8 flex-wrap">
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ownerColors.granicus.line }} />
            <span className="text-slate-500 text-[10px]">Granicus (5)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ownerColors.civicplus.line }} />
            <span className="text-slate-500 text-[10px]">CivicPlus (2)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ownerColors.other.line }} />
            <span className="text-slate-500 text-[10px]">Independent (3)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ownerColors.custom.line }} />
            <span className="text-slate-500 text-[10px]">Custom (3)</span>
          </div>
        </div>
        <div className="h-3 w-px bg-slate-700" />
        <div className="flex items-center gap-3">
          {Object.entries(levelBadge).map(([level, badge]) => (
            <div key={level} className="flex items-center gap-1">
              <span
                className="w-3.5 h-3.5 rounded-full text-[7px] font-bold flex items-center justify-center"
                style={{ backgroundColor: badge.color, color: '#0f172a' }}
              >
                {badge.label}
              </span>
              <span className="text-slate-500 text-[10px]">{badge.title}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="text-center mt-5 text-slate-600 text-[10px]">
        10 platform adapters + 3 custom scrapers for bespoke city portals
      </div>
    </div>
  );
};

export default MunicipalPipelineDiagram;
