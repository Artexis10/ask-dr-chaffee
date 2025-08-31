import React from 'react';

interface SearchBarProps {
  query: string;
  setQuery: (query: string) => void;
  handleSearch: (e: React.FormEvent) => void;
  loading: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ query, setQuery, handleSearch, loading }) => {
  return (
    <form onSubmit={handleSearch} className="search-form">
      <div className="search-container">
        <input
          type="text"
          className="search-input"
          placeholder="Search Dr. Chaffee's knowledge..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search query"
        />
        <button 
          type="submit" 
          className="search-button"
          disabled={loading}
          aria-label="Search"
        >
          {loading ? '🔄' : '🔍'} {loading ? 'Searching...' : 'Search'}
        </button>
      </div>
    </form>
  );
};
