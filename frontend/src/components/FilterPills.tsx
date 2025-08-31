import React from 'react';

interface FilterPillsProps {
  sourceFilter: 'all' | 'youtube' | 'zoom';
  setSourceFilter: React.Dispatch<React.SetStateAction<'all' | 'youtube' | 'zoom'>>;
  yearFilter: string;
  setYearFilter: (filter: string) => void;
  availableYears: string[];
}

export const FilterPills: React.FC<FilterPillsProps> = ({ 
  sourceFilter, 
  setSourceFilter, 
  yearFilter, 
  setYearFilter,
  availableYears
}) => {
  return (
    <div className="filter-container">
      <div className="filter-group">
        <span className="filter-label">Source:</span>
        <div className="filter-pills">
          <button
            className={`filter-pill ${sourceFilter === 'all' ? 'active' : ''}`}
            onClick={() => setSourceFilter('all')}
            aria-pressed={sourceFilter === 'all'}
            aria-label="Filter by all sources"
          >
            🔍 All
          </button>
          <button
            className={`filter-pill ${sourceFilter === 'youtube' ? 'active' : ''}`}
            onClick={() => setSourceFilter('youtube')}
            aria-pressed={sourceFilter === 'youtube'}
            aria-label="Filter by YouTube only"
          >
            📺 YouTube
          </button>
          <button
            className={`filter-pill ${sourceFilter === 'zoom' ? 'active' : ''}`}
            onClick={() => setSourceFilter('zoom')}
            aria-pressed={sourceFilter === 'zoom'}
            aria-label="Filter by Zoom only"
          >
            💼 Zoom
          </button>
        </div>
      </div>
      
      {availableYears.length > 0 && (
        <div className="filter-group">
          <span className="filter-label">Year:</span>
          <select
            className="year-filter"
            value={yearFilter}
            onChange={(e) => setYearFilter(e.target.value)}
            aria-label="Filter by year"
          >
            <option value="all">All Years</option>
            {availableYears.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
};
