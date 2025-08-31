import { useState } from 'react';
import Head from 'next/head';

interface SearchResult {
  id: number;
  title: string;
  text: string;
  url: string;
  start_time_seconds: number;
  end_time_seconds: number;
  similarity: string; // Now a percentage string from API
  source_type: string;
  published_at?: string;
}

interface GroupedResults {
  videoId: string;
  videoTitle: string;
  url: string;
  source_type: string;
  clips: SearchResult[];
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'youtube' | 'zoom'>('all');
  const [yearFilter, setYearFilter] = useState<string>('');
  const [availableYears, setAvailableYears] = useState<string[]>([]);
  const [selectedResultIndex, setSelectedResultIndex] = useState(-1);
  const [totalResults, setTotalResults] = useState(0);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError('');
    setResults([]);

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          query: query.trim(),
          source_filter: sourceFilter,
          year_filter: yearFilter || undefined
        }),
      });
      
      // Track search analytics
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('analytics', {
          detail: { event: 'search_submitted', query: query.trim(), filters: { sourceFilter, yearFilter } }
        }));
      }

      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`);
      }

      const data = await response.json();
      setResults(data.results || []);
      setTotalResults(data.total || 0);
      
      // Extract available years for filter
      const yearSet = new Set(
        (data.results || [])
          .map((r: SearchResult) => r.published_at ? new Date(r.published_at).getFullYear().toString() : null)
          .filter(Boolean)
      );
      const years = Array.from(yearSet).filter(y => y !== null).sort((a, b) => parseInt(b as string) - parseInt(a as string));
      setAvailableYears(years as string[]);
      
      setSelectedResultIndex(-1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const extractVideoId = (url: string): string => {
    const match = url.match(/[?&]v=([^&]+)/) || url.match(/youtu\.be\/([^?]+)/);
    return match ? match[1] : '';
  };

  const getVideoTitle = (title: string): string => {
    // Remove "Video " prefix if present
    return title.replace(/^Video \w+$/, 'Dr. Chaffee Video');
  };

  const groupResultsByVideo = (results: SearchResult[]): GroupedResults[] => {
    const groups: { [key: string]: GroupedResults } = {};
    
    results.forEach(result => {
      const videoId = extractVideoId(result.url);
      const baseUrl = result.url.split('&t=')[0]; // Remove timestamp from grouping URL
      
      if (!groups[videoId]) {
        groups[videoId] = {
          videoId,
          videoTitle: getVideoTitle(result.title),
          url: baseUrl,
          source_type: result.source_type,
          clips: []
        };
      }
      
      groups[videoId].clips.push(result);
    });
    
    // Sort clips within each video by start time
    Object.values(groups).forEach(group => {
      group.clips.sort((a, b) => a.start_time_seconds - b.start_time_seconds);
    });
    
    return Object.values(groups);
  };

  const groupedResults = groupResultsByVideo(results);

  // Function to highlight search query in text
  const highlightSearchTerms = (text: string, searchQuery: string): string => {
    if (!searchQuery.trim()) return text;
    
    const terms = searchQuery.toLowerCase().split(/\s+/).filter(term => term.length > 2);
    let highlightedText = text;
    
    terms.forEach(term => {
      const regex = new RegExp(`(${term})`, 'gi');
      highlightedText = highlightedText.replace(regex, '<mark class="search-highlight">$1</mark>');
    });
    
    return highlightedText;
  };

  // Function to seek video to specific timestamp
  const seekToTimestamp = (videoId: string, seconds: number) => {
    const iframe = document.querySelector(`iframe[src*="${videoId}"]`) as HTMLIFrameElement;
    if (iframe && iframe.contentWindow) {
      // Send message to YouTube player to seek to timestamp
      iframe.contentWindow.postMessage(
        `{"event":"command","func":"seekTo","args":[${seconds}, true]}`,
        'https://www.youtube.com'
      );
      
      // Scroll video into view and track analytics
      iframe.scrollIntoView({ behavior: 'smooth', block: 'center' });
      
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('analytics', {
          detail: { event: 'result_clicked_play_here', videoId, timestamp: seconds }
        }));
      }
    }
  };

  // Copy timestamp link to clipboard
  const copyTimestampLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      // Could add a toast notification here
    } catch (err) {
      console.error('Failed to copy link:', err);
    }
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (results.length === 0) return;
    
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedResultIndex(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedResultIndex(prev => Math.max(prev - 1, -1));
    } else if (e.key === 'Enter' && selectedResultIndex >= 0) {
      e.preventDefault();
      const selectedResult = results[selectedResultIndex];
      const groupedResult = groupedResults.find(g => 
        g.clips.some(c => c.id === selectedResult.id)
      );
      
      if (e.shiftKey) {
        // Shift+Enter: Open in YouTube
        window.open(selectedResult.url, '_blank');
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('analytics', {
            detail: { event: 'result_clicked_youtube', url: selectedResult.url }
          }));
        }
      } else if (groupedResult && selectedResult.source_type === 'youtube') {
        // Enter: Play in embedded player
        seekToTimestamp(groupedResult.videoId, Math.floor(selectedResult.start_time_seconds));
      }
    }
  };

  return (
    <>
      <Head>
        <title>Ask Dr. Chaffee - Search Transcripts</title>
        <meta name="description" content="Search Dr. Anthony Chaffee's YouTube and Zoom recordings" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main className="container">
        <div className="header">
          <h1>Ask Dr. Chaffee</h1>
          <p>Search through Dr. Anthony Chaffee's YouTube videos and Zoom recordings</p>
        </div>

        <form onSubmit={handleSearch} className="search-form">
          <div className="search-input-container">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="🔍 Ask Dr. Chaffee about carnivore diet, plant toxins, health..."
              className="search-input"
              disabled={loading}
              aria-label="Search Dr. Chaffee's content"
            />
            <button type="submit" disabled={loading || !query.trim()} className="search-button">
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
          
          {/* Filter Pills */}
          <div className="filters-container">
            <div className="filter-group">
              <label className="filter-label">Source:</label>
              <div className="filter-pills">
                <button
                  type="button"
                  className={`filter-pill ${sourceFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setSourceFilter('all')}
                  aria-pressed={sourceFilter === 'all'}
                >
                  All
                </button>
                <button
                  type="button"
                  className={`filter-pill ${sourceFilter === 'youtube' ? 'active' : ''}`}
                  onClick={() => setSourceFilter('youtube')}
                  aria-pressed={sourceFilter === 'youtube'}
                >
                  📺 YouTube
                </button>
                <button
                  type="button"
                  className={`filter-pill ${sourceFilter === 'zoom' ? 'active' : ''}`}
                  onClick={() => setSourceFilter('zoom')}
                  aria-pressed={sourceFilter === 'zoom'}
                >
                  💼 Zoom
                </button>
              </div>
            </div>
            
            {availableYears.length > 0 && (
              <div className="filter-group">
                <label className="filter-label">Year:</label>
                <select
                  value={yearFilter}
                  onChange={(e) => setYearFilter(e.target.value)}
                  className="year-filter"
                  aria-label="Filter by year"
                >
                  <option value="">All Years</option>
                  {availableYears.map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </form>

        {error && (
          <div className="error">
            <p>Error: {error}</p>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="loading-skeleton" aria-live="polite" aria-label="Loading search results">
            {Array.from({length: 3}).map((_, i) => (
              <div key={i} className="skeleton-card">
                <div className="skeleton-header"></div>
                <div className="skeleton-video"></div>
                <div className="skeleton-text"></div>
                <div className="skeleton-text"></div>
              </div>
            ))}
          </div>
        )}
        
        {results.length > 0 && !loading && (
          <div className="results" role="main">
            <h2 aria-live="polite">
              🎯 Found {totalResults} relevant clip{totalResults !== 1 ? 's' : ''} in {groupedResults.length} video{groupedResults.length !== 1 ? 's' : ''}
            </h2>
            {groupedResults.map((group) => (
              <div key={group.videoId} className="video-card">
                <div className="video-header">
                  <h3>🎥 {group.videoTitle}</h3>
                  <span className="source-type">{group.source_type === 'youtube' ? '📺 YouTube' : '💼 Zoom'}</span>
                </div>
                
                {group.source_type === 'youtube' && group.videoId && (
                  <div className="video-embed">
                    <iframe
                      width="100%"
                      height="315"
                      src={`https://www.youtube.com/embed/${group.videoId}?enablejsapi=1&origin=${window.location.origin}`}
                      title={group.videoTitle}
                      frameBorder="0"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                    ></iframe>
                  </div>
                )}
                
                <div className="clips-container">
                  <h4>📄 {group.clips.length} relevant clip{group.clips.length !== 1 ? 's' : ''} found:</h4>
                  {group.clips.map((clip) => (
                    <div key={clip.id} className="clip-card">
                      <div className="clip-content">
                        <p 
                          className="transcript-text"
                          dangerouslySetInnerHTML={{
                            __html: highlightSearchTerms(clip.text, query)
                          }}
                        ></p>
                      </div>
                      <div className="clip-footer">
                        <span className="timestamp">
                          🕒 {formatTime(clip.start_time_seconds)} - {formatTime(clip.end_time_seconds)}
                        </span>
                        <span className="similarity">
                          📊 {clip.similarity}% relevant
                        </span>
                        <div className="clip-actions">
                          {group.source_type === 'youtube' && (
                            <button 
                              onClick={() => seekToTimestamp(group.videoId, Math.floor(clip.start_time_seconds))}
                              className="seek-button"
                              title="Jump to this moment in embedded video"
                              aria-label={`Play video at ${formatTime(clip.start_time_seconds)}`}
                            >
                              🎯 Play Here
                            </button>
                          )}
                          <button
                            onClick={() => copyTimestampLink(clip.url)}
                            className="copy-button"
                            title="Copy timestamp link"
                            aria-label="Copy link to clipboard"
                          >
                            📋 Copy Link
                          </button>
                          <a 
                            href={clip.url} 
                            target="_blank" 
                            rel="noopener noreferrer" 
                            className="watch-link"
                            onClick={() => {
                              if (typeof window !== 'undefined') {
                                window.dispatchEvent(new CustomEvent('analytics', {
                                  detail: { event: 'result_clicked_youtube', url: clip.url }
                                }));
                              }
                            }}
                          >
                            ▶️ Open in YouTube
                          </a>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <footer className="footer">
          <div className="footer-content">
            <p className="disclaimer">
              ⚠️ <strong>Educational Content Only:</strong> This content is for educational purposes only and should not be considered medical advice. 
              Always consult with your healthcare provider before making any changes to your diet or health regimen.
            </p>
            <div className="footer-links">
              <a 
                href="https://www.youtube.com/@anthonychaffeemd" 
                target="_blank" 
                rel="noopener noreferrer"
                className="official-channel-link"
              >
                📺 Visit Dr. Chaffee's Official YouTube Channel
              </a>
            </div>
          </div>
        </footer>

        <style jsx>{`
          .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
          }

          .header {
            text-align: center;
            margin-bottom: 3rem;
          }

          .header h1 {
            font-size: 2.5rem;
            color: #2c3e50;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
          }

          .header p {
            font-size: 1.1rem;
            color: #666;
          }

          .search-form {
            margin-bottom: 2rem;
          }

          .search-input-container {
            display: flex;
            gap: 1rem;
            align-items: center;
          }

          .search-input {
            flex: 1;
            padding: 1rem;
            font-size: 1rem;
            border: 2px solid #ddd;
            border-radius: 8px;
            outline: none;
            transition: border-color 0.2s;
          }

          .search-input:focus {
            border-color: #3498db;
          }

          .search-button {
            padding: 1rem 2rem;
            font-size: 1rem;
            background-color: #3498db;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: background-color 0.2s;
          }

          .search-button:hover:not(:disabled) {
            background-color: #2980b9;
          }

          .search-button:disabled {
            background-color: #bdc3c7;
            cursor: not-allowed;
          }

          .error {
            background-color: #f8d7da;
            color: #721c24;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 2rem;
          }

          .results h2 {
            color: #2c3e50;
            margin-bottom: 1.5rem;
          }

          .video-card {
            background: #fff;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            padding: 0;
            margin-bottom: 2rem;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
          }

          .video-card:hover {
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            transform: translateY(-2px);
          }

          .video-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
          }

          .video-header h3 {
            margin: 0;
            font-size: 1.3rem;
            font-weight: 600;
          }

          .source-type {
            background-color: rgba(255, 255, 255, 0.2);
            color: white;
            padding: 0.4rem 0.8rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
          }

          .video-embed {
            position: relative;
            width: 100%;
            height: 0;
            padding-bottom: 56.25%; /* 16:9 aspect ratio */
          }

          .video-embed iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
          }

          .clips-container {
            padding: 1.5rem;
          }

          .clips-container h4 {
            margin: 0 0 1rem 0;
            color: #2c3e50;
            font-size: 1.1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e9ecef;
          }

          .clip-card {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
            transition: all 0.2s ease;
          }

          .clip-card:hover {
            background: #fff;
            border-color: #3498db;
            box-shadow: 0 2px 8px rgba(52, 152, 219, 0.1);
          }

          .clip-card:last-child {
            margin-bottom: 0;
          }

          .transcript-text {
            background: white;
            padding: 1rem;
            border-left: 4px solid #3498db;
            margin: 0 0 1rem 0;
            font-style: italic;
            line-height: 1.6;
          }

          .clip-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85rem;
            color: #666;
            flex-wrap: wrap;
            gap: 1rem;
          }

          .watch-link {
            color: #3498db;
            text-decoration: none;
            font-weight: 500;
            padding: 0.3rem 0.8rem;
            border: 1px solid #3498db;
            border-radius: 6px;
            transition: all 0.2s ease;
          }

          .watch-link:hover {
            background: #3498db;
            color: white;
            text-decoration: none;
          }

          .timestamp {
            font-weight: 500;
            color: #495057;
          }

          .similarity {
            font-weight: 500;
            color: #28a745;
          }

          .filters-container {
            margin-top: 1rem;
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
            align-items: center;
          }

          .filter-group {
            display: flex;
            gap: 0.5rem;
            align-items: center;
          }

          .filter-label {
            font-weight: 500;
            color: #495057;
            font-size: 0.9rem;
          }

          .filter-pills {
            display: flex;
            gap: 0.5rem;
          }

          .filter-pill {
            padding: 0.4rem 0.8rem;
            border: 2px solid #dee2e6;
            background: white;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            color: #495057;
          }

          .filter-pill:hover {
            border-color: #667eea;
            background: #f8f9ff;
          }

          .filter-pill.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: #667eea;
          }

          .year-filter {
            padding: 0.4rem 0.8rem;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            font-size: 0.85rem;
            background: white;
            color: #495057;
          }

          .year-filter:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
          }

          .search-highlight {
            background: linear-gradient(120deg, #ffd93d 0%, #ffd93d 100%);
            background-size: 100% 0.2em;
            background-repeat: no-repeat;
            background-position: 0 90%;
            padding: 0.1em 0;
            font-weight: 500;
          }

          .clip-actions {
            display: flex;
            gap: 0.8rem;
            align-items: center;
            flex-wrap: wrap;
          }

          .seek-button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 0.4rem 0.8rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 4px rgba(102, 126, 234, 0.2);
          }

          .seek-button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(102, 126, 234, 0.3);
          }

          .seek-button:active {
            transform: translateY(0);
            box-shadow: 0 2px 4px rgba(102, 126, 234, 0.2);
          }

          .copy-button {
            background: #28a745;
            color: white;
            border: none;
            padding: 0.4rem 0.8rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 4px rgba(40, 167, 69, 0.2);
          }

          .copy-button:hover {
            background: #218838;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(40, 167, 69, 0.3);
          }

          .loading-skeleton {
            space-between: 2rem;
          }

          .skeleton-card {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            animation: pulse 1.5s ease-in-out infinite alternate;
          }

          .skeleton-header {
            height: 2rem;
            background: #dee2e6;
            border-radius: 6px;
            margin-bottom: 1rem;
            width: 70%;
          }

          .skeleton-video {
            height: 200px;
            background: #dee2e6;
            border-radius: 8px;
            margin-bottom: 1rem;
          }

          .skeleton-text {
            height: 1rem;
            background: #dee2e6;
            border-radius: 4px;
            margin-bottom: 0.5rem;
          }

          .skeleton-text:last-child {
            width: 60%;
          }

          @keyframes pulse {
            0% {
              opacity: 1;
            }
            100% {
              opacity: 0.7;
            }
          }

          @media (max-width: 768px) {
            .container {
              padding: 1rem;
              max-width: 100%;
            }

            .search-input-container {
              flex-direction: column;
            }

            .video-header {
              padding: 1rem;
            }

            .video-header h3 {
              font-size: 1.1rem;
            }

            .clips-container {
              padding: 1rem;
            }

            .clip-footer {
              flex-direction: column;
              align-items: flex-start;
              gap: 0.5rem;
            }

            .filters-container {
              flex-direction: column;
              gap: 1rem;
              align-items: flex-start;
            }

            .filter-group {
              flex-direction: column;
              align-items: flex-start;
            }

            .clip-actions {
              flex-direction: column;
              gap: 0.5rem;
            }

            .seek-button {
              align-self: stretch;
              text-align: center;
              padding: 0.5rem;
            }

            .copy-button {
              align-self: stretch;
              text-align: center;
              padding: 0.5rem;
            }

            .watch-link {
              align-self: stretch;
              text-align: center;
              padding: 0.5rem;
              background: #3498db;
              color: white !important;
              border-radius: 6px;
              text-decoration: none !important;
            }
          }

          .footer {
            margin-top: 4rem;
            padding-top: 2rem;
            border-top: 1px solid #dee2e6;
            background: #f8f9fa;
          }

          .footer-content {
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            text-align: center;
          }

          .disclaimer {
            background: #fff3cd;
            color: #856404;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
            line-height: 1.5;
          }

          .footer-links {
            display: flex;
            justify-content: center;
            gap: 2rem;
          }

          .official-channel-link {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.5rem;
            background: linear-gradient(135deg, #ff0000 0%, #cc0000 100%);
            color: white;
            text-decoration: none;
            border-radius: 25px;
            font-weight: 500;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(255, 0, 0, 0.2);
          }

          .official-channel-link:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(255, 0, 0, 0.3);
            text-decoration: none;
            color: white;
          }

          /* Focus states for accessibility */
          .search-input:focus,
          .filter-pill:focus,
          .year-filter:focus,
          .seek-button:focus,
          .copy-button:focus,
          .watch-link:focus,
          .official-channel-link:focus {
            outline: 2px solid #667eea;
            outline-offset: 2px;
          }
        `}</style>
      </main>
    </>
  );
}
