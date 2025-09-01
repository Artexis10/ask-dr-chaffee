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
          placeholder="Search Dr. Chaffee's knowledge..."
          value={query}
          onChange={handleInputChange}
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
