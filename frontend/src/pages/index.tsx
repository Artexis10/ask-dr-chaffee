import { useState, useEffect, useRef, useCallback, Suspense, lazy } from 'react';
import Head from 'next/head';
import { SearchBar } from '../components/SearchBar';
import { FilterPills } from '../components/FilterPills';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { Footer } from '../components/Footer';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { DarkModeToggle } from '../components/DarkModeToggle';
import { SearchResult, VideoGroup } from '../types';
import { analytics, setupAnalyticsListeners, trackEvent } from '../utils/analytics';

// Lazy load components that aren't needed for initial render
const SearchResults = lazy(() => import('../components/SearchResults').then(mod => ({ default: mod.SearchResults })));
const AnswerCard = lazy(() => import('../components/AnswerCard').then(mod => ({ default: mod.AnswerCard })));

// Simple fallback component for lazy-loaded components
const LazyLoadFallback = () => <div className="lazy-load-placeholder"></div>;

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
  const [answerData, setAnswerData] = useState<any>(null);
  const [answerLoading, setAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);
  const copyNotificationTimeout = useRef<NodeJS.Timeout | null>(null);

  // Global error handlers to prevent popup errors
  useEffect(() => {
    const handleError = (event: ErrorEvent) => {
      console.error('Global error caught:', event.error);
      event.preventDefault(); // Prevent the error popup
      return false;
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      console.error('Unhandled promise rejection caught:', event.reason);
      event.preventDefault(); // Prevent the error popup
      return false;
    };

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);

    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, []);
  
  // Initialize analytics
  useEffect(() => {
    // Initialize analytics with debug mode in development
    analytics.init({ debug: process.env.NODE_ENV === 'development' });
    
    // Set up event listeners for tracking user interactions
    setupAnalyticsListeners();
    
    // Track page load event
    trackEvent('page_loaded', {
      timestamp: new Date().toISOString(),
      userAgent: navigator.userAgent
    });
    
    return () => {
      // Track page unload event
      trackEvent('page_unloaded');
    };
  }, []);

  // Throttling mechanism to prevent rate limits
  const lastRequestTime = useRef<number>(0);
  const MIN_REQUEST_INTERVAL = 2000; // 2 seconds between requests
  
  // Loading timeout to prevent infinite loading
  const loadingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
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

  // Function to handle answer API call with retry logic and rate limiting
  const performAnswerWithRetry = useCallback(async (query: string, maxRetries: number = 3) => {
    if (!query.trim()) return;
    
    // Check if enough time has passed since last request
    const now = Date.now();
    const timeSinceLastRequest = now - lastRequestTime.current;
    
    if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
      const waitTime = MIN_REQUEST_INTERVAL - timeSinceLastRequest;
      console.log(`Throttling: waiting ${waitTime}ms before next request`);
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }
    
    lastRequestTime.current = Date.now();
    
    setAnswerLoading(true);
    setAnswerError('');
    
    let attempt = 0;
    
    while (attempt < maxRetries) {
      try {
        console.log(`Answer API attempt ${attempt + 1}/${maxRetries}...`);
        
        const params = new URLSearchParams({
          query: query.trim()
        });
        
        console.log('Answer API call URL:', `/api/answer?${params}`);
        
        // Add timeout to the fetch request
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
        
        const response = await fetch(`/api/answer?${params}`, {
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        let responseData;
        
        try {
          // Read the response body only once
          responseData = await response.json();
        } catch (error) {
          const jsonError = error as Error;
          console.error('Failed to parse response as JSON:', jsonError);
          
          // Check if this is an AbortError (timeout)
          if (jsonError.name === 'AbortError' || jsonError.message.includes('abort')) {
            setAnswerError('Request timed out. The server might be unavailable or overloaded.');
            
            // If we're in development, show a more helpful message
            if (process.env.NODE_ENV === 'development') {
              setAnswerError('API request timed out. Make sure your backend services are running properly.');
            }
          } else {
            setAnswerError(`Failed to parse response: ${jsonError.message}`);
          }
          
          return; // Exit the function
        }
        
        if (!response.ok) {
          // Handle rate limit specifically
          if (response.status === 429 || (responseData?.error && responseData.error.toLowerCase().includes('rate limit'))) {
            if (attempt < maxRetries - 1) {
              const backoffTime = Math.pow(2, attempt) * 3000; // Exponential backoff: 3s, 6s, 12s
              console.log(`Rate limited. Retrying in ${backoffTime}ms...`);
              setAnswerError(`Rate limited. Retrying in ${Math.ceil(backoffTime / 1000)} seconds...`);
              await new Promise(resolve => setTimeout(resolve, backoffTime));
              attempt++;
              continue;
            } else {
              // Don't throw, just set the error state
              setAnswerError('Service is currently experiencing high demand. Please try again in a few minutes.');
              return; // Exit the function
            }
          }
          
          // Don't throw, just set the error state
          setAnswerError(responseData?.error || `Answer failed with status: ${response.status}`);
          return; // Exit the function
        }
        
        console.log('Answer API response:', responseData);
        
        if (responseData && (responseData.answer || responseData.citations)) {
          setAnswerData(responseData);
          setAnswerError(''); // Clear any previous error messages
          break; // Success, exit retry loop
        } else {
          // Don't throw, just set the error state
          setAnswerError('No answer data received');
          return; // Exit the function
        }
        
      } catch (err) {
        console.error(`Answer API error (attempt ${attempt + 1}):`, err);
        
        const error = err as Error;
        const errorMessage = error.message || 'Answer request failed';
        
        // Handle network/connection errors specifically
        if (error.name === 'TypeError' && errorMessage.includes('fetch')) {
          setAnswerError('Unable to connect to the server. Please check your internet connection.');
          
          // If we're in development, show a more helpful message
          if (process.env.NODE_ENV === 'development') {
            setAnswerError('API connection failed. Make sure your backend services are running properly.');
          }
          
          return; // Exit the function
        }
        
        // If it's the last attempt or not a retryable error, set final error
        if (attempt === maxRetries - 1 || !errorMessage.toLowerCase().includes('rate limit')) {
          setAnswerError(`Something went wrong: ${errorMessage}`);
          return; // Exit the function instead of breaking
        }
        
        // Show a user-friendly message during retries
        setAnswerError(`Retrying... (attempt ${attempt + 1} of ${maxRetries})`);
        attempt++;
      }
    }
    
    setAnswerLoading(false);
    
    // Clear loading timeout when answer generation completes
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
      loadingTimeoutRef.current = null;
    }
  }, []);

  // Legacy function for backward compatibility
  const performAnswer = useCallback(async (query: string) => {
    return performAnswerWithRetry(query);
  }, [performAnswerWithRetry]);

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
      console.log('Raw results length:', data.results ? data.results.length : 'undefined');
      
      const results = data.results || [];
      console.log('Processed results:', results.length);
      
      let years: string[] = [];
      let grouped: VideoGroup[] = [];
      
      try {
        years = extractYears(results);
        console.log('Extracted years:', years);
      } catch (yearError) {
        console.error('Error extracting years:', yearError);
      }
      
      try {
        grouped = groupResultsByVideo(results);
        console.log('Grouped results:', grouped.length);
      } catch (groupError) {
        console.error('Error grouping results:', groupError);
      }
      
      // Update state all at once with new results
      console.log('Updating state with:', { 
        resultsLength: results.length, 
        groupedLength: grouped.length 
      });
      
      setResults(results);
      setTotalResults(results.length);
      setAvailableYears(years);
      setGroupedResults(grouped);
      
      console.log('State update complete');
      
    } catch (err) {
      console.error('Search error:', err);
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
      setResults([]);
      setGroupedResults([]);
      setTotalResults(0);
    } finally {
      setLoading(false);
      
      // Clear loading timeout when search completes
      if (loadingTimeoutRef.current) {
        clearTimeout(loadingTimeoutRef.current);
        loadingTimeoutRef.current = null;
      }
    }
  }, [extractYears, groupResultsByVideo]);

  // Clear results when query is empty (no debouncing)
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setGroupedResults([]);
      setTotalResults(0);
      setAnswerData(null);
      setAnswerError('');
    }
  }, [query]);

  // Function to handle search form submission with throttling
  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Check if we should throttle this request
    const now = Date.now();
    const timeSinceLastRequest = now - lastRequestTime.current;
    
    if (timeSinceLastRequest < MIN_REQUEST_INTERVAL) {
      const waitTime = Math.ceil((MIN_REQUEST_INTERVAL - timeSinceLastRequest) / 1000);
      setError(`Please wait ${waitTime} seconds before searching again to avoid rate limits.`);
      return;
    }
    
    // Clear any existing loading timeout
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
    }
    
    // Set a timeout to clear loading state after 30 seconds
    loadingTimeoutRef.current = setTimeout(() => {
      if (loading) {
        setLoading(false);
        setError('Request timed out. Please try again or refresh the page.');
      }
      if (answerLoading) {
        setAnswerLoading(false);
        setAnswerError('Answer generation timed out. Please try again or refresh the page.');
      }
    }, 30000); // 30 seconds timeout
    
    // Track search event with analytics
    trackEvent('search_submitted', {
      query,
      sourceFilter,
      yearFilter,
      timestamp: new Date().toISOString()
    });
    
    // Run search and answer in parallel, independently with full error isolation
    Promise.resolve().then(async () => {
      try {
        await performSearch(query, sourceFilter, yearFilter);
        
        // Track successful search
        trackEvent('search_results_loaded', {
          query,
          resultCount: totalResults,
          sourceFilter,
          yearFilter
        });
      } catch (err) {
        console.error('Search failed:', err);
        setError(err instanceof Error ? err.message : 'Search failed');
        
        // Track search error
        trackEvent('search_error', {
          query,
          error: err instanceof Error ? err.message : 'Unknown error',
          sourceFilter,
          yearFilter
        });
      }
    }).catch(err => {
      console.error('Search promise failed:', err);
      setError('Search encountered an error');
    });
    
    Promise.resolve().then(async () => {
      try {
        await performAnswerWithRetry(query); // Use the retry version directly
        
        // Track successful answer generation
        if (answerData) {
          trackEvent('answer_generated', {
            query,
            confidence: answerData.confidence,
            citationCount: answerData.citations?.length || 0,
            cached: answerData.cached || false
          });
        }
      } catch (err) {
        console.error('Answer failed:', err);
        // Answer failure doesn't affect search results
        
        // Track answer error
        trackEvent('answer_error', {
          query,
          error: err instanceof Error ? err.message : 'Unknown error'
        });
      }
    }).catch(err => {
      console.error('Answer promise failed:', err);
    });
  }, [query, sourceFilter, yearFilter, performSearch, performAnswerWithRetry, totalResults, answerData]);

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

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      // Clear copy notification timeout
      if (copyNotificationTimeout.current) {
        clearTimeout(copyNotificationTimeout.current);
      }
      
      // Clear loading timeout
      if (loadingTimeoutRef.current) {
        clearTimeout(loadingTimeoutRef.current);
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

  // Note: Filters are applied when user explicitly searches (no auto-search)

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
          <div className="header-content">
            <div className="logo-container">
              <div className="logo">AC</div>
            </div>
            <h1>Ask Dr. Chaffee</h1>
            <p>Search through Dr. Anthony Chaffee's medical knowledge base</p>
            <div className="search-hint">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 16V12M12 8H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z" 
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span>
                <strong>How it works:</strong> Enter your medical question and get AI-generated answers based on Dr. Chaffee's content, with direct links to video clips.
              </span>
            </div>
          </div>
          <div className="topics-container">
            <div className="topics-title">Popular topics:</div>
            <div className="topics">
              <button onClick={() => setQuery('carnivore diet benefits')}>Carnivore Diet</button>
              <button onClick={() => setQuery('autoimmune conditions treatment')}>Autoimmune Conditions</button>
              <button onClick={() => setQuery('ketosis explained')}>Ketosis</button>
              <button onClick={() => setQuery('plant toxins in food')}>Plant Toxins</button>
              <button onClick={() => setQuery('optimal human diet')}>Optimal Human Diet</button>
            </div>
          </div>
        </div>

        <ErrorBoundary>
          <SearchBar 
            query={query} 
            setQuery={handleSetQuery} 
            handleSearch={handleSearch} 
            loading={loading} 
          />
        </ErrorBoundary>

        <ErrorBoundary>
          <FilterPills 
            sourceFilter={sourceFilter} 
            setSourceFilter={setSourceFilter} 
            yearFilter={yearFilter} 
            setYearFilter={setYearFilter} 
            availableYears={availableYears} 
          />
        </ErrorBoundary>

        {loading && <LoadingSkeleton />}

        {error && (
          <div className="error-message" role="alert">
            ⚠️ {error}
          </div>
        )}

        <ErrorBoundary>
          <Suspense fallback={loading ? <LoadingSkeleton /> : <LazyLoadFallback />}>
            <AnswerCard
              answer={answerData}
              loading={answerLoading}
              error={answerError}
              onPlayClip={(videoId, timestamp) => seekToTimestamp(videoId, timestamp)}
              onCopyLink={copyTimestampLink}
            />
          </Suspense>
        </ErrorBoundary>

        <ErrorBoundary>
          <Suspense fallback={loading ? <LoadingSkeleton /> : <LazyLoadFallback />}>
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
          </Suspense>
        </ErrorBoundary>

        <Footer />

        {showCopyNotification && (
          <div className="copy-notification">
            {copySuccess}
          </div>
        )}
        
        <DarkModeToggle />

        <style jsx>{`
          .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
          }
          
          .header {
            text-align: center;
            margin-bottom: var(--space-6);
            padding: var(--space-6) 0;
            position: relative;
          }
          
          .header-content {
            max-width: 800px;
            margin: 0 auto var(--space-6) auto;
          }
          
          .logo-container {
            margin-bottom: var(--space-4);
            display: flex;
            justify-content: center;
          }
          
          .logo {
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            font-weight: 700;
            box-shadow: var(--shadow-md);
            position: relative;
            overflow: hidden;
          }
          
          .logo::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.3) 0%, rgba(255,255,255,0) 70%);
          }
          
          .header h1 {
            font-size: 2.8rem;
            margin-bottom: var(--space-3);
            color: var(--color-text);
            font-weight: 800;
            background: linear-gradient(to right, var(--color-primary), var(--color-accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-fill-color: transparent;
          }
          
          .header p {
            font-size: 1.3rem;
            color: var(--color-text-light);
            margin-bottom: var(--space-5);
          }

          .search-hint {
            background-color: rgba(59, 130, 246, 0.05);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-xl);
            padding: var(--space-4);
            font-size: 1rem;
            color: var(--color-text);
            text-align: left;
            display: flex;
            align-items: flex-start;
            gap: var(--space-3);
          }

          .search-hint svg {
            flex-shrink: 0;
            margin-top: 3px;
            color: var(--color-primary);
          }

          .search-hint strong {
            color: var(--color-primary-dark);
            font-weight: 600;
          }
          
          .topics-container {
            margin-top: var(--space-6);
            padding-top: var(--space-4);
          }
          
          .topics-title {
            font-size: 1rem;
            color: var(--color-text-light);
            margin-bottom: var(--space-3);
            font-weight: 500;
          }
          
          .topics {
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-2);
            justify-content: center;
          }
          
          .topics button {
            background: var(--color-card);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-lg);
            padding: var(--space-2) var(--space-3);
            font-size: 0.9rem;
            color: var(--color-text);
            cursor: pointer;
            transition: all var(--transition-normal);
          }
          
          .topics button:hover {
            background: rgba(59, 130, 246, 0.1);
            border-color: var(--color-primary-light);
            transform: translateY(-1px);
          }
          
          @media (max-width: 768px) {
            .header h1 {
              font-size: 2.2rem;
            }
            
            .header p {
              font-size: 1.1rem;
            }
            
            .topics {
              gap: var(--space-2);
            }
            
            .topics button {
              font-size: 0.8rem;
              padding: var(--space-1) var(--space-2);
              margin-bottom: var(--space-2);
            }
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
          
          .lazy-load-placeholder {
            min-height: 200px;
            width: 100%;
            background: linear-gradient(90deg, var(--color-background), var(--color-border-light), var(--color-background));
            background-size: 200% 100%;
            animation: shimmer 2s infinite;
            border-radius: var(--radius-xl);
          }
          
          @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
          }
        `}</style>
      </main>
    </>
  );
}
