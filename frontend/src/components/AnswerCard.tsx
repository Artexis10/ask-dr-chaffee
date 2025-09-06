import { useState } from 'react';

interface Citation {
  video_id: string;
  t_start_s: number;
  published_at: string;
}

interface AnswerData {
  answer_md: string;
  citations: Citation[];
  confidence: number;
  notes?: string;
  used_chunk_ids: string[];
  cached?: boolean;
  cache_date?: string;
}

interface AnswerCardProps {
  answer: AnswerData | null;
  loading: boolean;
  error?: string;
  onPlayClip?: (videoId: string, timestamp: number) => void;
  onCopyLink?: (url: string) => void;
}

export function AnswerCard({ answer, loading, error, onPlayClip, onCopyLink }: AnswerCardProps) {
  const [showSources, setShowSources] = useState(false);

  if (loading) {
    return (
      <div className="answer-card loading">
        <div className="answer-header">
          <div className="answer-title">
            <div className="loading-icon">🔄</div>
            <h3>Generating answer from Dr. Chaffee's recordings...</h3>
          </div>
        </div>
        <div className="loading-content">
          <div className="loading-bar"></div>
          <p>Searching through transcripts and synthesizing response...</p>
        </div>
        <style jsx>{`
          .answer-card.loading {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
          }
          .answer-header {
            display: flex;
            align-items: center;
            margin-bottom: 16px;
          }
          .answer-title {
            display: flex;
            align-items: center;
            gap: 12px;
          }
          .loading-icon {
            font-size: 20px;
            animation: spin 1s linear infinite;
          }
          .answer-title h3 {
            margin: 0;
            font-size: 18px;
            font-weight: 600;
          }
          .loading-content p {
            margin: 8px 0 0 0;
            opacity: 0.9;
            font-size: 14px;
          }
          .loading-bar {
            height: 3px;
            background: rgba(255, 255, 255, 0.3);
            border-radius: 2px;
            overflow: hidden;
            margin-bottom: 12px;
          }
          .loading-bar::after {
            content: '';
            display: block;
            height: 100%;
            background: rgba(255, 255, 255, 0.8);
            border-radius: 2px;
            animation: loading-progress 2s ease-in-out infinite;
          }
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
          @keyframes loading-progress {
            0% { width: 0%; margin-left: 0%; }
            50% { width: 60%; margin-left: 20%; }
            100% { width: 0%; margin-left: 100%; }
          }
        `}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="answer-card error">
        <div className="answer-header">
          <div className="answer-title">
            <span className="error-icon">⚠️</span>
            <h3>Unable to generate answer</h3>
          </div>
        </div>
        <p className="error-message">{error}</p>
        <style jsx>{`
          .answer-card.error {
            background: #fed7d7;
            color: #c53030;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            border: 1px solid #feb2b2;
          }
          .answer-header {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
          }
          .answer-title {
            display: flex;
            align-items: center;
            gap: 8px;
          }
          .answer-title h3 {
            margin: 0;
            font-size: 16px;
            font-weight: 600;
          }
          .error-message {
            margin: 0;
            font-size: 14px;
          }
        `}</style>
      </div>
    );
  }

  if (!answer) {
    return null;
  }

  // Parse inline citations and convert to clickable chips
  const renderAnswerWithCitations = (text: string) => {
    const citationRegex = /\[([^@]+)@(\d+:\d+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = citationRegex.exec(text)) !== null) {
      // Add text before citation
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      // Find corresponding citation data
      const videoId = match[1];
      const timestamp = match[2];
      const citation = answer.citations.find(c => 
        c.video_id === videoId && formatTimestamp(c.t_start_s) === timestamp
      );

      if (citation) {
        parts.push(
          <span
            key={match.index}
            className="citation-chip"
            onClick={() => {
              if (onPlayClip) {
                onPlayClip(videoId, citation.t_start_s);
              }
            }}
            title={`Play at ${timestamp} • ${citation.published_at}`}
          >
            clip {timestamp}
          </span>
        );
      } else {
        parts.push(`[${match[1]}@${match[2]}]`);
      }

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts;
  };

  const formatTimestamp = (seconds: number): string => {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const confidenceColor = answer.confidence >= 0.8 
    ? '#10b981' 
    : answer.confidence >= 0.6 
    ? '#f59e0b' 
    : '#ef4444';

  const confidenceLabel = answer.confidence >= 0.8
    ? 'High'
    : answer.confidence >= 0.6
    ? 'Medium'
    : 'Low';

  return (
    <div className="answer-card">
      <div className="answer-header">
        <div className="answer-title">
          <span className="answer-icon">💡</span>
          <h3>Dr. Chaffee's Answer</h3>
        </div>
        <div className="answer-meta">
          <span 
            className="confidence-badge"
            style={{ backgroundColor: confidenceColor }}
          >
            {confidenceLabel} Confidence
          </span>
          {answer.cached && (
            <span className="cache-badge" title={`Cached on ${formatDate(answer.cache_date!)}`}>
              📋 Cached
            </span>
          )}
        </div>
      </div>

      <div className="answer-content">
        <p className="answer-text">
          {renderAnswerWithCitations(answer.answer_md)}
        </p>

        {answer.notes && (
          <div className="answer-notes">
            <strong>Note:</strong> {answer.notes}
          </div>
        )}
      </div>

      <div className="answer-footer">
        <div className="sources-toggle" onClick={() => setShowSources(!showSources)}>
          <span>See sources ({answer.citations.length})</span>
          <span className={`toggle-arrow ${showSources ? 'expanded' : ''}`}>▼</span>
        </div>
        
        {showSources && (
          <div className="sources-list">
            {answer.citations.map((citation, index) => (
              <div key={index} className="source-item">
                <div className="source-info">
                  <button
                    className="play-button"
                    onClick={() => onPlayClip && onPlayClip(citation.video_id, citation.t_start_s)}
                    title="Play this clip"
                  >
                    ▶️
                  </button>
                  <span className="source-timestamp">
                    {formatTimestamp(citation.t_start_s)}
                  </span>
                  <span className="source-date">
                    {formatDate(citation.published_at)}
                  </span>
                </div>
                <button
                  className="copy-link-button"
                  onClick={() => {
                    const url = `https://youtube.com/watch?v=${citation.video_id}&t=${Math.floor(citation.t_start_s)}s`;
                    onCopyLink && onCopyLink(url);
                  }}
                  title="Copy YouTube link"
                >
                  🔗
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <style jsx>{`
        .answer-card {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border-radius: 12px;
          padding: 24px;
          margin-bottom: 24px;
          box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
        }

        .answer-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }

        .answer-title {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .answer-icon {
          font-size: 20px;
        }

        .answer-title h3 {
          margin: 0;
          font-size: 18px;
          font-weight: 600;
        }

        .answer-meta {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .confidence-badge, .cache-badge {
          padding: 4px 8px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 500;
          color: white;
        }

        .cache-badge {
          background: rgba(255, 255, 255, 0.2);
        }

        .answer-content {
          margin-bottom: 20px;
        }

        .answer-text {
          font-size: 16px;
          line-height: 1.6;
          margin: 0 0 12px 0;
        }

        .citation-chip {
          background: rgba(255, 255, 255, 0.2);
          color: white;
          padding: 2px 8px;
          border-radius: 12px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          display: inline-block;
          margin: 0 2px;
        }

        .citation-chip:hover {
          background: rgba(255, 255, 255, 0.3);
          transform: translateY(-1px);
        }

        .answer-notes {
          background: rgba(255, 255, 255, 0.1);
          padding: 12px;
          border-radius: 8px;
          font-size: 14px;
          margin-top: 12px;
        }

        .answer-footer {
          border-top: 1px solid rgba(255, 255, 255, 0.2);
          padding-top: 16px;
        }

        .sources-toggle {
          display: flex;
          justify-content: space-between;
          align-items: center;
          cursor: pointer;
          font-size: 14px;
          font-weight: 500;
          padding: 8px 0;
          transition: opacity 0.2s ease;
        }

        .sources-toggle:hover {
          opacity: 0.8;
        }

        .toggle-arrow {
          transition: transform 0.2s ease;
        }

        .toggle-arrow.expanded {
          transform: rotate(180deg);
        }

        .sources-list {
          margin-top: 12px;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          padding-top: 12px;
        }

        .source-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 0;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .source-item:last-child {
          border-bottom: none;
        }

        .source-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .play-button, .copy-link-button {
          background: rgba(255, 255, 255, 0.2);
          border: none;
          border-radius: 6px;
          padding: 4px 8px;
          cursor: pointer;
          font-size: 12px;
          color: white;
          transition: background 0.2s ease;
        }

        .play-button:hover, .copy-link-button:hover {
          background: rgba(255, 255, 255, 0.3);
        }

        .source-timestamp {
          font-weight: 600;
          font-family: monospace;
        }

        .source-date {
          font-size: 12px;
          opacity: 0.8;
        }

        @media (max-width: 768px) {
          .answer-card {
            padding: 16px;
          }

          .answer-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
          }

          .answer-meta {
            align-self: flex-end;
          }

          .source-info {
            gap: 8px;
            font-size: 14px;
          }
        }
      `}</style>
    </div>
  );
}
