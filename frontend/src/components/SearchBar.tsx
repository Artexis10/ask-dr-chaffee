import React, { useState, useRef, useEffect } from 'react';

interface SearchBarProps {
  query: string;
  setQuery: (query: string) => void;
  handleSearch: (e: React.FormEvent) => void;
  loading: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ query, setQuery, handleSearch, loading }) => {
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  
  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      handleSearch(e);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setQuery(value);
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setQuery('');
      inputRef.current?.blur();
    }
  };
  
  // Focus input on page load
  useEffect(() => {
    if (inputRef.current && !query) {
      inputRef.current.focus();
    }
  }, []);

  return (
    <form onSubmit={onSubmit} className="search-form">
      <div className={`search-container ${isFocused ? 'focused' : ''}`}>
        <div className="search-icon">
          {loading ? (
            <div className="spinner"></div>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M21 21L16.65 16.65M19 11C19 15.4183 15.4183 19 11 19C6.58172 19 3 15.4183 3 11C3 6.58172 6.58172 3 11 3C15.4183 3 19 6.58172 19 11Z" 
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </div>
        <input
          ref={inputRef}
          type="text"
          className="search-input"
          placeholder="Ask Dr. Chaffee about carnivore diet, autoimmune conditions, ketosis..."
          value={query}
          onChange={handleInputChange}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          aria-label="Search query"
          disabled={loading}
        />
        {query && (
          <button 
            type="button" 
            className="clear-button"
            onClick={() => setQuery('')}
            aria-label="Clear search"
            tabIndex={0}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        )}
        <button 
          type="submit" 
          className="search-button"
          disabled={loading || !query.trim()}
          aria-label="Search"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>
      
      <style jsx>{`
        .search-container {
          position: relative;
        }
        
        .search-container.focused {
          transform: translateY(-2px);
        }
        
        .search-icon {
          position: absolute;
          left: var(--space-4);
          top: 50%;
          transform: translateY(-50%);
          color: var(--color-text-light);
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          z-index: 2;
        }
        
        .search-input {
          padding-left: calc(var(--space-4) + 28px);
        }
        
        .clear-button {
          position: absolute;
          right: 140px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          color: var(--color-text-light);
          cursor: pointer;
          padding: var(--space-1);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all var(--transition-fast);
        }
        
        .clear-button:hover {
          background: rgba(0, 0, 0, 0.05);
          color: var(--color-text);
        }
        
        .spinner {
          width: 20px;
          height: 20px;
          border: 2px solid rgba(59, 130, 246, 0.3);
          border-radius: 50%;
          border-top-color: var(--color-primary);
          animation: spin 0.8s linear infinite;
        }
        
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        
        @media (max-width: 768px) {
          .clear-button {
            right: var(--space-4);
          }
          
          .search-button {
            margin-top: var(--space-3);
          }
        }
      `}</style>
    </form>
  );
};
