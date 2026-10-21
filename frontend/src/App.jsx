import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  MessageSquare,
  Plus,
  Trash2,
  Send,
  Upload,
  FileText,
  Settings,
  Sparkles,
  Zap,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Menu,
  X,
  Paperclip,
  Info,
  PanelLeftClose,
  PanelLeftOpen,
  BookOpen,
  Building2,
  Users,
  ShoppingCart,
  Search,
  Check,
  ArrowDown,
  UploadCloud,
  Cpu,
  Layers,
  Database,
  Loader2,
  Clock,
  AlertCircle,
  ArrowRight
} from 'lucide-react';

const RAW_API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const API_BASE = RAW_API_BASE.replace(/\/+$/, '');

// -----------------------------------------------------------------------------
// Upload Stages for High-Trustworthiness Progress Feedback
// -----------------------------------------------------------------------------
const UPLOAD_STAGES = [
  {
    step: 1,
    title: 'Uploading PDF Document',
    desc: 'Transferring file bytes to secure ingestion server',
    icon: UploadCloud,
  },
  {
    step: 2,
    title: 'Extracting Text & Section Hierarchy',
    desc: 'Parsing pages, titles, section headings & structured content',
    icon: Layers,
  },
  {
    step: 3,
    title: 'Generating Dense Vector Embeddings',
    desc: 'Running FastEmbed neural model for high-dimensional vectors',
    icon: Cpu,
  },
  {
    step: 4,
    title: 'Indexing into Qdrant Cloud',
    desc: 'Storing vector points with exact page and section citations',
    icon: Database,
  },
];

