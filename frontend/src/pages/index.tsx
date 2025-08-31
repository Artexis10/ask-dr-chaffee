import { useState } from 'react';
import Head from 'next/head';

interface SearchResult {
  id: number;
  title: string;
  text: string;
  url: string;
  start_time_seconds: number;
  end_time_seconds: number;
  similarity: number;
  source_type: string;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`);
      }

      const data = await response.json();
      setResults(data.results || []);
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
              placeholder="What would you like to know? (e.g., 'carnivore diet benefits')"
              className="search-input"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !query.trim()} className="search-button">
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {error && (
          <div className="error">
            <p>Error: {error}</p>
          </div>
        )}

        {results.length > 0 && (
          <div className="results">
            <h2>Found {results.length} relevant clips</h2>
            {results.map((result) => (
              <div key={result.id} className="result-card">
                <div className="result-header">
                  <h3>{result.title}</h3>
                  <span className="source-type">{result.source_type}</span>
                </div>
                <div className="result-content">
                  <p className="transcript-text">{result.text}</p>
                </div>
                <div className="result-footer">
                  <span className="timestamp">
                    {formatTime(result.start_time_seconds)} - {formatTime(result.end_time_seconds)}
                  </span>
                  <span className="similarity">
                    Relevance: {Math.round((1 - result.similarity) * 100)}%
                  </span>
                  {result.url && (
                    <a href={result.url} target="_blank" rel="noopener noreferrer" className="watch-link">
                      Watch Video
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

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

          .result-card {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            transition: box-shadow 0.2s;
          }

          .result-card:hover {
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
          }

          .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
          }

          .result-header h3 {
            margin: 0;
            color: #2c3e50;
            font-size: 1.1rem;
          }

          .source-type {
            background-color: #3498db;
            color: white;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            text-transform: uppercase;
          }

          .transcript-text {
            background: white;
            padding: 1rem;
            border-left: 4px solid #3498db;
            margin: 1rem 0;
            font-style: italic;
          }

          .result-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9rem;
            color: #666;
          }

          .watch-link {
            color: #3498db;
            text-decoration: none;
          }

          .watch-link:hover {
            text-decoration: underline;
          }

          @media (max-width: 600px) {
            .container {
              padding: 1rem;
            }

            .search-input-container {
              flex-direction: column;
            }

            .result-footer {
              flex-direction: column;
              align-items: flex-start;
              gap: 0.5rem;
            }
          }
        `}</style>
      </main>
    </>
  );
}
