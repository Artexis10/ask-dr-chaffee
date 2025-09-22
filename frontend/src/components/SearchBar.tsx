import React from 'react';

interface SearchBarProps {
  query: string;
  setQuery: (query: string) => void;
  handleSearch: (e: React.FormEvent) => void;
  loading: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ query, setQuery, handleSearch, loading }) => {
  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    console.log('SearchBar onSubmit called with query:', query);
    handleSearch(e);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    console.log('Input change:', value);
    setQuery(value);
  };

  React.useEffect(() => {
    console.log('SearchBar query state updated:', query);
  }, [query]);

  return (
    <form onSubmit={onSubmit} className="search-form">
      <div className="search-container">
        <input
          type="text"
          className="search-input"
          placeholder="Ask Dr. Chaffee about carnivore diet, autoimmune conditions, ketosis... (Press Enter or click Search)"
          value={query}
          onChange={handleInputChange}
          aria-label="Search query"
          disabled={loading}
        />
        <button 
          type="submit" 
          className="search-button"
          disabled={loading || !query.trim()}
          aria-label="Search"
          style={{ 
            opacity: loading || !query.trim() ? 0.6 : 1,
            cursor: loading || !query.trim() ? 'not-allowed' : 'pointer'
          }}
        >
          {loading ? '🔄 Searching...' : '🔍 Search Medical Knowledge'}
        </button>
      </div>
    </form>
  );
};
