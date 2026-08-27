import { useState, useRef, useEffect } from 'react';
import { Send, LogOut, Plus, PlaneTakeoff, Plane, Fuel, FileText, BarChart2, MessageSquare, ChevronDown, Layers, PanelLeftClose, PanelLeftOpen, MoreVertical, Trash2 } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface ChatProps {
  sessionId: string;
  onLogout: () => void;
  onActivity: () => void;
  onNewChat: (newSessionId: string) => void;  // Chat.tsx owns session creation; passes ID up
  onSwitchSession: (id: string) => void;
}

interface TodoItem {
  id: number;
  title: string;
  description?: string;
  completed?: boolean;
  reason?: string;
}

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'assistant';
  todos?: TodoItem[];
  toolCalls?: string[];
  mode?: 'reasoning' | 'fast';
}

interface SessionMeta {
  id: string;
  title: string;
  agent_key?: AgentKey;
  agent_name?: string;
  titles?: Partial<Record<AgentKey, string>>;
  updatedAt: number;
}

// TypewriterText removed in favor of native SSE streaming

const formatMarkdown = (text: string) => {
  const formatInline = (str: string) => {
    const lines = str.split('\n');
    return lines.map((line, idx) => {
      let isHeader = false;
      let headerLevel = 0;
      let isList = false;

      const headerMatch = line.match(/^(#{1,6})\s/);
      if (headerMatch) {
        isHeader = true;
        headerLevel = headerMatch[1].length;
        line = line.substring(headerLevel + 1).trim();
      } else if (line.trim().match(/^[-*]\s/)) {
        isList = true;
        line = line.trim().substring(2);
      }

      const parts = line.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
      const formattedLine = parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i} style={{ color: '#fff', fontWeight: 600 }}>{part.slice(2, -2)}</strong>;
        } else if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
          return <em key={i} style={{ fontStyle: 'italic', color: '#e2e8f0' }}>{part.slice(1, -1)}</em>;
        } else if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
          return <code key={i} style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 5px', borderRadius: '4px', fontSize: '0.85em', color: '#38bdf8' }}>{part.slice(1, -1)}</code>;
        }
        return part;
      });

      if (isHeader) {
        const fontSizes = ['1.5rem', '1.25rem', '1.1rem', '1rem', '0.9rem', '0.85rem'];
        return (
          <div key={idx} style={{ color: '#fff', fontSize: fontSizes[headerLevel - 1], fontWeight: 600, marginTop: '1.25rem', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            {formattedLine}
          </div>
        );
      }

      if (isList) {
        return (
          <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '0.3rem', paddingLeft: '0.5rem' }}>
            <span style={{ color: '#94a3b8' }}>•</span>
            <span style={{ flex: 1 }}>{formattedLine}</span>
          </div>
        );
      }

      return (
        <span key={idx}>
          {formattedLine}
          {idx < lines.length - 1 ? '\n' : ''}
        </span>
      );
    });
  };

  const lines = text.split('\n');
  const blocks: JSX.Element[] = [];
  let currentTable: string[] = [];
  let nonTableText: string[] = [];

  const renderTable = (tableLines: string[], key: number) => {
    if (tableLines.length < 2) {
      return <span key={key}>{formatInline(tableLines.join('\n'))}</span>;
    }

    const parseRow = (row: string) => row.split('|').map(c => c.trim()).filter((_, i, arr) => !(i === 0 && arr[0] === '') && !(i === arr.length - 1 && arr[arr.length - 1] === ''));

    const headers = parseRow(tableLines[0]);
    const rows = tableLines.slice(2).map(parseRow);

    return (
      <div key={key} style={{ overflowX: 'auto', margin: '0.75rem 0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #334155' }}>
              {headers.map((h, i) => (
                <th key={i} style={{ textAlign: 'left', padding: '6px 10px', color: '#94a3b8', fontWeight: 600 }}>{formatInline(h)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #1e293b' }}>
                {row.map((cell, j) => (
                  <td key={j} style={{ padding: '6px 10px' }}>{formatInline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  lines.forEach((line, i) => {
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      if (nonTableText.length > 0) {
        blocks.push(<span key={`text-${i}`}>{formatInline(nonTableText.join('\n') + '\n')}</span>);
        nonTableText = [];
      }
      currentTable.push(line);
    } else {
      if (currentTable.length > 0) {
        blocks.push(renderTable(currentTable, i));
        currentTable = [];
      }
      nonTableText.push(line);
    }
  });

  if (currentTable.length > 0) {
    blocks.push(renderTable(currentTable, lines.length));
  }
  if (nonTableText.length > 0) {
    blocks.push(<span key="text-end">{formatInline(nonTableText.join('\n'))}</span>);
  }

  return <>{blocks}</>;
};

const TextBlock = ({ content }: { content: string }) => {
  return <div style={{ whiteSpace: 'pre-wrap' }}>{formatMarkdown(content)}</div>;
};

const CHART_COLORS = ['#65a30d', '#a3e635', '#bef264', '#4ade80', '#86efac', '#4d7c0f', '#d9f99d', '#ecfccb'];

// Pulls a short unit token (e.g. "$", "L", "%", "kg") out of a label/description
// like "Total Contract Value ($)" or "measured in Litres (L)." — returns undefined
// if nothing recognizable is found.
const extractUnit = (...texts: (string | undefined)[]): string | undefined => {
  for (const text of texts) {
    if (!text) continue;
    const matches = [...text.matchAll(/\(([$€£%A-Za-z]{1,6})\)/g)];
    if (matches.length > 0) return matches[matches.length - 1][1];
  }
  return undefined;
};

// Formats a number for chart axes/tooltips using the metric's actual unit — never
// assumes currency. `unit` of "$" is prefixed, any other unit (e.g. "L", "%") is
// suffixed, and no unit at all just shows the plain number.
const formatVal = (v: number, unit?: string) => {
  const isCurrency = unit === '$';
  const abbrev = v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M`
    : v >= 1_000 ? `${(v / 1_000).toFixed(1)}k`
      : v.toLocaleString();
  if (isCurrency) return `$${abbrev}`;
  if (unit) return `${abbrev} ${unit}`;
  return abbrev;
};

const BarChartSVG = ({ data, xLabel, yLabel, unit }: { data: { name: string, value: number }[], xLabel?: string, yLabel?: string, unit?: string }) => {
  const outerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number, y: number, item: any } | null>(null);
  const maxVal = Math.max(...data.map(d => d.value));
  const chartH = 200;
  const paddingL = 60;
  const paddingB = 60;
  const paddingR = 20;

  // Give every bar a fixed, always-readable width instead of squeezing
  // narrower as more categories are added. With many categories (e.g. a
  // 24-month trend), the chart's own coordinate space (chartW) grows to fit
  // them all, and the outer wrapper scrolls horizontally rather than
  // clipping/overflowing — previously bars were forced into a fixed
  // 640-unit canvas with `overflow: visible`, so once there were enough
  // categories that even the 20px floor no longer fit, bars (and the
  // tooltip) were laid out past x=640 and rendered outside the chart's own
  // box entirely, bleeding past the card and even the chat bubble.
  const barW = 28;
  const barGap = 14;
  const contentW = data.length * (barW + barGap) - barGap;
  const chartW = Math.max(560, paddingL + contentW + paddingR);
  const svgH = chartH + paddingB + 20;

  // Position the tooltip relative to the *visible* (possibly scrollable)
  // container, using getBoundingClientRect rather than viewport coordinates
  // — immune to any ancestor transform, and clamped so it can never render
  // outside the visible chart area even near the right edge.
  const showTooltip = (e: React.MouseEvent, item: any) => {
    const rect = outerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width - 150));
    setTooltip({ x, y: e.clientY - rect.top, item });
  };

  return (
    <div ref={outerRef} style={{ position: 'relative', overflowX: 'auto' }}>
      <svg width={chartW} height={svgH} viewBox={`0 0 ${chartW} ${svgH}`} style={{ display: 'block' }}>
        {/* Y axis label */}
        {yLabel && <text x="12" y={(chartH + paddingB) / 2} transform={`rotate(-90, 12, ${(chartH + paddingB) / 2})`} textAnchor="middle" fontSize="10" fill="#64748b">{yLabel}</text>}

        {/* Y gridlines + ticks */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = 10 + chartH * (1 - pct);
          return (
            <g key={pct}>
              <line x1={paddingL} x2={chartW - paddingR} y1={y} y2={y} stroke="#1e293b" strokeWidth="1" />
              <text x={paddingL - 6} y={y + 4} textAnchor="end" fontSize="9" fill="#64748b">{formatVal(maxVal * pct, unit)}</text>
            </g>
          );
        })}

        {/* Bars */}
        {data.map((d, i) => {
          const barH = Math.max(2, (d.value / maxVal) * chartH);
          const x = paddingL + i * (barW + barGap);
          const y = 10 + chartH - barH;
          return (
            <g key={i}
              onMouseEnter={(e) => showTooltip(e, d)}
              onMouseMove={(e) => showTooltip(e, d)}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: 'pointer' }}
            >
              <rect x={x} y={y} width={barW} height={barH} rx="3" fill={CHART_COLORS[i % CHART_COLORS.length]} opacity="0.9" />
              <text
                x={x + barW / 2}
                y={chartH + paddingB - 4}
                textAnchor="middle"
                fontSize="9"
                fill="#94a3b8"
                transform={data.length > 6 ? `rotate(-35, ${x + barW / 2}, ${chartH + paddingB - 4})` : ''}
              >
                {d.name.length > 12 ? d.name.slice(0, 11) + '…' : d.name}
              </text>
            </g>
          );
        })}

        {/* X axis */}
        <line x1={paddingL} x2={chartW - paddingR} y1={chartH + 10} y2={chartH + 10} stroke="#334155" strokeWidth="1" />
        {xLabel && <text x={(paddingL + chartW - paddingR) / 2} y={chartH + paddingB + 14} textAnchor="middle" fontSize="10" fill="#64748b">{xLabel}</text>}
      </svg>
      {tooltip && (
        <div style={{
          position: 'absolute', left: tooltip.x + 12, top: tooltip.y - 36,
          background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px',
          padding: '6px 10px', color: '#fff', fontSize: '12px', pointerEvents: 'none', zIndex: 999, whiteSpace: 'nowrap'
        }}>
          <strong>{tooltip.item.name}</strong>: {formatVal(tooltip.item.value, unit)}
        </div>
      )}
    </div>
  );
};

const PieChartSVG = ({ data, unit }: { data: { name: string, value: number, percentage?: number }[], unit?: string }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number, y: number, item: any } | null>(null);
  const total = data.reduce((s, d) => s + d.value, 0);
  const cx = 130, cy = 110, r = 80, ri = 50;
  let angle = -Math.PI / 2;

  const slices = data.map((d, i) => {
    const pct = d.value / total;
    const startAngle = angle;
    angle += pct * Math.PI * 2;
    const endAngle = angle;
    const x1 = cx + r * Math.cos(startAngle), y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle), y2 = cy + r * Math.sin(endAngle);
    const xi1 = cx + ri * Math.cos(startAngle), yi1 = cy + ri * Math.sin(startAngle);
    const xi2 = cx + ri * Math.cos(endAngle), yi2 = cy + ri * Math.sin(endAngle);
    const large = pct > 0.5 ? 1 : 0;
    return { d: `M ${xi1} ${yi1} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} L ${xi2} ${yi2} A ${ri} ${ri} 0 ${large} 0 ${xi1} ${yi1} Z`, color: CHART_COLORS[i % CHART_COLORS.length], item: d, pct };
  });

  // See BarChartSVG's showTooltip comment — same fix, container-relative
  // instead of viewport-fixed, so it's immune to ancestor transforms.
  const showTooltip = (e: React.MouseEvent, item: any) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, item });
  };

  return (
    <div ref={containerRef} style={{ position: 'relative', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <svg width="260" height="220" style={{ flexShrink: 0, overflow: 'visible' }}>
        {slices.map((s, i) => (
          <path key={i} d={s.d} fill={s.color} stroke="#0f172a" strokeWidth="2"
            style={{ cursor: 'pointer', transition: 'opacity 0.15s' }}
            onMouseEnter={(e) => showTooltip(e, s.item)}
            onMouseMove={(e) => showTooltip(e, s.item)}
            onMouseLeave={() => setTooltip(null)}
          />
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="11" fill="#94a3b8">Total</text>
        <text x={cx} y={cy + 10} textAnchor="middle" fontSize="13" fontWeight="bold" fill="#fff">{formatVal(total, unit)}</text>
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: '160px' }}>
        {data.map((d, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
            <div style={{ width: 10, height: 10, borderRadius: '2px', background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0 }} />
            <span style={{ color: '#94a3b8', flex: 1 }}>{d.name}</span>
            <span style={{ color: '#fff', fontWeight: 600 }}>{((d.value / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
      {tooltip && (
        <div style={{
          position: 'absolute', left: tooltip.x + 12, top: tooltip.y - 36,
          background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px',
          padding: '6px 10px', color: '#fff', fontSize: '12px', pointerEvents: 'none', zIndex: 999, whiteSpace: 'nowrap'
        }}>
          <strong>{tooltip.item.name}</strong>: {formatVal(tooltip.item.value, unit)}
        </div>
      )}
    </div>
  );
};

const ChartRenderer = ({ data }: { data: any }) => {
  if (!data || !data.type || !Array.isArray(data.data) || data.data.length === 0) return null;

  // Prefer an explicit "unit" field from the agent; otherwise infer it from the
  // label/description text (e.g. "(L)", "($)"); default to "$" only as a last
  // resort so existing money-based charts keep working unchanged.
  const unit = data.unit || extractUnit(data.y_label, data.description, data.title) || '$';

  return (
    <div style={{ width: '100%', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '0.75rem', marginTop: '1rem', border: '1px solid var(--border)' }}>
      <h4 style={{ margin: '0 0 0.25rem', color: '#fff', fontSize: '0.95rem', fontWeight: 600 }}>{data.title}</h4>
      {data.description && <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0 0 1rem' }}>{data.description}</p>}
      {data.type === 'bar'
        ? <BarChartSVG data={data.data} xLabel={data.x_label} yLabel={data.y_label} unit={unit} />
        : <PieChartSVG data={data.data} unit={unit} />
      }
    </div>
  );
};

interface ReasoningStep {
  type: 'text' | 'tool_call' | 'tool_result';
  text?: string;
  name?: string;
  summary?: string;
}

const parseReasoning = (content: string): ReasoningStep[] => {
  const steps: ReasoningStep[] = [];
  const regex = /<tool_call name="([^"]+)" \/>|<tool_result summary="([^"]+)" \/>/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    const textSegment = content.slice(lastIndex, match.index).trim();
    if (textSegment) {
      steps.push({ type: 'text', text: textSegment });
    }

    if (match[1]) {
      const toolName = match[1];
      const lastStep = steps[steps.length - 1];
      // Deduplicate consecutive identical tool calls
      if (!lastStep || lastStep.type !== 'tool_call' || lastStep.name !== toolName) {
        steps.push({ type: 'tool_call', name: toolName });
      }
    } else if (match[2]) {
      steps.push({ type: 'tool_result', summary: match[2] });
    }

    lastIndex = regex.lastIndex;
  }

  const finalSegment = content.slice(lastIndex).trim();
  if (finalSegment) {
    steps.push({ type: 'text', text: finalSegment });
  }

  return steps;
};

const TOOL_LABELS: Record<string, { title: string, desc: string, defaultReasoning: string }> = {
  resolve_entity: {
    title: 'Entity Resolution & Canonical Matching',
    desc: 'Match entity terms against database index',
    defaultReasoning: 'Executing entity resolution across the database index to normalize entity names, airline codes, client descriptors, and categories against authoritative canonical database entities. This ensures exact matching and eliminates categorical ambiguity before SQL generation.'
  },
  lookup_glossary_term: {
    title: 'Business Glossary Mapping',
    desc: 'Map operational terms to database fields',
    defaultReasoning: 'Consulting the business glossary to map user-facing business and operational terminology into their approved underlying database tables and column definitions.'
  },
  lookup_metric: {
    title: 'Metric Pattern Resolution',
    desc: 'Retrieve pre-approved SQL aggregate pattern',
    defaultReasoning: 'Resolving metric definition from the centralized metric store to retrieve pre-approved SQL aggregation formulas and filtering logic. This guarantees analytical consistency and prevents divergent metric definitions across queries.'
  },
  search_schema_graph: {
    title: 'Knowledge Graph Schema Search',
    desc: 'Find relevant tables and join paths',
    defaultReasoning: 'Querying the knowledge graph to identify relevant tables, columns, and join relationships needed for the query. This provides join-aware schema discovery with relationship context.'
  },
  get_table_schema: {
    title: 'Table Schema Retrieval',
    desc: 'Retrieve column data types and constraints',
    defaultReasoning: 'Inspecting full schema definitions, primary keys, and column constraints for relevant database tables to ensure accurate join predicates, type safety, and column compatibility in SQL construction.'
  },
  list_tables: {
    title: 'Database Table Enumeration',
    desc: 'Enumerate accessible database tables',
    defaultReasoning: 'Retrieving accessible relational tables from the database catalog to verify table availability and establish the correct source entities for query execution.'
  },
  search_example_sql: {
    title: 'Historical SQL Pattern Retrieval',
    desc: 'Fetch reference past query patterns',
    defaultReasoning: 'Querying example vector repository to retrieve verified, high-confidence historical SQL patterns and domain-specific query templates that align with the user question intent.'
  },
  validate_sql: {
    title: 'SQL Safety & Syntax Validation',
    desc: 'Validate syntax, safety, and table relationships',
    defaultReasoning: 'Executing rigorous automated syntax, relationship, and security validation on the constructed SQL query. Verifies table aliases, join criteria, aggregate clauses, and read-only safety prior to execution.'
  },
  run_sql: {
    title: 'Database Query Execution',
    desc: 'Execute query on active database warehouse',
    defaultReasoning: 'Executing the validated, optimized read-only SQL query against the active database warehouse to retrieve actual rows and aggregate metrics for synthesis.'
  },
  get_contract_document: {
    title: 'Contract Document Retrieval',
    desc: 'Fetch full document text for clause check',
    defaultReasoning: 'Retrieving full contract legal document text to perform clause extraction, verify specific terms, and validate contractual obligations directly against primary contract sources.'
  },
  find_query_function: {
    title: 'Pre-Built Function Matching',
    desc: 'Check for a pre-approved query function',
    defaultReasoning: 'Searching the pre-built function catalog to check whether this question is already covered by a pre-approved, reviewed query function before falling back to schema search and manual SQL generation. This can skip the schema/SQL pipeline entirely when a confident match exists.'
  },
  run_query_function: {
    title: 'Query Function Execution',
    desc: 'Run the matched pre-approved function',
    defaultReasoning: 'Executing the matched pre-built query function with the resolved parameter values. Since the underlying SQL is fixed and already reviewed, this guarantees a correct join/aggregation without any risk of a hallucinated query.'
  },
};

interface ExecutionStepItem {
  id: number;
  title: string;
  description?: string;
  completed: boolean;
  reasoningText?: string;
}

const buildExecutionTimeline = (content: string, isStreaming?: boolean, todos?: TodoItem[], toolCalls?: string[]): ExecutionStepItem[] => {
  if (!content && (!todos || todos.length === 0) && (!toolCalls || toolCalls.length === 0)) return [];

  const rawSteps = parseReasoning(content);
  const items: ExecutionStepItem[] = [];
  let id = 1;

  if (rawSteps.length > 0) {
    for (let i = 0; i < rawSteps.length; i++) {
      const step = rawSteps[i];

      if (step.type === 'text') {
        const isFirst = items.length === 0;
        const isLast = (i === rawSteps.length - 1);

        let title = isFirst
          ? 'Intent Classification & Strategy'
          : (isLast && !isStreaming ? 'Result Analysis & Validation' : 'Execution Reasoning & Next Steps');

        items.push({
          id: id++,
          title,
          description: isFirst ? 'Identify user inquiry goals and extract relevant business terms' : undefined,
          completed: true,
          reasoningText: step.text,
        });
      } else if (step.type === 'tool_call' && step.name) {
        const meta = TOOL_LABELS[step.name] || {
          title: `Execute ${step.name}`,
          desc: `Perform ${step.name} database operation`,
          defaultReasoning: `Executing ${step.name} operation against the system to retrieve required analytical context and schema definitions.`
        };

        // Attach subsequent text segment if available; otherwise use rich default reasoning (50+ words)
        let reasoningText = meta.defaultReasoning;
        if (i + 1 < rawSteps.length && rawSteps[i + 1].type === 'text') {
          reasoningText = rawSteps[i + 1].text || meta.defaultReasoning;
          i++; // advance index
        }

        items.push({
          id: id++,
          title: meta.title,
          description: meta.desc,
          completed: true,
          reasoningText,
        });
      }
    }
  } else if (toolCalls && toolCalls.length > 0) {
    toolCalls.forEach(tool => {
      const meta = TOOL_LABELS[tool] || {
        title: `Execute ${tool}`,
        desc: `Perform ${tool} database operation`,
        defaultReasoning: `Executing ${tool} operation against the system to retrieve required analytical context.`
      };
      items.push({
        id: id++,
        title: meta.title,
        description: meta.desc,
        completed: true,
        reasoningText: meta.defaultReasoning,
      });
    });
  } else if (content) {
    items.push({
      id: id++,
      title: 'Intent Classification & Reasoning',
      completed: true,
      reasoningText: content,
    });
  }

  // If streaming is complete and we had tools, add final synthesis step if not already present
  const hasSynthesis = items.some(it => it.title.includes('Synthesis'));
  if (!isStreaming && items.length > 1 && !hasSynthesis) {
    items.push({
      id: id++,
      title: 'Result Synthesis & Output',
      description: 'Synthesized SQL query results into structured final answer',
      completed: true,
      reasoningText: 'Analyzing retrieved query results, computing summary aggregates, and formatting output insights with clear conversational presentation and supporting visualizations.',
    });
  }

  return items;
};

const ReasoningBlock = ({ content, isStreaming, todos, toolCalls }: { content: string, isStreaming?: boolean, todos?: TodoItem[], toolCalls?: string[] }) => {
  const [isOpen, setIsOpen] = useState(false);

  const timelineItems = buildExecutionTimeline(content, isStreaming, todos, toolCalls);

  return (
    <div className="reasoning-custom-block">
      <div
        className="reasoning-custom-header"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="reasoning-title">Thought process</span>
        <svg
          className={`reasoning-icon ${isOpen ? 'open' : ''}`}
          width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </div>

      {isOpen && (
        <div className="reasoning-content fade-in" style={{ padding: '0.85rem 1rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {timelineItems.map((task) => (
              <div
                key={task.id}
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  border: '1px solid rgba(56, 189, 248, 0.22)',
                  borderLeft: `4px solid ${task.completed ? '#10b981' : '#38bdf8'}`,
                  borderRadius: '8px',
                  padding: '0.75rem 0.95rem',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <div style={{ color: task.completed ? '#10b981' : '#38bdf8', display: 'flex', alignItems: 'center' }}>
                    {task.completed ? (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    ) : (
                      <div style={{ width: '10px', height: '10px', borderRadius: '50%', border: '2px solid #38bdf8' }} />
                    )}
                  </div>

                  <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#f1f5f9' }}>
                    {task.title}
                  </div>

                  {task.description && (
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8', marginLeft: 'auto' }}>
                      {task.description}
                    </span>
                  )}
                </div>

                {task.reasoningText && (
                  <div style={{
                    fontSize: '0.86rem',
                    lineHeight: 1.6,
                    color: '#cbd5e1',
                    paddingLeft: '24px',
                    marginTop: '6px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                    paddingTop: '6px',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {formatMarkdown(task.reasoningText)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// Ephemeral rotating status label shown in Fast mode while tools are
// running (nothing persists once the real answer starts streaming in) —
// replaces the "Thought process" panel without exposing chips or narration.
const FAST_STATUS_VERBS: Record<string, string> = {
  resolve_entity: 'Resolving entities',
  lookup_glossary_term: 'Mapping business terms',
  lookup_metric: 'Retrieving metric definitions',
  search_schema_graph: 'Searching schema graph',
  get_table_schema: 'Reading table structure',
  list_tables: 'Discovering tables',
  search_example_sql: 'Checking similar queries',
  validate_sql: 'Validating query',
  run_sql: 'Running query',
  get_contract_document: 'Reading document',
  find_query_function: 'Searching for a matching function',
  run_query_function: 'Running matched function',
};

const StatusDots = ({ toolCalls }: { toolCalls?: string[] }) => {
  const last = toolCalls && toolCalls.length > 0 ? toolCalls[toolCalls.length - 1] : null;
  const label = last ? (FAST_STATUS_VERBS[last] || 'Working') : 'Thinking';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#94a3b8', fontSize: '0.85rem', padding: '2px 0' }}>
      <span>{label}</span>
      <span className="status-dots">
        <span>.</span><span>.</span><span>.</span>
      </span>
    </div>
  );
};

const MessageFormatter = ({ text, isStreaming, todos, toolCalls, mode }: { text: string, isStreaming?: boolean, todos?: TodoItem[], toolCalls?: string[], mode?: 'reasoning' | 'fast' }) => {
  const regex = /(?:<(think|thought|reasoning)>([\s\S]*?)<\/\1>)|(?:```(reasoning|thought)\n([\s\S]*?)```)/gi;

  let combinedReasoning = '';
  let match;

  // Extract and combine all reasoning content
  while ((match = regex.exec(text)) !== null) {
    const content = match[2] || match[4];
    if (combinedReasoning) combinedReasoning += '\n\n';
    combinedReasoning += content.trim();
  }

  // Remove all reasoning blocks from the text to get the final answer
  let remainingText = text.replace(regex, '').trim();

  // Also handle incomplete reasoning blocks (e.g. streaming `<thought>...` without closing tag)
  const openTagMatch = remainingText.match(/<(think|thought|reasoning)>([\s\S]*)$/i);
  if (openTagMatch) {
    if (combinedReasoning) combinedReasoning += '\n\n';
    combinedReasoning += openTagMatch[2].trim();
    remainingText = remainingText.slice(0, openTagMatch.index).trim();
  }

  // Split the remaining text into an ordered sequence of text/chart segments,
  // supporting any number of json:chart blocks in a single answer (e.g. a
  // multi-graph report). Each chart is rendered exactly where it appeared in
  // the text — right after whatever heading/paragraph preceded it — instead
  // of every chart being collected and dumped at the very end. Any fenced
  // block that's chart-shaped JSON or explicitly tagged json:chart/chart is
  // always removed from the visible text (whether or not it renders), so
  // broken/duplicate chart JSON never leaks out as raw code.
  const segments: ({ type: 'text', content: string } | { type: 'chart', data: any })[] = [];
  const blockRegex = /```(json:chart|json|chart)?\s*\n?([\s\S]*?)```|(\{[\s\r\n]*"type"[\s\r\n]*:[\s\r\n]*"(?:bar|pie)"[\s\S]*?"data"[\s\r\n]*:[\s\r\n]*\[[\s\S]*?\][\s\r\n]*\})/gi;
  let lastIndex = 0;
  let blockMatch;

  while ((blockMatch = blockRegex.exec(remainingText)) !== null) {
    const isFenced = blockMatch[2] !== undefined;
    const tag = (blockMatch[1] || '').toLowerCase();
    const body = (isFenced ? blockMatch[2] : blockMatch[3]).trim();

    let parsed: any = null;
    try {
      parsed = JSON.parse(body);
    } catch (e) {
      // not valid JSON — still removed below if explicitly chart-tagged
    }
    const isChartShaped = parsed && (parsed.type === 'bar' || parsed.type === 'pie') && Array.isArray(parsed.data) && parsed.data.length > 0;
    const isChartTagged = isFenced && (tag === 'json:chart' || tag === 'chart');

    if (isChartShaped || isChartTagged) {
      const preceding = remainingText.slice(lastIndex, blockMatch.index);
      if (preceding.trim()) segments.push({ type: 'text', content: preceding });
      if (isChartShaped) {
        segments.push({ type: 'chart', data: parsed });
      }
      lastIndex = blockMatch.index + blockMatch[0].length;
    }
  }

  const remainder = remainingText.slice(lastIndex);
  if (remainder.trim()) segments.push({ type: 'text', content: remainder });

  const hasTodos = todos && todos.length > 0;
  const hasContent = segments.length > 0;

  const renderSegments = (topMargin: string) => segments.map((seg, i) => {
    const marginTop = i === 0 ? topMargin : '0.75rem';
    return seg.type === 'chart'
      ? <div key={i} className="fade-in" style={{ marginTop }}><ChartRenderer data={seg.data} /></div>
      : <div key={i} style={{ marginTop }}><TextBlock content={seg.content} /></div>;
  });

  // Fast mode
  if (mode === 'fast') {
    const showStatus = isStreaming && !hasContent;
    return (
      <>
        {showStatus && <StatusDots toolCalls={toolCalls} />}
        {renderSegments('0')}
      </>
    );
  }

  // If there is no reasoning at all and no todos, just render the segments
  if (!combinedReasoning && !hasTodos) {
    return <>{renderSegments('0')}</>;
  }

  return (
    <>
      <ReasoningBlock content={combinedReasoning} isStreaming={isStreaming} todos={todos} toolCalls={toolCalls} />
      {renderSegments('0.5rem')}
    </>
  );
};

type AgentType = 'contracts' | 'aviation';
type AgentMode = 'fast' | 'reasoning';
type AgentKey = 'contracts-fast' | 'contracts-reasoning' | 'aviation-fast' | 'aviation-reasoning';

const AGENT_KEY_LABELS: Record<AgentKey, string> = {
  'contracts-fast': 'Contracts Agent — Fast',
  'contracts-reasoning': 'Contracts Agent — Reasoning',
  'aviation-fast': 'Aviation Agent — Fast',
  'aviation-reasoning': 'Aviation Agent — Reasoning',
};

function parseAgentKey(key: AgentKey): { agent: AgentType; mode: AgentMode } {
  const [agent, mode] = key.split('-') as [AgentType, AgentMode];
  return { agent, mode };
}

function isEmptyChatTitle(title?: string): boolean {
  return !title || title === 'New Chat';
}

function moveSessionToFront(list: SessionMeta[], id: string): SessionMeta[] {
  const idx = list.findIndex(s => s.id === id);
  if (idx <= 0) return list;
  const next = [...list];
  const [item] = next.splice(idx, 1);
  next.unshift(item);
  return next;
}

interface AgentConfig {
  id: AgentType;
  name: string;
  shortName: string;
  badge: string;
  tagline: string;
  welcomeMessage: string;
  capabilities: { icon: any, label: string }[];
  faqs: string[];
}

const AGENT_CONFIGS: Record<AgentType, AgentConfig> = {
  contracts: {
    id: 'contracts',
    name: 'Contracts & Sales Intelligence',
    shortName: 'Contracts Agent',
    badge: 'CONTRACTS & SALES',
    tagline: 'CONTRACTS & SALES INTELLIGENCE',
    welcomeMessage: "Hello! I'm AVT, your Emarat Contracts & Sales intelligence assistant. I'm trained on commercial contracts, client revenue analytics, pricing terms, and legal clauses.\n\nHow can I assist you today?",
    capabilities: [
      { icon: FileText, label: 'Commercial contracts' },
      { icon: BarChart2, label: 'Client revenue analytics' },
      { icon: Fuel, label: 'Fuel pricing & contract rates' },
      { icon: PlaneTakeoff, label: 'Deal terms & renewal clauses' },
      { icon: MessageSquare, label: 'Legal clause search' },
    ],
    faqs: [
      "What's our total active contract value?",
      "Which contracts are expiring soon?",
      "Explain the termination clause for Ironvale Aerospace Solutions",
      "Show me top clients by revenue (Bar Chart)"
    ],
  },
  aviation: {
    id: 'aviation',
    name: 'Aviation Operations & Uplift',
    shortName: 'Aviation Agent',
    badge: 'AVIATION OPERATIONS',
    tagline: 'FLIGHT & UPLIFT OPERATIONS',
    welcomeMessage: "Hello! I'm AVT, your Emarat Aviation Operations assistant. I'm trained on aircraft refueling operations, fuel uplifts (Litres), flight movements, airline consumption, and stand analytics.\n\nHow can I assist you with aviation data today?",
    capabilities: [
      { icon: Fuel, label: 'Fuel uplift volumes (Litres)' },
      { icon: PlaneTakeoff, label: 'Flight movements & schedules' },
      { icon: Plane, label: 'Airline fleet & aircraft models' },
      { icon: BarChart2, label: 'Stand utilization & turnaround' },
      { icon: Layers, label: 'Aircraft tail registration search' },
    ],
    faqs: [
      "What is the total fuel volume uplifted by airline?",
      "Show fuel volume distribution by Aircraft Type (Bar Chart)",
      "Which stands handled the highest fuel volume?",
      "List flights and refueling details for SkyMira Air"
    ],
  },
};

export default function Chat({ sessionId, onLogout, onActivity, onNewChat, onSwitchSession }: ChatProps) {
  const [agentKey, setAgentKey] = useState<AgentKey>(() => {
    const saved = localStorage.getItem('active_agent_key');
    return (saved as AgentKey) || 'contracts-fast';
  });
  const { agent: activeAgent, mode: agentMode } = parseAgentKey(agentKey);
  const reasoningMode = agentMode === 'reasoning';
  const [isAgentMenuOpen, setIsAgentMenuOpen] = useState(false);

  const currentConfig = AGENT_CONFIGS[activeAgent];

  const [messages, setMessages] = useState<Message[]>([{ id: '1', text: currentConfig.welcomeMessage, sender: 'assistant' }]);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const createSessionOnServer = async (key: AgentKey = agentKey): Promise<string | null> => {
    const username = localStorage.getItem('chat_username') || 'user';
    const res = await fetch(`${API_BASE}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, title: 'New Chat', agent_key: key }),
    });
    const data = await res.json();
    return data.session_id || null;
  };

  const handleDeleteSession = async (e: React.MouseEvent, targetSessionId: string) => {
    e.stopPropagation();
    setOpenMenuId(null);
    const username = localStorage.getItem('chat_username') || '';
    try {
      await fetch(
        `${API_BASE}/sessions/${targetSessionId}?username=${encodeURIComponent(username)}`,
        { method: 'DELETE' }
      );
      const remaining = sessions.filter(s => s.id !== targetSessionId);
      setSessions(remaining);
      if (targetSessionId === sessionId) {
        if (remaining.length > 0) {
          onSwitchSession(remaining[0].id);
        } else {
          const newId = await createSessionOnServer();
          if (newId) {
            setSessions([{ id: newId, title: 'New Chat', agent_key: agentKey, agent_name: AGENT_KEY_LABELS[agentKey], updatedAt: Date.now() }]);
            onNewChat(newId);
          }
        }
      }
    } catch (err) {
      console.error('Failed to delete session', err);
    }
  };

  // Load every chat tab for this user (all agents). Do not filter by agent.
  useEffect(() => {
    const username = localStorage.getItem('chat_username');
    if (!username) return;
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/sessions?username=${encodeURIComponent(username)}`
        );
        const data = await res.json();
        if (cancelled || !Array.isArray(data)) return;

        const enriched: SessionMeta[] = await Promise.all(
          data.map(async (s: any) => {
            if (!isEmptyChatTitle(s.title)) return s;
            try {
              const hRes = await fetch(`${API_BASE}/sessions/${s.id}/history`);
              const msgs: any[] = await hRes.json();
              const firstUser = Array.isArray(msgs) ? msgs.find(m => m.role === 'user') : null;
              if (firstUser) {
                return { ...s, title: firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '') };
              }
            } catch (_) {}
            return s;
          })
        );
        if (cancelled) return;

        setSessions(prev => {
          const optimisticTitles: Record<string, string> = {};
          prev.forEach(s => { if (!isEmptyChatTitle(s.title)) optimisticTitles[s.id] = s.title; });
          const merged = enriched.map(s =>
            optimisticTitles[s.id] ? { ...s, title: optimisticTitles[s.id] } : s
          );
          const extras = prev.filter(s => !merged.some(m => m.id === s.id));
          const combined = [...extras, ...merged];
          return moveSessionToFront(combined, sessionIdRef.current || sessionId);
        });
      } catch (e) {
        if (!cancelled) console.error(e);
      }
    })();

    return () => { cancelled = true; };
  }, []);

  // Load the full transcript for whatever tab is selected (any agent).
  useEffect(() => {
    let cancelled = false;
    setIsLoading(false);
    setInput('');
    setOpenMenuId(null);

    const welcome = currentConfig.welcomeMessage;
    setMessages([{ id: '1', text: welcome, sender: 'assistant' }]);

    fetch(`${API_BASE}/sessions/${sessionId}/history`)
      .then(r => r.json())
      .then((data: any[]) => {
        if (cancelled) return;
        if (!Array.isArray(data) || data.length === 0) {
          setMessages([{ id: '1', text: welcome, sender: 'assistant' }]);
          return;
        }
        const firstUser = data.find(m => m.role === 'user');
        if (!firstUser) {
          setMessages([{ id: '1', text: welcome, sender: 'assistant' }]);
          return;
        }
        setMessages(data.map(m => ({
          id: m.id,
          text: m.content,
          sender: m.role as 'user' | 'assistant',
          toolCalls: m.toolCalls,
          mode: m.mode,
        })));
        const title = firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '');
        setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title } : s));
      })
      .catch(console.error);

    return () => { cancelled = true; };
  }, [sessionId]);
  const [isSidebarVisible, setIsSidebarVisible] = useState<boolean>(() => {
    const saved = localStorage.getItem('sidebar_visible');
    return saved === null ? true : saved === 'true';
  });

  const toggleSidebar = () => {
    setIsSidebarVisible(prev => {
      const next = !prev;
      localStorage.setItem('sidebar_visible', String(next));
      return next;
    });
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const getSessionDisplayTitle = (s: SessionMeta, _agent: AgentType): string => {
    if (!isEmptyChatTitle(s.title)) return s.title;
    if (s.id === sessionId) {
      const firstUser = messages.find(m => m.sender === 'user');
      if (firstUser && firstUser.text) {
        return firstUser.text.slice(0, 30) + (firstUser.text.length > 30 ? '...' : '');
      }
    }
    return s.title || 'New Chat';
  };

  useEffect(() => {
    localStorage.setItem(`chat_history_${sessionId}_${agentKey}`, JSON.stringify(messages));
  }, [messages, sessionId, agentKey]);

  const handleSwitchAgentKey = async (newKey: AgentKey) => {
    if (newKey === agentKey) {
      setIsAgentMenuOpen(false);
      return;
    }
    const { agent: newAgent } = parseAgentKey(newKey);
    const currentMeta = sessions.find(s => s.id === sessionId);
    const alreadyNewChat = !messages.some(m => m.sender === 'user') && isEmptyChatTitle(currentMeta?.title);

    setAgentKey(newKey);
    localStorage.setItem('active_agent_key', newKey);
    setIsAgentMenuOpen(false);
    setMessages([{ id: '1', text: AGENT_CONFIGS[newAgent].welcomeMessage, sender: 'assistant' }]);

    if (alreadyNewChat) {
      setSessions(prev => prev.map(s =>
        s.id === sessionId
          ? { ...s, agent_key: newKey, agent_name: AGENT_KEY_LABELS[newKey], updatedAt: Date.now() }
          : s
      ));
      const username = localStorage.getItem('chat_username') || 'user';
      fetch(`${API_BASE}/sessions/${sessionId}/agent`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, agent_key: newKey }),
      }).catch(console.error);
      return;
    }

    try {
      const newId = await createSessionOnServer(newKey);
      if (!newId) return;
      setSessions(prev => [
        { id: newId, title: 'New Chat', agent_key: newKey, agent_name: AGENT_KEY_LABELS[newKey], updatedAt: Date.now() },
        ...prev,
      ]);
      onNewChat(newId);
    } catch (e) {
      console.error('Failed to open a new chat for this agent', e);
    }
  };

  const sendMessage = async (textToSend: string) => {
    if (!textToSend.trim()) return;

    onActivity();

    const userMessage: Message = {
      id: Date.now().toString(),
      text: textToSend,
      sender: 'user'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Optimistically update the sidebar title on the FIRST user message.
    // This fires immediately — before the LLM responds — so the sidebar
    // never stays as "New Chat" after the user types something.
    // Works even if the Cosmos DB sessions fetch is still in-flight (sessions=[]):
    // in that case the session is added optimistically and will be de-duped
    // when the fetch completes.
    const isFirstUserMessage = !messages.some(m => m.sender === 'user');
    if (isFirstUserMessage) {
      const sidebarTitle = textToSend.slice(0, 30) + (textToSend.length > 30 ? '...' : '');
      setSessions(prev => {
        const alreadyInList = prev.some(s => s.id === sessionId);
        if (alreadyInList) {
          // Update in place
          return moveSessionToFront(
            prev.map(s => s.id === sessionId ? { ...s, title: sidebarTitle, updatedAt: Date.now() } : s),
            sessionId
          );
        }
        // Session not yet in list (fetch still in progress) — add it optimistically at top
        return [{ id: sessionId, title: sidebarTitle, updatedAt: Date.now() } as SessionMeta, ...prev];
      });
    }


    // Capture the toggle position at send time
    const modeAtSend: 'reasoning' | 'fast' = reasoningMode ? 'reasoning' : 'fast';
    const endpoint = reasoningMode
      ? `${API_BASE}/chat`
      : `${API_BASE}/chat/fast`;

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage.text, session_id: sessionId, agent_type: activeAgent, agent_key: agentKey })
      });

      if (res.status === 401) {
        alert('Session expired. Please log in again.');
        onLogout();
        return;
      }

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      const assistantMessageId = (Date.now() + 1).toString();
      let currentText = '';

      setMessages(prev => [...prev, { id: assistantMessageId, text: '', sender: 'assistant', mode: modeAtSend }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();
            if (data === '[DONE]') break;
            try {
              const parsed = JSON.parse(data);
              if (parsed.text !== undefined || parsed.todos !== undefined || parsed.tool_call !== undefined) {
                if (parsed.text) currentText += parsed.text;
                setMessages(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (updated[lastIdx].id === assistantMessageId) {
                    const msg = updated[lastIdx];
                    const existingToolCalls = msg.toolCalls || [];
                    const newToolCalls = parsed.tool_call && !existingToolCalls.includes(parsed.tool_call)
                      ? [...existingToolCalls, parsed.tool_call]
                      : existingToolCalls;

                    updated[lastIdx] = {
                      ...msg,
                      text: currentText,
                      todos: parsed.todos !== undefined ? parsed.todos : msg.todos,
                      toolCalls: newToolCalls,
                    };
                  }
                  return updated;
                });
              } else if (parsed.error) {
                currentText += "\nError: " + parsed.error;
                setMessages(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (updated[lastIdx].id === assistantMessageId) {
                    updated[lastIdx] = { ...updated[lastIdx], text: currentText };
                  }
                  return updated;
                });
              }
            } catch (e) {
              console.error("Error parsing SSE data", e, data);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "Connection error. Please try again later.",
        sender: 'assistant'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleNewChatClick = async () => {
    try {
      const newId = await createSessionOnServer();
      if (newId) {
        setSessions(prev => [
          { id: newId, title: 'New Chat', agent_key: agentKey, agent_name: AGENT_KEY_LABELS[agentKey], updatedAt: Date.now() },
          ...prev.filter(s => s.id !== newId),
        ]);
        onNewChat(newId);
      }
    } catch (e) {
      console.error('Failed to start new chat', e);
    }
  };

  const handleLogoutClick = async () => {
    try {
      // Use SSO logout to clear the session cookie
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (e) {
      // Ignore errors on logout
    }
    onLogout();
  };

  return (
    <div className="app-container fade-in">
      {/* Top Navigation */}
      <nav className="top-nav">
        <div className="nav-brand">
          <PlaneTakeoff size={24} />
          <span>Emarat Aviation</span>
        </div>
        <div className="nav-links">
          <span>Home</span>
          <span>Task Allocation</span>
          <span>Contracts</span>
          <span>Dashboards</span>
          <span>Contact</span>
          <button className="nav-btn active">Chat Support</button>
        </div>
      </nav>

      <div className="main-content">
        {/* Sidebar */}
        <div className={`sidebar ${isSidebarVisible ? '' : 'collapsed'}`}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2.5rem' }}>
            <div className="app-card" style={{ margin: 0 }}>
              <div className="app-icon-container">
                {activeAgent === 'aviation' ? <PlaneTakeoff size={24} color="white" /> : <FileText size={24} color="white" />}
              </div>
              <div className="app-info">
                <h4>AVT</h4>
                <p>{currentConfig.tagline}</p>
              </div>
            </div>
            <button
              className="sidebar-toggle-btn"
              onClick={toggleSidebar}
              title="Hide sidebar"
              style={{
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#94a3b8',
                cursor: 'pointer',
                padding: '6px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              <PanelLeftClose size={18} />
            </button>
          </div>

          <div className="capabilities-section">
            <h3 className="sidebar-title">CAPABILITIES</h3>
            <ul className="capabilities-list">
              {currentConfig.capabilities.map((cap, i) => {
                const IconComponent = cap.icon;
                return (
                  <li key={i}>
                    <IconComponent size={18} /> {cap.label}
                  </li>
                );
              })}
            </ul>
          </div>

          {(() => {
              return (
                <div className="history-section">
                  <h3 className="sidebar-title">RECENT CHATS</h3>
                  <div className="history-list">
                    {sessions.length === 0 ? (
                      <div style={{ color: '#475569', fontSize: '0.78rem', padding: '6px 4px' }}>
                        No chats yet.
                      </div>
                    ) : sessions.map(s => {
                      const displayTitle = getSessionDisplayTitle(s, activeAgent);
                      const isMenuOpen = openMenuId === s.id;
                      const tabAgent = s.agent_name || (s.agent_key ? AGENT_KEY_LABELS[s.agent_key] : '');
                      return (
                        <div
                          key={s.id}
                          className="session-row"
                          style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
                          onMouseLeave={() => setOpenMenuId(null)}
                        >
                          <button
                            className={`history-button ${s.id === sessionId ? 'active' : ''}`}
                            style={{ flex: 1, paddingRight: '32px', minWidth: 0, flexDirection: 'column', alignItems: 'flex-start', gap: '2px' }}
                            onClick={() => {
                              if (s.agent_key && s.agent_key !== agentKey) {
                                setAgentKey(s.agent_key);
                                localStorage.setItem('active_agent_key', s.agent_key);
                              }
                              onSwitchSession(s.id);
                            }}
                          >
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%' }}>
                              <MessageSquare size={16} style={{ flexShrink: 0 }} />
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {displayTitle}
                              </span>
                            </span>
                            {tabAgent && (
                              <span style={{ fontSize: '0.68rem', color: '#64748b', paddingLeft: '28px' }}>
                                {tabAgent}
                              </span>
                            )}
                          </button>

                          {/* 3-dot menu trigger */}
                          <button
                            onClick={(e) => { e.stopPropagation(); setOpenMenuId(isMenuOpen ? null : s.id); }}
                            style={{
                              position: 'absolute', right: '4px',
                              background: 'transparent', border: 'none',
                              color: s.id === sessionId ? 'var(--primary)' : '#94a3b8',
                              cursor: 'pointer',
                              padding: '4px', borderRadius: '4px',
                              display: 'flex', alignItems: 'center',
                            }}
                            className={`session-menu-btn ${isMenuOpen ? 'open' : ''}`}
                            title="Options"
                          >
                            <MoreVertical size={14} />
                          </button>

                          {/* Dropdown menu */}
                          {isMenuOpen && (
                            <div style={{
                              position: 'absolute', right: '0', top: '100%', zIndex: 100,
                              background: '#0f172a', border: '1px solid #1e293b',
                              borderRadius: '8px', padding: '4px', minWidth: '130px',
                              boxShadow: '0 8px 24px rgba(0,0,0,0.4)'
                            }}>
                              <button
                                onClick={(e) => handleDeleteSession(e, s.id)}
                                style={{
                                  display: 'flex', alignItems: 'center', gap: '8px',
                                  width: '100%', padding: '8px 10px',
                                  background: 'transparent', border: 'none',
                                  color: '#f87171', cursor: 'pointer',
                                  fontSize: '0.82rem', borderRadius: '6px',
                                  transition: 'background 0.15s'
                                }}
                                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(248,113,113,0.1)')}
                                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                              >
                                <Trash2 size={13} />
                                Delete chat
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

          <h3 className="sidebar-title" style={{ marginTop: sessions.length > 0 ? '2.5rem' : '0' }}>TRY ASKING</h3>
          <div className="faq-list">
            {currentConfig.faqs.map((faq, i) => (
              <button key={i} className="faq-button" onClick={() => sendMessage(faq)} disabled={isLoading}>
                {faq}
              </button>
            ))}
          </div>
        </div>

        {/* Chat Window */}
        <div className="chat-layout">
          <header className="chat-window-header">
            <div className="header-left">
              {!isSidebarVisible && (
                <button
                  className="sidebar-toggle-btn"
                  onClick={toggleSidebar}
                  title="Show sidebar"
                  style={{
                    background: 'rgba(56, 189, 248, 0.1)',
                    border: '1px solid rgba(56, 189, 248, 0.3)',
                    color: '#38bdf8',
                    cursor: 'pointer',
                    padding: '6px 8px',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginRight: '6px',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <PanelLeftOpen size={18} />
                </button>
              )}
              <div className="app-icon-container small">
                {activeAgent === 'aviation' ? <PlaneTakeoff size={16} color="white" /> : <FileText size={16} color="white" />}
              </div>
              <div className="header-title-col">
                {/* Interactive Agent Selector Dropdown */}
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={() => setIsAgentMenuOpen(prev => !prev)}
                    title="Click to switch intelligence agent"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '7px',
                      background: 'rgba(56, 189, 248, 0.1)',
                      border: '1px solid rgba(56, 189, 248, 0.3)',
                      borderRadius: '6px',
                      padding: '3px 9px',
                      color: '#38bdf8',
                      cursor: 'pointer',
                      fontSize: '0.88rem',
                      fontWeight: 600,
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <span>{AGENT_KEY_LABELS[agentKey]}</span>
                    <ChevronDown size={14} style={{ transform: isAgentMenuOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
                  </button>

                  {isAgentMenuOpen && (
                    <>
                      <div
                        onClick={() => setIsAgentMenuOpen(false)}
                        style={{ position: 'fixed', inset: 0, zIndex: 190 }}
                      />
                      <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        marginTop: '6px',
                        background: '#0f172a',
                        border: '1px solid rgba(56, 189, 248, 0.3)',
                        borderRadius: '8px',
                        padding: '5px',
                        zIndex: 200,
                        minWidth: '280px',
                        boxShadow: '0 10px 25px rgba(0,0,0,0.6)'
                      }}>
                        {(['contracts-fast', 'contracts-reasoning', 'aviation-fast', 'aviation-reasoning'] as AgentKey[]).map((key) => {
                          const { agent, mode } = parseAgentKey(key);
                          const isActive = key === agentKey;
                          const Icon = agent === 'aviation' ? PlaneTakeoff : FileText;
                          return (
                            <div
                              key={key}
                              onClick={() => handleSwitchAgentKey(key)}
                              style={{
                                display: 'flex', alignItems: 'center', gap: '10px',
                                padding: '8px 10px', borderRadius: '6px', cursor: 'pointer',
                                background: isActive ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                                color: isActive ? '#38bdf8' : '#cbd5e1',
                                fontSize: '0.84rem', fontWeight: isActive ? 600 : 400,
                                marginTop: '2px',
                              }}
                            >
                              <Icon size={16} color={isActive ? '#38bdf8' : '#94a3b8'} />
                              <div>
                                <div>{AGENT_KEY_LABELS[key]}</div>
                                <div style={{ fontSize: '0.72rem', color: '#64748b' }}>
                                  {mode === 'reasoning' ? 'Full step-by-step thought process' : 'Quicker, tool-verified answers'}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
                <span className="online-status"><div className="dot"></div> Online</span>
              </div>
            </div>
            <div className="header-right">
              <span className="badge">{currentConfig.badge}</span>
              <button className="btn-icon" onClick={handleNewChatClick} title="New Chat"><Plus size={18} /></button>
              <button className="btn-icon" onClick={handleLogoutClick} title="Logout"><LogOut size={18} /></button>
            </div>
          </header>

          <div className="chat-messages">
            {messages.map((msg) => (
              <div key={msg.id} className={`message-wrapper ${msg.sender}`}>
                {msg.sender === 'assistant' && (
                  <div className="message-avatar">
                    <div className="app-icon-container small">
                      <Plane size={16} color="white" />
                    </div>
                  </div>
                )}
                <div className={`message-bubble ${msg.sender}`}>
                  {msg.sender === 'assistant' ? (
                    <MessageFormatter
                      text={msg.text}
                      isStreaming={isLoading && msg.id === messages[messages.length - 1].id}
                      todos={msg.todos}
                      toolCalls={msg.toolCalls}
                      mode={msg.mode || agentMode}
                    />
                  ) : (
                    <span style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</span>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-wrapper">
            <div className="chat-input-container">
              <form className="chat-form" onSubmit={handleSend}>
                <input
                  type="text"
                  className="input"
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    onActivity();
                  }}
                  placeholder="Ask about fuel prices, contracts, uplifts..."
                  disabled={isLoading}
                />
                <button type="submit" className="send-btn" disabled={isLoading || !input.trim()}>
                  <Send size={18} />
                </button>
              </form>
            </div>
            <div className="chat-footer-text">
              AVT is in preview. Responses will be powered by your fine-tuned aviation model.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