// -----------------------------------------------------------------------------
// Trustworthy Upload Progress Display Component
// -----------------------------------------------------------------------------
function UploadProgressDisplay({ progress, onDismiss, onAskQuestion }) {
  if (!progress || !progress.active) return null;

  const isComplete = progress.stage === 4;
  const isError = progress.stage === -1;

  return (
    <div className="w-full max-w-lg mx-auto p-4 sm:p-5 rounded-2xl bg-[#131d31] border border-blue-500/30 shadow-2xl animate-fade-in relative overflow-hidden backdrop-blur select-none">
      {/* Background ambient lighting */}
      <div className="absolute -top-12 -left-12 w-32 h-32 bg-blue-500/10 rounded-full blur-2xl pointer-events-none" />
      <div className="absolute -bottom-12 -right-12 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none" />

      {/* Header with File Info & Close/Dismiss */}
      <div className="flex items-start justify-between gap-3 mb-3 relative z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-md ${
              isComplete
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : isError
                ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                : 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
            }`}
          >
            {isComplete ? (
              <CheckCircle2 size={22} className="animate-bounce" />
            ) : isError ? (
              <AlertCircle size={22} />
            ) : (
              <FileText size={20} className="animate-pulse" />
            )}
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-bold text-white truncate max-w-[220px] sm:max-w-[300px]" title={progress.filename}>
              {progress.filename}
            </h4>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span className="font-mono">{progress.fileSize}</span>
              <span>•</span>
              <span className="flex items-center gap-1 font-mono">
                <Clock size={11} className="text-slate-400" />
                {progress.elapsedSeconds}s
              </span>
            </div>
          </div>
        </div>

        {(isComplete || isError) && (
          <button
            onClick={onDismiss}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            title="Dismiss"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Progress Bar & Percentage */}
      {!isError && (
        <div className="mb-4 relative z-10">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="font-semibold text-slate-200">
              {isComplete ? 'Indexing Completed Successfully' : UPLOAD_STAGES[progress.stage]?.title || 'Processing Document...'}
            </span>
            <span className="font-mono font-bold text-blue-400">
              {progress.percentage}%
            </span>
          </div>

          <div className="w-full h-2.5 bg-slate-800/80 rounded-full overflow-hidden border border-slate-700/60 relative">
            <div
              className={`h-full rounded-full transition-all duration-300 ease-out relative overflow-hidden ${
                isComplete
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                  : 'bg-gradient-to-r from-blue-600 via-indigo-500 to-cyan-400'
              }`}
              style={{ width: `${progress.percentage}%` }}
            >
              {!isComplete && (
                <div className="absolute inset-0 bg-white/20 animate-shimmer" />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Step Breakdown */}
      {!isError && !isComplete && (
        <div className="space-y-1.5 mb-3.5 relative z-10">
          {UPLOAD_STAGES.map((s, idx) => {
            const isDone = progress.stage > idx;
            const isCurrent = progress.stage === idx;
            const isPending = progress.stage < idx;

            return (
              <div
                key={idx}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs transition-all duration-200 ${
                  isCurrent
                    ? 'bg-blue-500/10 border border-blue-500/30 text-white'
                    : isDone
                    ? 'bg-slate-800/30 text-slate-300'
                    : 'text-slate-500 opacity-60'
                }`}
              >
                <div className="flex-shrink-0">
                  {isDone ? (
                    <div className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                      <Check size={12} />
                    </div>
                  ) : isCurrent ? (
                    <div className="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center">
                      <Loader2 size={12} className="animate-spin" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full bg-slate-800 text-slate-500 flex items-center justify-center text-[10px] font-mono">
                      {idx + 1}
                    </div>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{s.title}</div>
                  {isCurrent && (
                    <div className="text-[11px] text-blue-300/80 truncate mt-0.5">{s.desc}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Error Message */}
      {isError && (
        <div className="p-3 mb-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs relative z-10">
          <div className="font-semibold mb-1">Upload failed</div>
          <div>{progress.errorMessage}</div>
        </div>
      )}

      {/* Success Call to Action */}
      {isComplete && (
        <div className="space-y-3 relative z-10">
          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center justify-between">
            <span className="font-medium">
              Ready! {progress.chunksCount ? `${progress.chunksCount} chunks indexed with citations` : 'Grounded references active'}
            </span>
            <span className="text-[10px] font-mono text-emerald-400 font-bold">100% Grounded</span>
          </div>

          <button
            onClick={() => {
              if (onAskQuestion) onAskQuestion(`Summarize the core takeaways of ${progress.filename}`);
              if (onDismiss) onDismiss();
            }}
            className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-lg shadow-blue-500/20 transition-all active:scale-[0.99]"
          >
            <span>Ask questions about this document</span>
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* Trust message */}
      {!isComplete && !isError && (
        <p className="text-center text-[10px] text-slate-400 italic relative z-10">
          Please wait while your document is indexed for sub-second, verified citations.
        </p>
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// Citation Helpers for Research Paper Style Citations [1], [2], etc.
// -----------------------------------------------------------------------------
function parseCitation(rawText, fallbackIndex = null) {
  let clean = (rawText || '').trim();

  // Extract leading [1] or [1] -> if present
  let id = null;
  const idMatch = clean.match(/^\[(\d+)\]\s*(?:->)?\s*/);
  if (idMatch) {
    id = idMatch[1];
    clean = clean.substring(idMatch[0].length).trim();
  } else if (fallbackIndex) {
    id = String(fallbackIndex);
  }

  clean = clean.replace(/^\[|\]$/g, '').trim();
  clean = clean.replace(/^Source:\s*/i, '');

  let filename = '';
  let page = '';
  let section = '';

  const bulletDelimiter = clean.includes(' • ') ? ' • ' : clean.includes(' | ') ? ' | ' : null;

  if (bulletDelimiter) {
    const parts = clean.split(bulletDelimiter).map((s) => s.trim());
    filename = parts[0] || '';
    parts.slice(1).forEach((part) => {
      if (/^page/i.test(part)) {
        page = part.replace(/^page[:\s]*/i, '').trim();
      } else if (/^section/i.test(part)) {
        section = part.replace(/^section[:\s]*/i, '').trim();
      } else {
        section = part.trim();
      }
    });
  } else {
    const pageMatch = clean.match(/(?:,\s*|\s+|^)Page:?\s*(\d+)/i);
    const sectionMatch = clean.match(/(?:,\s*|\s+|^)Section:?\s*([^,\]]+)/i);

    if (pageMatch) page = pageMatch[1].trim();
    if (sectionMatch) section = sectionMatch[1].trim();

    let fnPart = clean;
    const cutIdx = clean.search(/(?:,\s*|\s+)Page:?|(?:,\s*|\s+)Section:?/i);
    if (cutIdx !== -1) {
      fnPart = clean.substring(0, cutIdx).trim();
    } else {
      const commaIdx = clean.indexOf(',');
      if (commaIdx !== -1) fnPart = clean.substring(0, commaIdx).trim();
    }
    filename = fnPart;
  }

  filename = (filename || '').replace(/[,;]+$/, '').replace(/^['"]|['"]$/g, '').trim();
  const displayName = filename.split(/[\\/]/).pop();
  return { id, filename: displayName, page, section, raw: clean };
}

function getCitationTooltip(sources, num) {
  if (!sources || !Array.isArray(sources)) return `Reference [${num}]`;
  const found = sources.find((s, idx) => {
    const p = parseCitation(s, idx + 1);
    return p.id === String(num);
  });
  if (found) {
    const p = parseCitation(found);
    return `[${num}] ${p.filename}${p.page ? ` (Page ${p.page})` : ''}${p.section ? ` - ${p.section}` : ''}`;
  }
  return `Jump to Reference [${num}]`;
}

function renderWithCitations(children, msgIndex, msgSources, onCitationClick) {
  if (Array.isArray(children)) {
    return children.map((child, idx) => (
      <React.Fragment key={idx}>{renderWithCitations(child, msgIndex, msgSources, onCitationClick)}</React.Fragment>
    ));
  }
  if (typeof children !== 'string') return children;

  // Match numeric citations: [1], [2], [1, 2], [1][2] OR legacy [Source: ...]
  const regex = /\[(\d+(?:\s*,\s*\d+)*)\]|\[(Source:[^\]]+|[^\]]*(?:Page|Section|\.pdf)[^\]]*)\]/gi;
  if (!regex.test(children)) return children;

  const parts = [];
  let lastIdx = 0;
  let match;
  regex.lastIndex = 0;
  while ((match = regex.exec(children)) !== null) {
    if (match.index > lastIdx) {
      parts.push(children.substring(lastIdx, match.index));
    }

    if (match[1]) {
      // Numeric citation(s) e.g. "1" or "1, 2"
      const nums = match[1].split(/,\s*/).map((n) => n.trim()).filter(Boolean);
      nums.forEach((num, nIdx) => {
        const tooltip = getCitationTooltip(msgSources, num);
        parts.push(
          <button
            key={`${match.index}-${nIdx}`}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (onCitationClick) onCitationClick(msgIndex, num);
            }}
            className="inline-flex items-center justify-center min-w-[20px] h-[19px] px-1.5 mx-0.5 -mt-0.5 rounded-md bg-blue-500/20 hover:bg-blue-500/40 text-blue-300 hover:text-blue-100 border border-blue-500/40 text-[11px] font-mono font-bold align-baseline transition-all duration-150 active:scale-95 cursor-pointer shadow-sm group"
            title={tooltip}
          >
            [{num}]
          </button>
        );
      });
    } else if (match[2]) {
      // Legacy formatted citation [Source: ...]
      const { filename, page, section, raw } = parseCitation(match[2]);
      parts.push(
        <span
          key={match.index}
          className="inline-flex items-center gap-1.5 px-2 py-0.5 mx-1 my-0.5 rounded-lg bg-blue-950/80 border border-blue-500/40 text-blue-200 font-mono text-[11px] align-baseline shadow-sm hover:border-blue-400 hover:bg-blue-900/60 transition-colors select-none cursor-pointer"
          title={`Verified Citation: ${raw}`}
        >
          <FileText size={11} className="text-blue-400 flex-shrink-0" />
          <span className="font-semibold text-slate-100 truncate max-w-[150px]">{filename}</span>
          {page && (
            <span className="px-1.5 py-0.2 rounded bg-blue-600/30 text-blue-300 border border-blue-400/30 text-[10px] font-semibold">
              P.{page}
            </span>
          )}
          {section && section !== `Page ${page}` && (
            <span className="px-1.5 py-0.2 rounded bg-indigo-600/30 text-indigo-300 border border-indigo-400/30 text-[10px] truncate max-w-[130px]">
              {section}
            </span>
          )}
        </span>
      );
    }

    lastIdx = regex.lastIndex;
  }

  if (lastIdx < children.length) {
    parts.push(children.substring(lastIdx));
  }
  return parts;
}

export default function App() {
  // ---------------------------------------------------------------------------
  // State Management
  // ---------------------------------------------------------------------------
  const [sessions, setSessions] = useState(() => {
    try {
      const saved = localStorage.getItem('rag_chat_sessions');
      if (saved) {
        const parsed = JSON.parse(saved);
        const cleanSessions = {};
        let emptyCount = 0;
        Object.entries(parsed).forEach(([id, sess]) => {
          if (!sess.messages || sess.messages.length === 0) {
            emptyCount++;
            if (emptyCount === 1) {
              cleanSessions[id] = sess;
            }
          } else {
            cleanSessions[id] = sess;
          }
        });
        if (Object.keys(cleanSessions).length > 0) {
          return cleanSessions;
        }
      }
    } catch (e) {
      console.warn('Failed to parse saved sessions:', e);
    }

    const defaultId = 'sess_' + Date.now();
    return {
      [defaultId]: {
        id: defaultId,
        title: 'New Conversation',
        createdAt: Date.now(),
        messages: [],
      },
    };
  });

  const [activeSessionId, setActiveSessionId] = useState(() => {
    try {
      const savedId = localStorage.getItem('rag_active_session_id');
      return savedId || null;
    } catch {
      return null;
    }
  });

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth < 768;
    }
    return false;
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [highlightedRef, setHighlightedRef] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [selectedModel, setSelectedModel] = useState('auto');
  const [topK, setTopK] = useState(5);
  const [openCitations, setOpenCitations] = useState({});
  const [openPreviousChats, setOpenPreviousChats] = useState(true);
  const [openSettings, setOpenSettings] = useState(false);
  const [openDocs, setOpenDocs] = useState(true);
  const [openAbout, setOpenAbout] = useState(false);
  const [healthStatus, setHealthStatus] = useState({ backend: true, qdrant: true, inngest: true });
  const [isDragOver, setIsDragOver] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const chatContainerRef = useRef(null);
  const sidebarFileInputRef = useRef(null);
  const chatboxFileInputRef = useRef(null);
  const heroFileInputRef = useRef(null);

  // Smooth container-internal scrolling to citation (Never scrolls window or body!)
  const scrollToCitation = (msgIndex, refNum) => {
    const refId = `ref-${msgIndex}-${refNum}`;
    const el = document.getElementById(refId);
    const container = chatContainerRef.current;
    if (el && container) {
      const elRect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const offset = elRect.top - containerRect.top + container.scrollTop - 24;
      container.scrollTo({ top: offset, behavior: 'smooth' });
      setHighlightedRef(refId);
      setTimeout(() => {
        setHighlightedRef(null);
      }, 2500);
    }
  };

  // ---------------------------------------------------------------------------
  // Persistence & Initialization
  // ---------------------------------------------------------------------------
  useEffect(() => {
    try {
      localStorage.setItem('rag_chat_sessions', JSON.stringify(sessions));
    } catch (e) {
      console.warn('Failed to persist sessions:', e);
    }
  }, [sessions]);

  useEffect(() => {
    try {
      if (activeSessionId) {
        localStorage.setItem('rag_active_session_id', activeSessionId);
      }
    } catch (e) {
      console.warn('Failed to persist active session ID:', e);
    }
  }, [activeSessionId]);

  // Ensure active session exists on initial load
  useEffect(() => {
    const sessionKeys = Object.keys(sessions);
    if (!activeSessionId || !sessions[activeSessionId]) {
      if (sessionKeys.length > 0) {
        const sorted = sessionKeys.sort((a, b) => (sessions[b]?.createdAt || 0) - (sessions[a]?.createdAt || 0));
        setActiveSessionId(sorted[0]);
      }
    }
  }, []);

  // Fetch documents and health on mount
  useEffect(() => {
    fetchDocuments();
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // Handle mobile screen detection on window resize
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Auto-scroll chat to bottom inside container ONLY (Never causes window or body to scroll)
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [sessions, activeSessionId, loading]);

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isNotAtBottom = scrollHeight - scrollTop - clientHeight > 100;
    setShowScrollBottom(isNotAtBottom);
  };

  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  };

  // ---------------------------------------------------------------------------
  // API Calls
  // ---------------------------------------------------------------------------
  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (res.ok) {
        const data = await res.json();
        setHealthStatus({
          backend: true,
          qdrant: data.qdrant_cloud ?? true,
          inngest: data.inngest_cloud ?? true,
        });
      } else {
        setHealthStatus({ backend: false, qdrant: false, inngest: false });
      }
    } catch {
      setHealthStatus({ backend: false, qdrant: false, inngest: false });
    }
  };

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (e) {
      console.warn('Could not fetch documents:', e);
    }
  };

  // High-Trustworthiness Multi-Stage Document Ingestion
  const handleFileUpload = async (eOrFile) => {
    let file = null;
    if (eOrFile && eOrFile.target && eOrFile.target.files) {
      file = eOrFile.target.files[0];
    } else if (eOrFile instanceof File) {
      file = eOrFile;
    } else if (eOrFile && eOrFile.dataTransfer && eOrFile.dataTransfer.files) {
      file = eOrFile.dataTransfer.files[0];
    }
    if (!file || !file.name) return;

    const formattedSize =
      file.size > 1024 * 1024
        ? (file.size / (1024 * 1024)).toFixed(1) + ' MB'
        : (file.size / 1024).toFixed(0) + ' KB';

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setUploadProgress({
        active: true,
        filename: file.name,
        fileSize: formattedSize,
        stage: -1,
        percentage: 0,
        elapsedSeconds: 0,
        errorMessage: 'Only PDF documents are supported.',
      });
      return;
    }

    setUploading(true);
    setUploadProgress({
      active: true,
      filename: file.name,
      fileSize: formattedSize,
      stage: 0,
      percentage: 12,
      elapsedSeconds: 0,
      chunksCount: null,
      errorMessage: null,
    });

    const startTime = Date.now();
    const timer = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      const seconds = parseFloat(elapsed);

      setUploadProgress((prev) => {
        if (!prev || !prev.active || prev.stage === 4 || prev.stage === -1) return prev;
        let nextStage = prev.stage;
        let nextPct = prev.percentage;

        if (seconds < 1.0) {
          nextStage = 0;
          nextPct = Math.min(25, 12 + Math.floor(seconds * 13));
        } else if (seconds < 2.8) {
          nextStage = 1;
          nextPct = Math.min(55, 25 + Math.floor((seconds - 1.0) * 16));
        } else if (seconds < 5.0) {
          nextStage = 2;
          nextPct = Math.min(82, 55 + Math.floor((seconds - 2.8) * 12));
        } else {
          nextStage = 3;
          nextPct = Math.min(95, 82 + Math.floor((seconds - 5.0) * 3));
        }

        return {
          ...prev,
          stage: nextStage,
          percentage: nextPct,
          elapsedSeconds: seconds,
        };
      });
    }, 200);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Upload failed');
      }

      const data = await res.json();
      clearInterval(timer);

      const totalSeconds = ((Date.now() - startTime) / 1000).toFixed(1);
      setUploadProgress({
        active: true,
        filename: file.name,
        fileSize: formattedSize,
        stage: 4,
        percentage: 100,
        elapsedSeconds: totalSeconds,
        chunksCount: data.chunks_count || null,
        errorMessage: null,
      });

      fetchDocuments();

      // Keep success banner visible for 4.5 seconds so user has time to read
      setTimeout(() => {
        setUploadProgress((prev) => (prev && prev.stage === 4 ? null : prev));
      }, 4500);

    } catch (err) {
      clearInterval(timer);
      setUploadProgress({
        active: true,
        filename: file.name,
        fileSize: formattedSize,
        stage: -1,
        percentage: 0,
        elapsedSeconds: ((Date.now() - startTime) / 1000).toFixed(1),
        errorMessage: err.message || 'Failed to process document',
      });
    } finally {
      setUploading(false);
      if (sidebarFileInputRef.current) sidebarFileInputRef.current.value = '';
      if (chatboxFileInputRef.current) chatboxFileInputRef.current.value = '';
      if (heroFileInputRef.current) heroFileInputRef.current.value = '';
    }
  };

  const handleDeleteDocument = async (filename) => {
    if (!window.confirm(`Are you sure you want to remove "${filename}" from AskFiles?`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/documents/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete document');
      }

      setUploadMessage(`Removed ${filename}`);
      fetchDocuments();
      setTimeout(() => setUploadMessage(null), 3000);
    } catch (err) {
      alert(`Could not delete document: ${err.message}`);
    }
  };

  // ---------------------------------------------------------------------------
  // Chat Session Actions
  // ---------------------------------------------------------------------------
  const handleNewChat = () => {
    const newId = 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    const newSession = {
      id: newId,
      title: 'New Conversation',
      createdAt: Date.now(),
      messages: [],
    };
    setSessions((prev) => ({ [newId]: newSession, ...prev }));
    setActiveSessionId(newId);
    setInput('');
    if (isMobile) {
      setSidebarOpen(false);
    }
  };

  const handleDeleteChat = (e, id) => {
    e.stopPropagation();
    setSessions((prev) => {
      const copy = { ...prev };
      delete copy[id];
      if (Object.keys(copy).length === 0) {
        const freshId = 'sess_' + Date.now();
        return {
          [freshId]: {
            id: freshId,
            title: 'New Conversation',
            createdAt: Date.now(),
            messages: [],
          },
        };
      }
      return copy;
    });

    if (activeSessionId === id) {
      const remaining = Object.keys(sessions).filter((k) => k !== id);
      if (remaining.length > 0) {
        setActiveSessionId(remaining[0]);
      } else {
        handleNewChat();
      }
    }
  };

  const handleSendMessage = async (queryText = null) => {
    const textToSend = (queryText || input).trim();
    if (!textToSend || loading) return;

    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const currentId = activeSessionId || Object.keys(sessions)[0];
    const currentSession = sessions[currentId] || {
      id: currentId,
      title: 'New Conversation',
      createdAt: Date.now(),
      messages: [],
    };

    const updatedTitle =
      currentSession.messages.length === 0
        ? textToSend.slice(0, 32) + (textToSend.length > 32 ? '...' : '')
        : currentSession.title;

    const userMessage = {
      role: 'user',
      content: textToSend,
      timestamp: Date.now(),
    };

    setSessions((prev) => ({
      ...prev,
      [currentId]: {
        ...currentSession,
        title: updatedTitle,
        messages: [...currentSession.messages, userMessage],
      },
    }));

    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: textToSend,
          top_k: Number(topK),
          model: selectedModel !== 'auto' ? selectedModel : null,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Server returned error ${res.status}`);
      }

      const data = await res.json();

      const assistantMessage = {
        role: 'assistant',
        content: data.answer || '(No answer returned)',
        model_used: data.model_used,
        latency_ms: data.latency_ms,
        sources: data.sources || [],
        fallback_history: data.fallback_history || [],
        num_contexts: data.num_contexts || 0,
        timestamp: Date.now(),
      };

      setSessions((prev) => {
        const s = prev[currentId] || currentSession;
        return {
          ...prev,
          [currentId]: {
            ...s,
            messages: [...s.messages, assistantMessage],
          },
        };
      });
    } catch (err) {
      const errorMessage = {
        role: 'assistant',
        content: `⚠️ **Error generating answer:** ${err.message}`,
        model_used: 'Error',
        latency_ms: 0,
        sources: [],
        fallback_history: [],
        timestamp: Date.now(),
      };

      setSessions((prev) => {
        const s = prev[currentId] || currentSession;
        return {
          ...prev,
          [currentId]: {
            ...s,
            messages: [...s.messages, errorMessage],
          },
        };
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleInputResize = (e) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  const activeSession = sessions[activeSessionId] || Object.values(sessions)[0] || { messages: [] };

  const previousSessions = Object.values(sessions)
    .filter((s) => s.messages && s.messages.length > 0)
    .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="flex h-full w-full bg-[#0f172a] text-slate-100 font-sans antialiased overflow-hidden relative">
      {/* Mobile Backdrop Overlay */}
      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 transition-opacity duration-300 md:hidden"
        />
      )}

      {/* =====================================================================
          SIDEBAR (Slide-over drawer on mobile, collapsible on desktop)
      ====================================================================== */}
      <aside
        className={`
          ${isMobile
            ? `fixed inset-y-0 left-0 z-50 w-72 sm:w-80 shadow-2xl border-r border-slate-800 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'}`
            : `relative ${sidebarOpen ? 'translate-x-0 w-80 border-r border-slate-800' : '-translate-x-full w-0 border-r-0 pointer-events-none'}`
          }
          transition-all duration-300 ease-in-out bg-[#090d16] flex flex-col flex-shrink-0 h-full overflow-hidden
        `}
      >
        {/* AskFiles Logo Header with Sidebar Collapse Icon */}
        <div className="p-4 border-b border-slate-800 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
                <FileText size={18} className="text-white drop-shadow" />
              </div>
              <div>
                <span className="text-base font-bold tracking-tight text-white flex items-center">
                  Ask<span className="text-blue-400">Files</span>
                </span>
                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-medium block -mt-0.5">
                  Doc AI Assistant
                </span>
              </div>
            </div>

            {/* Clickable Sidebar Close/Collapse Icon */}
            <button
              onClick={() => setSidebarOpen(false)}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              title="Close sidebar"
            >
              <PanelLeftClose size={18} />
            </button>
          </div>

          {/* New Chat Primary Button */}
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-all duration-150 shadow-lg shadow-blue-600/20 active:scale-[0.98]"
          >
            <Plus size={16} />
            New Chat
          </button>
        </div>

        {/* Scrollable Center Section */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
          {/* Previous Conversation Section with Expand/Collapse Arrow */}
          <div className="pt-1">
            <button
              onClick={() => setOpenPreviousChats(!openPreviousChats)}
              className="w-full flex items-center justify-between py-1.5 px-2 text-xs font-semibold text-slate-400 hover:text-white uppercase tracking-wider transition-colors"
            >
              <span className="flex items-center gap-2">
                <MessageSquare size={14} className="text-blue-400" />
                Previous Conversations {previousSessions.length > 0 && `(${previousSessions.length})`}
              </span>
              {openPreviousChats ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {openPreviousChats && (
              <div className="mt-1 space-y-1 animate-fade-in max-h-48 overflow-y-auto pr-1">
                {previousSessions.length === 0 ? (
                  <p className="px-3 py-2 text-xs text-slate-500 italic">No previous chats yet.</p>
                ) : (
                  previousSessions.map((s) => {
                    const isActive = s.id === activeSessionId;
                    return (
                      <div
                        key={s.id}
                        onClick={() => {
                          setActiveSessionId(s.id);
                          if (isMobile) setSidebarOpen(false);
                        }}
                        className={`group flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer text-xs transition-colors duration-150 mb-1 ${
                          isActive
                            ? 'bg-slate-800/90 text-white font-medium border border-slate-700/60 shadow-sm'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 truncate pr-2">
                          <MessageSquare size={13} className={isActive ? 'text-blue-400' : 'text-slate-500'} />
                          <span className="truncate">{s.title || 'Conversation'}</span>
                        </div>
                        <button
                          onClick={(e) => handleDeleteChat(e, s.id)}
                          className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-400 rounded transition-opacity duration-150"
                          title="Delete chat"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>

          {/* Document Management Section */}
          <div className="border-t border-slate-800/80 pt-2.5">
            <button
              onClick={() => setOpenDocs(!openDocs)}
              className="w-full flex items-center justify-between py-1.5 px-2 text-xs font-semibold text-slate-400 hover:text-white uppercase tracking-wider"
            >
              <span className="flex items-center gap-2">
                <FileText size={14} className="text-blue-400" />
                Documents ({documents.length})
              </span>
              {openDocs ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {openDocs && (
              <div className="mt-2 space-y-2 animate-fade-in">
                <input
                  type="file"
                  ref={sidebarFileInputRef}
                  onChange={handleFileUpload}
                  accept=".pdf"
                  className="hidden"
                  id="sidebar-file-upload"
                />
                <label
                  htmlFor="sidebar-file-upload"
                  className={`w-full flex items-center justify-center gap-2 py-2 px-3 border border-dashed rounded-xl cursor-pointer text-xs transition-colors ${
                    uploading
                      ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                      : 'border-slate-700 hover:border-slate-500 bg-slate-800/40 hover:bg-slate-800 text-slate-300'
                  }`}
                >
                  {uploading ? <Loader2 size={14} className="animate-spin text-blue-400" /> : <Upload size={14} />}
                  <span>{uploading ? 'Processing PDF...' : 'Upload PDF'}</span>
                </label>

                {/* Sidebar Mini Progress Bar during Ingestion */}
                {uploadProgress && uploadProgress.active && (
                  <div className="p-2.5 rounded-xl bg-blue-950/60 border border-blue-500/30 text-xs animate-fade-in">
                    <div className="flex items-center justify-between gap-1 mb-1.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {uploadProgress.stage === 4 ? (
                          <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0" />
                        ) : uploadProgress.stage === -1 ? (
                          <AlertCircle size={13} className="text-red-400 flex-shrink-0" />
                        ) : (
                          <Loader2 size={13} className="text-blue-400 animate-spin flex-shrink-0" />
                        )}
                        <span className="font-medium text-slate-200 truncate text-[11px]">{uploadProgress.filename}</span>
                      </div>
                      <span className="font-mono text-blue-400 font-bold text-[10px] flex-shrink-0">
                        {uploadProgress.stage === 4 ? '100%' : `${uploadProgress.percentage}%`}
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          uploadProgress.stage === 4
                            ? 'bg-emerald-400'
                            : uploadProgress.stage === -1
                            ? 'bg-red-400'
                            : 'bg-gradient-to-r from-blue-500 to-cyan-400'
                        }`}
                        style={{ width: `${uploadProgress.percentage}%` }}
                      />
                    </div>
                    <div className="text-[10px] text-slate-400 truncate mt-1">
                      {uploadProgress.stage === 4
                        ? 'Indexed successfully!'
                        : uploadProgress.stage === -1
                        ? uploadProgress.errorMessage
                        : UPLOAD_STAGES[uploadProgress.stage]?.title || 'Processing...'}
                    </div>
                  </div>
                )}

                <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
                  {documents.length === 0 ? (
                    <p className="text-[11px] text-slate-400 italic px-2 py-1">No PDFs uploaded yet.</p>
                  ) : (
                    documents.map((doc, idx) => (
                      <div
                        key={idx}
                        className="group flex items-center justify-between text-[11px] text-slate-300 bg-slate-800/50 hover:bg-slate-800/80 px-2.5 py-1.5 rounded-lg border border-slate-700/40 transition-colors"
                      >
                        <div className="truncate pr-2 font-mono text-xs flex items-center gap-1.5">
                          <FileText size={12} className="text-blue-400 flex-shrink-0" />
                          <span className="truncate" title={doc.filename}>{doc.filename}</span>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          <span className="text-[10px] text-slate-400">
                            {Math.round(doc.size_bytes / 1024)} KB
                          </span>
                          <button
                            onClick={() => handleDeleteDocument(doc.filename)}
                            className="p-1 text-slate-400 hover:text-red-400 rounded hover:bg-red-500/10 transition-colors"
                            title={`Remove ${doc.filename}`}
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Settings Section */}
          <div className="border-t border-slate-800/80 pt-2.5">
            <button
              onClick={() => setOpenSettings(!openSettings)}
              className="w-full flex items-center justify-between py-1.5 px-2 text-xs font-semibold text-slate-400 hover:text-white uppercase tracking-wider"
            >
              <span className="flex items-center gap-2">
                <Settings size={14} className="text-purple-400" />
                Settings
              </span>
              {openSettings ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {openSettings && (
              <div className="mt-2 space-y-3 px-1 animate-fade-in text-xs">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">AI Reasoning Engine</label>
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="auto">Smart Automatic (High Speed & Precision)</option>
                    <option value="google/gemini-2.5-flash">High Speed Engine (Real-Time Responses)</option>
                    <option value="qwen/qwen-2.5-72b-instruct">Deep Analysis Engine (Complex Reasoning)</option>
                    <option value="nvidia/nemotron-3-super-120b-a12b:free">High Capacity Engine (Comprehensive Synthesis)</option>
                  </select>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                    <span>Reference Search Depth</span>
                    <span className="text-white font-mono">{topK}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="15"
                    value={topK}
                    onChange={(e) => setTopK(e.target.value)}
                    className="w-full accent-blue-500"
                  />
                </div>
              </div>
            )}
          </div>

          {/* About this App Section */}
          <div className="border-t border-slate-800/80 pt-2.5">
            <button
              onClick={() => setOpenAbout(!openAbout)}
              className="w-full flex items-center justify-between py-1.5 px-2 text-xs font-semibold text-slate-400 hover:text-white uppercase tracking-wider"
            >
              <span className="flex items-center gap-2">
                <Info size={14} className="text-cyan-400" />
                About AskFiles
              </span>
              {openAbout ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {openAbout && (
              <div className="mt-2 space-y-3.5 px-1 animate-fade-in text-[11px] text-slate-300 leading-relaxed max-h-72 overflow-y-auto pr-1">
                <p className="text-slate-400">
                  <strong className="text-white">AskFiles</strong> is an Intelligent Conversational Documents Assistant that simplifies document comprehension with verified page and section citations.
                </p>

                {/* Integrations */}
                <div>
                  <div className="font-semibold text-blue-400 uppercase tracking-wider text-[10px] mb-1.5">
                    Enterprise System Integrations
                  </div>
                  <ul className="space-y-2 text-slate-300">
                    <li className="flex items-start gap-1.5">
                      <Building2 size={12} className="text-blue-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <strong className="text-white">ERP Integration:</strong> Query vendor contracts, procurement POs, and supply compliance.
                        <div className="text-[10px] text-slate-400 italic">e.g. "What are the payment terms in the 2026 Vendor Agreement?"</div>
                      </div>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <Users size={12} className="text-indigo-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <strong className="text-white">CRM Integration:</strong> Real-time lookup of customer SLAs, customized terms, and support escalation SOPs.
                        <div className="text-[10px] text-slate-400 italic">e.g. "What is the guaranteed response time for Tier-1 SLA clients?"</div>
                      </div>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <ShoppingCart size={12} className="text-amber-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <strong className="text-white">POS (Point of Sale):</strong> Check store return policies, warranty rules, and promotion terms at checkout.
                        <div className="text-[10px] text-slate-400 italic">e.g. "Can open-box electronics be exchanged after 14 days?"</div>
                      </div>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <BookOpen size={12} className="text-emerald-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <strong className="text-white">Company Intranet:</strong> Instant search across HR handbooks, engineering guidelines, and security policies.
                        <div className="text-[10px] text-slate-400 italic">e.g. "What is our remote work hardware stipend policy?"</div>
                      </div>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <Search size={12} className="text-cyan-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <strong className="text-white">Research & Legal:</strong> Synthesize complex scientific papers, financial filings, and case law briefs.
                        <div className="text-[10px] text-slate-400 italic">e.g. "Extract the Q3 operating margin trends and EBITDA guidance."</div>
                      </div>
                    </li>
                  </ul>
                </div>

                {/* Key Capabilities */}
                <div>
                  <div className="font-semibold text-blue-400 uppercase tracking-wider text-[10px] mb-1.5">
                    What You Can Do
                  </div>
                  <ul className="space-y-1 text-slate-300 list-disc list-inside">
                    <li>Upload documents via chatbox, sidebar, or main dropzone.</li>
                    <li>Query documents with grounded answers & page citations.</li>
                    <li>Switch multiple chat sessions with saved local history.</li>
                    <li>Manage documents with real-time index synchronization.</li>
                  </ul>
                </div>

                {/* Problems Solved */}
                <div>
                  <div className="font-semibold text-blue-400 uppercase tracking-wider text-[10px] mb-1.5">
                    Problems Solved
                  </div>
                  <ul className="space-y-1 text-slate-300 list-disc list-inside">
                    <li><strong className="text-white">Grounded Responses:</strong> Every answer is verified against exact document sections with citations.</li>
                    <li><strong className="text-white">Zero Search Latency:</strong> Sub-3s retrieval replaces manual scanning.</li>
                    <li><strong className="text-white">Always Available:</strong> Multi-engine automated failover guarantees uninterrupted service.</li>
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* System Status Footer */}
        <div className="border-t border-slate-800 p-3 bg-slate-950/60 flex-shrink-0">
          <div className="grid grid-cols-3 gap-1 text-[10px] text-slate-400">
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${healthStatus.backend ? 'bg-emerald-500' : 'bg-rose-500'}`} />
              <span>AI Engine</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${healthStatus.qdrant ? 'bg-emerald-500' : 'bg-rose-500'}`} />
              <span>Doc Store</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${healthStatus.inngest ? 'bg-emerald-500' : 'bg-rose-500'}`} />
              <span>Service</span>
            </div>
          </div>
        </div>
      </aside>

      {/* =====================================================================
          MAIN CHAT CONTAINER
      ====================================================================== */}
      <main className="flex-1 flex flex-col h-full min-h-0 bg-[#0f172a] relative overflow-hidden">
        {/* Top Header Bar (Permanently Fixed at Top on Mobile & Desktop) */}
        <header className="h-14 border-b border-slate-800/80 bg-[#0f172a] px-3 sm:px-4 flex items-center justify-between flex-shrink-0 z-30 select-none">
          <div className="flex items-center gap-2 sm:gap-3">
            {/* Hamburger / Sidebar Toggle Button with Open/Close Arrow State */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 -ml-1 text-slate-300 hover:text-white rounded-lg hover:bg-slate-800 transition-colors active:scale-95 flex items-center justify-center"
              title={sidebarOpen ? "Close sidebar" : "Open sidebar"}
              aria-label="Toggle navigation menu"
            >
              {sidebarOpen ? (
                <PanelLeftClose size={20} className="text-blue-400" />
              ) : (
                <PanelLeftOpen size={20} />
              )}
            </button>

            {/* AskFiles Logo in Top Bar */}
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 flex items-center justify-center text-white shadow-md shadow-blue-500/20 flex-shrink-0">
                <FileText size={16} className="text-white drop-shadow" />
              </div>
              <div className="flex flex-col">
                <span className="text-base font-bold tracking-tight text-white flex items-center leading-none">
                  Ask<span className="text-blue-400">Files</span>
                </span>
                <span className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold leading-none mt-0.5">
                  Doc AI Assistant
                </span>
              </div>
            </div>
          </div>

          {/* Right Action: Quick New Chat Button */}
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1.5 py-1.5 px-3 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 hover:text-white border border-blue-500/30 font-medium text-xs transition-all active:scale-95 shadow-sm"
            title="Start New Conversation"
            aria-label="New Chat"
          >
            <Plus size={15} className="text-blue-400" />
            <span className="hidden sm:inline">New Chat</span>
          </button>
        </header>

        {/* Floating Upload Progress Modal when in Active Chat */}
        {uploadProgress && uploadProgress.active && activeSession.messages.length > 0 && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
            <div className="w-full max-w-lg">
              <UploadProgressDisplay
                progress={uploadProgress}
                onDismiss={() => setUploadProgress(null)}
                onAskQuestion={(prompt) => handleSendMessage(prompt)}
              />
            </div>
          </div>
        )}

        {/* Scrollable Messages Stream / Main Viewpoint (The ONLY scrollable container) */}
        <div
          ref={chatContainerRef}
          onScroll={handleScroll}
          className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-3 sm:px-6 md:px-8 py-4 sm:py-6 space-y-6 relative"
        >
          {activeSession.messages.length === 0 ? (
            /* Empty State Hero */
            <div className="min-h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center px-3 py-4 sm:px-4 sm:py-8 animate-fade-in">
              {/* AskFiles Brand Logo in Viewpoint */}
              <div className="flex items-center gap-2.5 sm:gap-3 mb-2">
                <div className="w-9 h-9 sm:w-11 sm:h-11 rounded-2xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 flex items-center justify-center text-white shadow-xl shadow-blue-500/20">
                  <FileText size={20} className="text-white drop-shadow sm:hidden" />
                  <FileText size={24} className="text-white drop-shadow hidden sm:block" />
                </div>
                <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center">
                  Ask<span className="text-blue-400">Files</span>
                </span>
              </div>

              {/* Motto */}
              <p className="text-xs text-blue-300 font-medium tracking-wide mb-4 sm:mb-6 max-w-md px-2">
                Intelligent Conversational Documents Assistant that simplify your document
              </p>

              {/* Heading */}
              <h3 className="text-lg sm:text-xl font-bold text-white mb-1.5 sm:mb-2">How can I help with your documents?</h3>
              <p className="text-xs sm:text-sm text-slate-400 mb-4 sm:mb-6 max-w-md px-2">
                Upload PDFs using the sidebar, chatbox, or the box below and ask questions. Answers are grounded in your documents with exact page numbers and section citations.
              </p>

              {/* Main Viewpoint Drag & Drop Upload Zone OR High-Trust Progress Card */}
              {uploadProgress && uploadProgress.active ? (
                <div className="w-full max-w-md my-4 sm:my-6 animate-fade-in">
                  <UploadProgressDisplay
                    progress={uploadProgress}
                    onDismiss={() => setUploadProgress(null)}
                    onAskQuestion={(prompt) => handleSendMessage(prompt)}
                  />
                </div>
              ) : (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragOver(true);
                  }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragOver(false);
                    if (e.dataTransfer.files?.[0]) {
                      handleFileUpload(e.dataTransfer.files[0]);
                    }
                  }}
                  className={`w-full max-w-md p-4 sm:p-5 border-2 border-dashed rounded-2xl mb-4 sm:mb-6 transition-all duration-200 cursor-pointer ${
                    isDragOver
                      ? 'border-blue-400 bg-blue-500/10 scale-[1.02]'
                      : 'border-slate-700 hover:border-slate-500 bg-slate-800/40 hover:bg-slate-800/60'
                  }`}
                >
                  <input
                    type="file"
                    ref={heroFileInputRef}
                    onChange={handleFileUpload}
                    accept=".pdf"
                    className="hidden"
                    id="hero-file-upload"
                  />
                  <label htmlFor="hero-file-upload" className="cursor-pointer flex flex-col items-center">
                    <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center mb-2">
                      <Upload size={20} />
                    </div>
                    <span className="text-sm font-semibold text-slate-200 mb-1">
                      {uploading ? 'Processing & analyzing document...' : 'Click or drag & drop PDF here'}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Upload documents to query with page and section citations
                    </span>
                  </label>
                </div>
              )}

              {/* Suggested Questions */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
                {[
                  'Summarize the core takeaways of the document.',
                  'What are the key technical concepts described?',
                  'Extract all important dates, deadlines and metrics.',
                ].map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleSendMessage(prompt)}
                    className="p-3.5 text-left rounded-xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/50 hover:border-blue-500/50 text-xs text-slate-300 hover:text-white transition-all duration-150"
                  >
                    "{prompt}"
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Message List */
            <div className="max-w-3xl mx-auto space-y-6">
              {activeSession.messages.map((msg, index) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={index}
                    className={`flex gap-3.5 ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in`}
                  >
                    {!isUser && (
                      <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <Sparkles size={16} />
                      </div>
                    )}

                    <div className={`max-w-[85%] sm:max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
                      {/* Message Bubble with Rendered Visual Citation Pills */}
                      <div
                        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                          isUser
                            ? 'bg-blue-600 text-white rounded-tr-none shadow-md shadow-blue-600/10'
                            : 'bg-slate-800/90 text-slate-100 rounded-tl-none border border-slate-700/60 shadow-sm'
                        }`}
                      >
                        <div className="prose prose-invert prose-sm max-w-none break-words">
                          <ReactMarkdown
                            components={{
                              p: ({ children }) => <p className="mb-2.5 last:mb-0 leading-relaxed">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</p>,
                              li: ({ children }) => <li className="leading-relaxed mb-1">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</li>,
                              blockquote: ({ children }) => <blockquote className="border-l-4 border-blue-500/50 pl-3 italic my-2">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</blockquote>,
                              h1: ({ children }) => <h1 className="text-xl font-bold mb-2 text-slate-100">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</h1>,
                              h2: ({ children }) => <h2 className="text-lg font-bold mb-2 text-slate-100">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</h2>,
                              h3: ({ children }) => <h3 className="text-base font-semibold mb-1 text-slate-100">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</h3>,
                              td: ({ children }) => <td className="p-2 border border-slate-700">{renderWithCitations(children, index, msg.sources, scrollToCitation)}</td>,
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      </div>

                      {/* Assistant Telemetry & Citations Footer */}
                      {!isUser && (
                        <div className="mt-2 space-y-2">
                          {/* Latency Display Only */}
                          {msg.latency_ms > 0 && (
                            <div className="flex items-center gap-2 text-[10px] text-slate-400">
                              <span className="font-mono">
                                Response time: {(msg.latency_ms / 1000).toFixed(2)}s
                              </span>
                            </div>
                          )}

                          {/* Failover Alert if any */}
                          {msg.fallback_history && msg.fallback_history.length > 0 && (
                            <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] flex items-start gap-1.5">
                              <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
                              <div>
                                <span>Automatic Failover triggered. Primary engine recovered successfully.</span>
                              </div>
                            </div>
                          )}

                          {/* Academic References / Bottom Citation Layer */}
                          {msg.sources && msg.sources.length > 0 && (
                            <div className="mt-3.5 pt-3 border-t border-slate-700/60">
                              <div className="flex items-center gap-1.5 mb-2 text-xs font-semibold text-slate-300 uppercase tracking-wider">
                                <BookOpen size={13} className="text-blue-400" />
                                <span>References & Citations ({msg.sources.length})</span>
                              </div>

                              <div className="space-y-1.5">
                                {msg.sources.map((src, sIdx) => {
                                  const parsed = parseCitation(src, sIdx + 1);
                                  const refId = `ref-${index}-${parsed.id || sIdx + 1}`;
                                  const isHighlighted = highlightedRef === refId;
                                  return (
                                    <div
                                      id={refId}
                                      key={sIdx}
                                      className={`flex flex-wrap items-center gap-2 p-2.5 rounded-xl text-xs transition-all duration-300 ${
                                        isHighlighted
                                          ? 'bg-blue-950/90 border-2 border-blue-400 ring-2 ring-blue-500/40 shadow-lg shadow-blue-500/25 scale-[1.01]'
                                          : 'bg-slate-800/80 border border-slate-700/70 hover:border-blue-500/40'
                                      }`}
                                    >
                                      {/* [1] -> */}
                                      <div className="flex items-center gap-1">
                                        <span className="px-2 py-0.5 rounded-md bg-blue-600/30 text-blue-300 border border-blue-500/30 font-mono text-xs font-bold flex-shrink-0">
                                          [{parsed.id || sIdx + 1}]
                                        </span>
                                        <span className="text-slate-400 font-mono text-xs">→</span>
                                      </div>

                                      {/* PDF Name */}
                                      <div className="flex items-center gap-1.5 font-medium text-slate-100 min-w-0">
                                        <FileText size={13} className="text-blue-400 flex-shrink-0" />
                                        <span className="font-mono text-xs truncate">{parsed.filename}</span>
                                      </div>

                                      {/* Page No */}
                                      {parsed.page && (
                                        <span className="px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[10px] font-mono font-semibold">
                                          Page {parsed.page}
                                        </span>
                                      )}

                                      {/* Section Title */}
                                      {parsed.section && (
                                        <span className="px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-[10px] font-mono truncate max-w-[220px]">
                                          Section: {parsed.section}
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {isUser && (
                      <div className="w-8 h-8 rounded-lg bg-slate-700 text-slate-300 flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-semibold">
                        You
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Loading Indicator */}
              {loading && (
                <div className="flex gap-3.5 animate-fade-in">
                  <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 flex items-center justify-center flex-shrink-0">
                    <Sparkles size={16} />
                  </div>
                  <div className="bg-slate-800/90 border border-slate-700/60 rounded-2xl rounded-tl-none px-4 py-3 text-sm text-slate-400 flex items-center gap-2">
                    <div className="flex gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-xs">Analyzing documents & formulating answer...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Floating Scroll-to-Bottom Arrow Button */}
          {showScrollBottom && (
            <button
              onClick={scrollToBottom}
              className="absolute bottom-28 right-4 sm:right-8 z-20 p-2.5 rounded-full bg-slate-800/95 hover:bg-slate-700 text-blue-400 hover:text-white border border-slate-700/80 shadow-2xl backdrop-blur transition-all duration-150 active:scale-90 animate-fade-in group"
              title="Scroll to latest messages"
              aria-label="Scroll to bottom"
            >
              <ArrowDown size={18} className="group-hover:translate-y-0.5 transition-transform" />
            </button>
          )}
        </div>

        {/* =====================================================================
            FIXED PINNED BOTTOM INPUT BAR WITH UPLOAD IN CHATBOX
        ====================================================================== */}
        <div className="flex-shrink-0 border-t border-slate-800/80 bg-[#0f172a] px-3 pt-2 pb-[max(0.6rem,env(safe-area-inset-bottom))] sm:px-4 sm:pt-2.5 sm:pb-3 z-20">
          <div className="max-w-3xl mx-auto">
            {/* Inline Upload Message */}
            {uploadMessage && (!uploadProgress || !uploadProgress.active) && (
              <div className="mb-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs flex items-center justify-between">
                <span className="font-mono">{uploadMessage}</span>
                <button onClick={() => setUploadMessage(null)} className="text-slate-400 hover:text-white">
                  <X size={12} />
                </button>
              </div>
            )}

            <div className="relative flex items-end bg-[#1e293b] border border-slate-700/80 rounded-2xl p-2 shadow-2xl focus-within:border-blue-500 transition-colors">
              {/* Paperclip Document Upload inside Chatbox */}
              <input
                type="file"
                ref={chatboxFileInputRef}
                onChange={handleFileUpload}
                accept=".pdf"
                className="hidden"
                id="chatbox-pdf-upload"
              />
              <label
                htmlFor="chatbox-pdf-upload"
                className={`p-2 rounded-xl transition-colors cursor-pointer flex-shrink-0 mr-1 ${
                  uploading
                    ? 'text-blue-400 bg-blue-500/10 animate-pulse'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
                title="Attach and analyze PDF document"
              >
                <Paperclip size={18} />
              </label>

              {/* Textarea */}
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputResize}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about your documents..."
                rows={1}
                disabled={loading}
                className="w-full bg-transparent text-slate-100 text-sm placeholder-slate-400 resize-none px-2 py-1.5 focus:outline-none max-h-40 leading-relaxed"
              />

              {/* Send Button */}
              <button
                onClick={() => handleSendMessage()}
                disabled={!input.trim() || loading}
                className={`p-2.5 rounded-xl transition-all duration-150 flex-shrink-0 ${
                  input.trim() && !loading
                    ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-600/20 active:scale-95'
                    : 'bg-slate-800 text-slate-400 cursor-not-allowed'
                }`}
                title="Send message (Enter)"
              >
                <Send size={16} />
              </button>
            </div>

            {/* Custom Requested Clean Pro Footer */}
            <p className="text-center text-[11px] text-slate-400 mt-2">
              Developed by{' '}
              <a
                href="https://www.linkedin.com/in/devhamed/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 font-medium underline underline-offset-2 transition-colors"
              >
                Hamed Hasan
              </a>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
