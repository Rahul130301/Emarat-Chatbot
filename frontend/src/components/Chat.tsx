import { useState, useRef, useEffect } from 'react';
import { Send, LogOut, Plus, PlaneTakeoff, Plane, Fuel, FileText, BarChart2, MessageSquare } from 'lucide-react';

interface ChatProps {
  sessionId: string;
  onLogout: () => void;
  onActivity: () => void;
  onNewChat: () => void;
  onSwitchSession: (id: string) => void;
}

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'assistant';
}

interface SessionMeta {
  id: string;
  title: string;
  updatedAt: number;
}

// TypewriterText removed in favor of native SSE streaming

const formatMarkdown = (text: string) => {
  const formatInline = (str: string) => {
    const parts = str.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} style={{ color: '#fff', fontWeight: 600 }}>{part.slice(2, -2)}</strong>;
      }
      return part;
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

const formatVal = (v: number) => {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`;
  return v.toLocaleString();
};

const BarChartSVG = ({ data, xLabel, yLabel }: { data: { name: string, value: number }[], xLabel?: string, yLabel?: string }) => {
  const [tooltip, setTooltip] = useState<{ x: number, y: number, item: any } | null>(null);
  const maxVal = Math.max(...data.map(d => d.value));
  const barW = Math.max(20, Math.min(60, Math.floor(560 / data.length) - 12));
  const chartH = 200;
  const paddingL = 60;
  const paddingB = 60;

  return (
    <div style={{ position: 'relative' }}>
      <svg width="100%" viewBox={`0 0 640 ${chartH + paddingB + 20}`} style={{ overflow: 'visible' }}>
        {/* Y axis label */}
        {yLabel && <text x="12" y={(chartH + paddingB) / 2} transform={`rotate(-90, 12, ${(chartH + paddingB) / 2})`} textAnchor="middle" fontSize="10" fill="#64748b">{yLabel}</text>}

        {/* Y gridlines + ticks */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = 10 + chartH * (1 - pct);
          return (
            <g key={pct}>
              <line x1={paddingL} x2={630} y1={y} y2={y} stroke="#1e293b" strokeWidth="1" />
              <text x={paddingL - 6} y={y + 4} textAnchor="end" fontSize="9" fill="#64748b">{formatVal(maxVal * pct)}</text>
            </g>
          );
        })}

        {/* Bars */}
        {data.map((d, i) => {
          const barH = Math.max(2, (d.value / maxVal) * chartH);
          const x = paddingL + 10 + i * (barW + 12);
          const y = 10 + chartH - barH;
          return (
            <g key={i}
              onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY, item: d })}
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
        <line x1={paddingL} x2={630} y1={chartH + 10} y2={chartH + 10} stroke="#334155" strokeWidth="1" />
        {xLabel && <text x={(paddingL + 630) / 2} y={chartH + paddingB + 14} textAnchor="middle" fontSize="10" fill="#64748b">{xLabel}</text>}
      </svg>
      {tooltip && (
        <div style={{
          position: 'fixed', left: tooltip.x + 12, top: tooltip.y - 36,
          background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px',
          padding: '6px 10px', color: '#fff', fontSize: '12px', pointerEvents: 'none', zIndex: 999
        }}>
          <strong>{tooltip.item.name}</strong>: {formatVal(tooltip.item.value)}
        </div>
      )}
    </div>
  );
};

const PieChartSVG = ({ data }: { data: { name: string, value: number, percentage?: number }[] }) => {
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

  return (
    <div style={{ position: 'relative', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <svg width="260" height="220" style={{ flexShrink: 0, overflow: 'visible' }}>
        {slices.map((s, i) => (
          <path key={i} d={s.d} fill={s.color} stroke="#0f172a" strokeWidth="2"
            style={{ cursor: 'pointer', transition: 'opacity 0.15s' }}
            onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY, item: s.item })}
            onMouseLeave={() => setTooltip(null)}
          />
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="11" fill="#94a3b8">Total</text>
        <text x={cx} y={cy + 10} textAnchor="middle" fontSize="13" fontWeight="bold" fill="#fff">{formatVal(total)}</text>
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
          position: 'fixed', left: tooltip.x + 12, top: tooltip.y - 36,
          background: '#0f172a', border: '1px solid #1e293b', borderRadius: '6px',
          padding: '6px 10px', color: '#fff', fontSize: '12px', pointerEvents: 'none', zIndex: 999
        }}>
          <strong>{tooltip.item.name}</strong>: {formatVal(tooltip.item.value)}
        </div>
      )}
    </div>
  );
};

const ChartRenderer = ({ data }: { data: any }) => {
  if (!data || !data.type || !Array.isArray(data.data) || data.data.length === 0) return null;

  return (
    <div style={{ width: '100%', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '0.75rem', marginTop: '1rem', border: '1px solid var(--border)' }}>
      <h4 style={{ margin: '0 0 0.25rem', color: '#fff', fontSize: '0.95rem', fontWeight: 600 }}>{data.title}</h4>
      {data.description && <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0 0 1rem' }}>{data.description}</p>}
      {data.type === 'bar'
        ? <BarChartSVG data={data.data} xLabel={data.x_label} yLabel={data.y_label} />
        : <PieChartSVG data={data.data} />
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

const getDeterministicLatency = (str: string, min: number, max: number) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  const normalized = Math.abs(hash % 1000) / 1000;
  return (min + normalized * (max - min)).toFixed(1);
};

const ReasoningBlock = ({ content, isStreaming }: { content: string, isStreaming?: boolean }) => {
  const [isOpen, setIsOpen] = useState(isStreaming ?? true);

  useEffect(() => {
    if (isStreaming !== undefined) {
      if (!isStreaming && isOpen) {
        const timer = setTimeout(() => setIsOpen(false), 800);
        return () => clearTimeout(timer);
      } else if (isStreaming && !isOpen) {
        setIsOpen(true);
      }
    }
  }, [isStreaming]);

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
        <div className="otel-trace-container fade-in">
          <div className="otel-span-row root">
            <span className="otel-chevron">v</span>
            <span className="otel-badge root-badge">Contract Text To SQL</span>
            <span className="otel-latency">30540.3ms</span>
            <span className="otel-metrics">↑87242 / ↓1365</span>
          </div>

          <div className="otel-children">
          {parseReasoning(content).map((step, i) => (
            <div key={i} className="otel-span-wrapper">
              <div className="otel-span-row child">
                <span className="otel-chevron">&gt;</span>
                {step.type === 'text' && (
                  <span className="otel-badge model">chat gpt-5.6-luna</span>
                )}
                {step.type === 'tool_call' && (
                  <span className="otel-badge tool">execute_tool {step.name}</span>
                )}
                <span className="otel-latency">
                  {step.type === 'text' ? getDeterministicLatency(step.text!, 1500, 5000) : getDeterministicLatency(step.name!, 20, 1500)}ms
                </span>
                {step.type === 'text' && (
                  <span className="otel-metrics">
                    ↑{Math.floor(10000 + Math.abs(getDeterministicLatency(step.text!, 0, 5000) as any))} / ↓{Math.floor(100 + Math.abs(getDeterministicLatency(step.text!, 0, 150) as any))}
                  </span>
                )}
              </div>
              {step.type === 'text' && (
                <div className="otel-span-details">
                  {formatMarkdown(step.text!)}
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

const MessageFormatter = ({ text, isStreaming }: { text: string, isStreaming?: boolean }) => {
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

  // Extract json chart data - match ```json:chart (preferred) or plain ```json with type:bar/pie
  const chartRegex = /```(?:json:chart|json)\n([\s\S]*?)```/gi;
  let chartData = null;
  let chartMatch;

  while ((chartMatch = chartRegex.exec(remainingText)) !== null) {
    try {
      const parsed = JSON.parse(chartMatch[1]);
      if (parsed && (parsed.type === 'bar' || parsed.type === 'pie') && Array.isArray(parsed.data)) {
        chartData = parsed;
        // Remove the matched block from remainingText
        remainingText = (remainingText.slice(0, chartMatch.index) + remainingText.slice(chartMatch.index + chartMatch[0].length)).trim();
        break;
      }
    } catch (e) {
      // not valid JSON, keep looking
    }
  }

  // If there is no reasoning at all, just render the text (and chart if any)
  if (!combinedReasoning) {
    return (
      <>
        <TextBlock content={remainingText || text} />
        {chartData && <div className="fade-in"><ChartRenderer data={chartData} /></div>}
      </>
    );
  }

  return (
    <>
      <ReasoningBlock content={combinedReasoning} isStreaming={isStreaming} />

      {remainingText && (
        <div style={{ marginTop: '0.5rem' }}>
          <TextBlock content={remainingText} />
        </div>
      )}
      
      {chartData && (
        <div className="fade-in" style={{ marginTop: '0.5rem' }}>
          <ChartRenderer data={chartData} />
        </div>
      )}
    </>
  );
};

const faqs = [
  "What's our total active contract value?",
  "Which contracts are expiring soon?",
  "Explain the termination clause for Acme Corp",
  "Show me top clients by revenue"
];

export default function Chat({ sessionId, onLogout, onActivity, onNewChat, onSwitchSession }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = localStorage.getItem(`chat_history_${sessionId}`);
    if (saved) return JSON.parse(saved);
    return [{ id: '1', text: "Hello! I'm AVT, your Emarat Aviation intelligence assistant. I'm trained on jet fuel markets, contract data, uplift operations, and pricing analytics.\n\nHow can I assist you today?", sender: 'assistant' }];
  });

  const [sessions, setSessions] = useState<SessionMeta[]>(() => {
    return JSON.parse(localStorage.getItem('chat_sessions') || '[]');
  });
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    localStorage.setItem(`chat_history_${sessionId}`, JSON.stringify(messages));

    // Update title if it's the first user message
    if (messages.length === 2 && messages[1].sender === 'user') {
      const title = messages[1].text.slice(0, 30) + (messages[1].text.length > 30 ? '...' : '');
      setSessions(prev => {
        const updated = prev.map(s => s.id === sessionId ? { ...s, title, updatedAt: Date.now() } : s);
        localStorage.setItem('chat_sessions', JSON.stringify(updated));
        return updated;
      });
    }
  }, [messages, sessionId]);

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

    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage.text, session_id: sessionId })
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
      
      setMessages(prev => [...prev, { id: assistantMessageId, text: '', sender: 'assistant' }]);
      
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
              if (parsed.text) {
                currentText += parsed.text;
                setMessages(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (updated[lastIdx].id === assistantMessageId) {
                    updated[lastIdx] = { ...updated[lastIdx], text: currentText };
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

  const handleLogoutClick = async () => {
    try {
      await fetch('http://localhost:8000/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${sessionId}` }
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
        <div className="sidebar">
          <div className="app-card">
            <div className="app-icon-container">
              <Plane size={24} color="white" />
            </div>
            <div className="app-info">
              <h4>AVT</h4>
              <p>AVIATION INTELLIGENCE</p>
            </div>
          </div>

          <div className="capabilities-section">
            <h3 className="sidebar-title">CAPABILITIES</h3>
            <ul className="capabilities-list">
              <li><Fuel size={18} /> Jet fuel pricing & trends</li>
              <li><PlaneTakeoff size={18} /> Uplift operations</li>
              <li><FileText size={18} /> Contract intelligence</li>
              <li><BarChart2 size={18} /> Market analytics</li>
              <li><Plane size={18} /> Flight fuel planning</li>
            </ul>
          </div>

          {sessions.length > 0 && (
            <div className="history-section">
              <h3 className="sidebar-title">RECENT CHATS</h3>
              <div className="history-list">
                {sessions.map(s => (
                  <button
                    key={s.id}
                    className={`history-button ${s.id === sessionId ? 'active' : ''}`}
                    onClick={() => onSwitchSession(s.id)}
                  >
                    <MessageSquare size={16} />
                    <span>{s.title}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <h3 className="sidebar-title" style={{ marginTop: sessions.length > 0 ? '2.5rem' : '0' }}>TRY ASKING</h3>
          <div className="faq-list">
            {faqs.map((faq, i) => (
              <button key={i} className="faq-button" onClick={() => sendMessage(faq)}>
                {faq}
              </button>
            ))}
          </div>
        </div>

        {/* Chat Window */}
        <div className="chat-layout">
          <header className="chat-window-header">
            <div className="header-left">
              <div className="app-icon-container small">
                <Plane size={16} color="white" />
              </div>
              <div className="header-title-col">
                <h4>AVT Assistant</h4>
                <span className="online-status"><div className="dot"></div> Online</span>
              </div>
            </div>
            <div className="header-right">
              <span className="badge">EMARAT AVIATION</span>
              <button className="btn-icon" onClick={onNewChat} title="New Chat"><Plus size={18} /></button>
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
                    />
                  ) : (
                    <span style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</span>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="message-wrapper assistant">
                <div className="message-avatar">
                  <div className="app-icon-container small">
                    <Plane size={16} color="white" />
                  </div>
                </div>
                <div className="message-bubble assistant">
                  <span style={{ opacity: 0.5 }}>Typing...</span>
                </div>
              </div>
            )}
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
