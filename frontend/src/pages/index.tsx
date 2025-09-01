import { useState, useEffect, useRef, useCallback } from 'react';
import Head from 'next/head';
import { SearchBar } from '../components/SearchBar';
import { FilterPills } from '../components/FilterPills';
import { SearchResults } from '../components/SearchResults';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { Footer } from '../components/Footer';
import { SearchResult, VideoGroup } from '../types';

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'youtube' | 'zoom'>('all');
  const [yearFilter, setYearFilter] = useState<string>('all');
  const [availableYears, setAvailableYears] = useState<string[]>([]);
  const [selectedResultIndex, setSelectedResultIndex] = useState(-1);
  const [totalResults, setTotalResults] = useState(0);
  const [groupedResults, setGroupedResults] = useState<VideoGroup[]>([]);
  const [copySuccess, setCopySuccess] = useState('');
  const [showCopyNotification, setShowCopyNotification] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const copyNotificationTimeout = useRef<NodeJS.Timeout | null>(null);

  // Debug query state changes
  const handleSetQuery = useCallback((newQuery: string) => {
    console.log('Home: setQuery called with:', newQuery);
    setQuery(newQuery);
  }, []);

  useEffect(() => {
    console.log('Home: query state changed to:', query);
  }, [query]);

  // Function to extract years from results
  const extractYears = useCallback((results: SearchResult[]) => {
    const yearsSet = new Set<string>();
    results.forEach((result) => {
      if (result.published_at) {
        const year = new Date(result.published_at).getFullYear().toString();
        yearsSet.add(year);
      }
    });
    return Array.from(yearsSet).sort((a, b) => b.localeCompare(a)); // Sort descending
  }, []);

  // Function to group results by video
  const groupResultsByVideo = useCallback((results: SearchResult[]): VideoGroup[] => {
    const groups: { [key: string]: VideoGroup } = {};
    
    results.forEach((result) => {
      // Extract videoId from YouTube URL or use the result ID for non-YouTube sources
      let videoId = '';
      let videoTitle = result.title || 'Unknown Video';
      
      if (result.source_type === 'youtube' && result.url) {
        const match = result.url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&]+)/);
        if (match && match[1]) {
          videoId = match[1];
        }
      } else {
        // For non-YouTube sources, use the result ID as a unique identifier
        videoId = result.id;
      }
      
      if (!groups[videoId]) {
        groups[videoId] = {
          videoId,
          videoTitle,
          source_type: result.source_type,
          url: result.url,
          clips: []
        };
      }
      
      groups[videoId].clips.push(result);
    });
    
    // Convert to array and sort by relevance (using the highest similarity clip in each group)
    return Object.values(groups).sort((a, b) => {
      const aMaxSimilarity = Math.max(...a.clips.map(clip => clip.similarity));
      const bMaxSimilarity = Math.max(...b.clips.map(clip => clip.similarity));
      return bMaxSimilarity - aMaxSimilarity;
    });
  }, []);

  // Function to perform search API call
  const performSearch = useCallback(async (searchQuery: string, currentSourceFilter: string, currentYearFilter: string) => {
    if (!searchQuery.trim()) return;
    
    console.log('Starting search for:', searchQuery, 'with filters:', { currentSourceFilter, currentYearFilter });
    
    setLoading(true);
    setError('');
    
    try {
      const params = new URLSearchParams({
        q: searchQuery,
        ...(currentSourceFilter !== 'all' && { source_filter: currentSourceFilter }),
        ...(currentYearFilter !== 'all' && { year_filter: currentYearFilter })
      });
      
      console.log('API call URL:', `/api/search?${params}`);
      
      const response = await fetch(`/api/search?${params}`);
      
      if (!response.ok) {
        throw new Error(`Search failed with status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('API response:', data);
      
      const results = data.results || [];
      const years = extractYears(results);
      const grouped = groupResultsByVideo(results);
      
      // Update state all at once with new results
      setResults(results);
      setTotalResults(results.length);
      setAvailableYears(years);
      setGroupedResults(grouped);
      
      console.log('State updated - results:', results.length, 'groups:', grouped.length);
      
    } catch (err) {
      console.error('Search error:', err);
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
      setResults([]);
      setGroupedResults([]);
      setTotalResults(0);
    } finally {
      setLoading(false);
    }
  }, [extractYears, groupResultsByVideo]);

  // Debounced search effect for typing (only triggers on query changes)
  const currentFiltersRef = useRef({ sourceFilter, yearFilter });
  useEffect(() => {
    currentFiltersRef.current = { sourceFilter, yearFilter };
  }, [sourceFilter, yearFilter]);

  useEffect(() => {
    if (!query.trim()) {
      // Clear results when query is empty
      setResults([]);
      setGroupedResults([]);
      setTotalResults(0);
      return;
    }

    // Debounce search while typing - use current filter values at time of execution
    const debounceTimer = setTimeout(() => {
      console.log('Debounced search triggered for query:', query);
      const filters = currentFiltersRef.current;
      performSearch(query, filters.sourceFilter, filters.yearFilter);
    }, 300); // 300ms delay

    return () => {
      clearTimeout(debounceTimer);
    };
  }, [query, performSearch]); // Only depend on query for debouncing

  // Function to handle search form submission
  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    await performSearch(query, sourceFilter, yearFilter);
  }, [query, sourceFilter, yearFilter, performSearch]);

  // Function to highlight search terms in text
  const highlightSearchTerms = (text: string, query: string): string => {
    if (!query.trim()) return text;
    
    const terms = query.trim().split(/\s+/).filter(term => term.length > 2);
    let highlightedText = text;
    
    terms.forEach(term => {
      const regex = new RegExp(`(${term})`, 'gi');
      highlightedText = highlightedText.replace(regex, '<mark>$1</mark>');
    });
    
    return highlightedText;
  };

  // Function to seek to a specific timestamp in YouTube video
  const seekToTimestamp = (videoId: string, seconds: number) => {
    if (typeof window !== 'undefined') {
      const iframe = document.querySelector(`iframe[src*="${videoId}"]`) as HTMLIFrameElement;
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage(JSON.stringify({
          event: 'command',
          func: 'seekTo',
          args: [seconds, true]
        }), '*');
      }
    }
  };

  // Function to copy timestamp link to clipboard
  const copyTimestampLink = (url: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(url)
        .then(() => {
          setCopySuccess('Link copied to clipboard!');
          setShowCopyNotification(true);
          
          if (copyNotificationTimeout.current) {
            clearTimeout(copyNotificationTimeout.current);
          }
          
          copyNotificationTimeout.current = setTimeout(() => {
            setShowCopyNotification(false);
          }, 2000);
        })
        .catch(() => {
          setCopySuccess('Failed to copy link');
          setShowCopyNotification(true);
          
          if (copyNotificationTimeout.current) {
            clearTimeout(copyNotificationTimeout.current);
          }
          
          copyNotificationTimeout.current = setTimeout(() => {
            setShowCopyNotification(false);
          }, 2000);
        });
    }
  };

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (copyNotificationTimeout.current) {
        clearTimeout(copyNotificationTimeout.current);
      }
    };
  }, []);

  // Handle keyboard navigation
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && selectedResultIndex >= 0) {
      const selectedResult = results[selectedResultIndex];
      if (!selectedResult) return;
      
      // Find the group this result belongs to
      const groupedResult = groupedResults.find(group => 
        group.clips.some(clip => clip.id === selectedResult.id)
      );
      
      if (groupedResult && selectedResult.source_type === 'youtube') {
        // Enter: Play in embedded player
        seekToTimestamp(groupedResult.videoId, Math.floor(selectedResult.start_time_seconds));
      }
    }
  };

  // Add keyboard event listener
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [selectedResultIndex, results, groupedResults]);

  // Re-run search immediately when filters change (no debouncing for filters)
  const prevFilters = useRef({ sourceFilter, yearFilter });
  useEffect(() => {
    const filtersChanged = prevFilters.current.sourceFilter !== sourceFilter || 
                          prevFilters.current.yearFilter !== yearFilter;
    
    if (query.trim() && filtersChanged) {
      console.log('Filter change triggered immediate search');
      performSearch(query, sourceFilter, yearFilter);
    }
    
    prevFilters.current = { sourceFilter, yearFilter };
  }, [sourceFilter, yearFilter, query, performSearch]);

  return (
    <>
      <Head>
        <title>Ask Dr. Chaffee | Search Medical Knowledge</title>
        <meta name="description" content="Search through Dr. Anthony Chaffee's medical knowledge" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main className="container">
        <div className="header">
          <h1>Ask Dr. Chaffee</h1>
          <p>Search through Dr. Anthony Chaffee's YouTube videos and Zoom recordings</p>
        </div>

        <SearchBar 
          query={query} 
          setQuery={handleSetQuery} 
          handleSearch={handleSearch} 
          loading={loading} 
        />

        <FilterPills 
          sourceFilter={sourceFilter} 
          setSourceFilter={setSourceFilter} 
          yearFilter={yearFilter} 
          setYearFilter={setYearFilter} 
          availableYears={availableYears} 
        />

        {loading && <LoadingSkeleton />}

        {error && (
          <div className="error-message" role="alert">
            ⚠️ {error}
          </div>
        )}

        <SearchResults 
          results={results}
          query={query}
          loading={loading}
          totalResults={totalResults}
          groupedResults={groupedResults}
          sourceFilter={sourceFilter}
          highlightSearchTerms={highlightSearchTerms}
          seekToTimestamp={seekToTimestamp}
          copyTimestampLink={copyTimestampLink}
        />

        <Footer />

        {showCopyNotification && (
          <div className="copy-notification">
            {copySuccess}
          </div>
        )}

        <style jsx>{`
          .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
          }
          
          .header {
            text-align: center;
            margin-bottom: 2rem;
          }
          
          .header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            color: #2d3748;
          }
          
          .header p {
            font-size: 1.2rem;
            color: #4a5568;
          }
          
          .error-message {
            background-color: #fed7d7;
            color: #c53030;
            padding: 1rem;
            border-radius: 0.5rem;
            margin: 1rem 0;
          }
          
          .copy-notification {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background-color: #2d3748;
            color: white;
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            animation: fadeIn 0.3s, fadeOut 0.3s 1.7s;
            z-index: 1000;
          }
          
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          
          @keyframes fadeOut {
            from { opacity: 1; transform: translateY(0); }
            to { opacity: 0; transform: translateY(20px); }
          }
        `}</style>
      </main>
    </>
  );
}
