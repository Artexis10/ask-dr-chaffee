// Frontend Integration Examples for RAG Search API
// Use these in your React/Vue/Angular frontend

// ==============================================
// BASIC SEARCH FUNCTION
// ==============================================

async function searchChaffeeContent(query) {
    try {
        const response = await fetch('http://localhost:5001/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ query: query })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        return result;
        
    } catch (error) {
        console.error('Search error:', error);
        throw error;
    }
}

// ==============================================
// REACT COMPONENT EXAMPLE
// ==============================================

import React, { useState, useCallback, useEffect } from 'react';
import { debounce } from 'lodash'; // npm install lodash

const ChaffeeSearch = () => {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Debounced search to avoid too many API calls
    const debouncedSearch = useCallback(
        debounce(async (searchQuery) => {
            if (searchQuery.length < 3) {
                setResults(null);
                return;
            }

            setLoading(true);
            setError(null);

            try {
                const result = await searchChaffeeContent(searchQuery);
                setResults(result);
            } catch (err) {
                setError('Search failed. Please try again.');
                console.error('Search error:', err);
            } finally {
                setLoading(false);
            }
        }, 500), // 500ms delay
        []
    );

    useEffect(() => {
        debouncedSearch(query);
    }, [query, debouncedSearch]);

    const handleQueryChange = (e) => {
        setQuery(e.target.value);
    };

    const openYouTubeLink = (source) => {
        window.open(source.url, '_blank');
    };

    return (
        <div className="chaffee-search">
            <div className="search-input">
                <input
                    type="text"
                    placeholder="Ask Dr. Chaffee about carnivore diet, autoimmune conditions, ketosis..."
                    value={query}
                    onChange={handleQueryChange}
                    className="search-field"
                />
                {loading && <div className="loading-spinner">Searching...</div>}
            </div>

            {error && (
                <div className="error-message">
                    {error}
                </div>
            )}

            {results && (
                <div className="search-results">
                    <div className="result-metadata">
                        <span className={`confidence confidence-${results.confidence}`}>
                            Confidence: {results.confidence}
                        </span>
                        <span className="cost">Cost: ${results.cost_usd?.toFixed(4)}</span>
                        <span className="time">{results.processing_time?.toFixed(2)}s</span>
                    </div>

                    <div className="answer">
                        <h3>Dr. Chaffee's Perspective:</h3>
                        <div className="answer-text">
                            {results.answer.split('\n').map((paragraph, index) => (
                                <p key={index}>{paragraph}</p>
                            ))}
                        </div>
                    </div>

                    <div className="sources">
                        <h4>Sources from Dr. Chaffee's Videos:</h4>
                        {results.sources.map((source, index) => (
                            <div key={index} className="source-item" onClick={() => openYouTubeLink(source)}>
                                <div className="source-title">{source.title}</div>
                                <div className="source-metadata">
                                    {source.timestamp && (
                                        <span className="timestamp">⏰ {source.timestamp}</span>
                                    )}
                                    <span className="similarity">
                                        Relevance: {(source.similarity * 100).toFixed(1)}%
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default ChaffeeSearch;

// ==============================================
// VUE.JS COMPONENT EXAMPLE
// ==============================================

/*
<template>
  <div class="chaffee-search">
    <div class="search-input">
      <input
        v-model="query"
        @input="handleSearch"
        type="text"
        placeholder="Ask Dr. Chaffee about health topics..."
        class="search-field"
      />
      <div v-if="loading" class="loading">Searching...</div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="results" class="results">
      <div class="confidence" :class="`confidence-${results.confidence}`">
        Confidence: {{ results.confidence }}
      </div>
      
      <div class="answer">
        <h3>Answer:</h3>
        <p v-for="(paragraph, index) in results.answer.split('\n')" :key="index">
          {{ paragraph }}
        </p>
      </div>

      <div class="sources">
        <h4>Video Sources:</h4>
        <div
          v-for="(source, index) in results.sources"
          :key="index"
          @click="openVideo(source)"
          class="source"
        >
          <div class="source-title">{{ source.title }}</div>
          <div class="source-time" v-if="source.timestamp">{{ source.timestamp }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { debounce } from 'lodash';

export default {
  name: 'ChaffeeSearch',
  data() {
    return {
      query: '',
      results: null,
      loading: false,
      error: null
    };
  },
  methods: {
    handleSearch: debounce(async function() {
      if (this.query.length < 3) {
        this.results = null;
        return;
      }

      this.loading = true;
      this.error = null;

      try {
        const response = await fetch('http://localhost:5001/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: this.query })
        });

        if (!response.ok) throw new Error('Search failed');
        
        this.results = await response.json();
      } catch (err) {
        this.error = 'Search failed. Please try again.';
      } finally {
        this.loading = false;
      }
    }, 500),

    openVideo(source) {
      window.open(source.url, '_blank');
    }
  }
};
</script>
*/

// ==============================================
// VANILLA JAVASCRIPT EXAMPLE
// ==============================================

class ChaffeeSearchWidget {
    constructor(containerElement) {
        this.container = containerElement;
        this.searchTimeout = null;
        this.init();
    }

    init() {
        this.container.innerHTML = `
            <div class="search-container">
                <input type="text" id="search-input" 
                       placeholder="Ask Dr. Chaffee about health topics...">
                <div id="search-results"></div>
            </div>
        `;

        const searchInput = this.container.querySelector('#search-input');
        searchInput.addEventListener('input', (e) => {
            this.handleSearch(e.target.value);
        });
    }

    handleSearch(query) {
        clearTimeout(this.searchTimeout);
        
        if (query.length < 3) {
            this.clearResults();
            return;
        }

        this.showLoading();

        this.searchTimeout = setTimeout(async () => {
            try {
                const results = await searchChaffeeContent(query);
                this.displayResults(results);
            } catch (error) {
                this.showError('Search failed. Please try again.');
            }
        }, 500);
    }

    showLoading() {
        const resultsDiv = this.container.querySelector('#search-results');
        resultsDiv.innerHTML = '<div class="loading">Searching Dr. Chaffee\'s content...</div>';
    }

    clearResults() {
        const resultsDiv = this.container.querySelector('#search-results');
        resultsDiv.innerHTML = '';
    }

    showError(message) {
        const resultsDiv = this.container.querySelector('#search-results');
        resultsDiv.innerHTML = `<div class="error">${message}</div>`;
    }

    displayResults(results) {
        const resultsDiv = this.container.querySelector('#search-results');
        
        const sourcesHTML = results.sources.map(source => `
            <div class="source" onclick="window.open('${source.url}', '_blank')">
                <div class="source-title">${source.title}</div>
                <div class="source-time">${source.timestamp || ''}</div>
            </div>
        `).join('');

        resultsDiv.innerHTML = `
            <div class="search-result">
                <div class="confidence confidence-${results.confidence}">
                    Confidence: ${results.confidence}
                </div>
                <div class="answer">
                    <h3>Dr. Chaffee's Answer:</h3>
                    <div class="answer-text">${results.answer.replace(/\n/g, '<br>')}</div>
                </div>
                <div class="sources">
                    <h4>Video Sources:</h4>
                    ${sourcesHTML}
                </div>
            </div>
        `;
    }
}

// Usage: new ChaffeeSearchWidget(document.getElementById('search-widget'));

// ==============================================
// CSS STYLES (OPTIONAL)
// ==============================================

const searchStyles = `
.chaffee-search {
    max-width: 800px;
    margin: 0 auto;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.search-field {
    width: 100%;
    padding: 12px 16px;
    font-size: 16px;
    border: 2px solid #e1e5e9;
    border-radius: 8px;
    margin-bottom: 16px;
}

.search-field:focus {
    outline: none;
    border-color: #0066cc;
}

.confidence {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    margin-bottom: 16px;
    display: inline-block;
}

.confidence-high { background: #d4edda; color: #155724; }
.confidence-medium { background: #fff3cd; color: #856404; }
.confidence-low { background: #f8d7da; color: #721c24; }

.answer {
    background: #f8f9fa;
    padding: 16px;
    border-radius: 8px;
    margin-bottom: 16px;
}

.answer h3 {
    margin-top: 0;
    color: #2c3e50;
}

.source-item {
    border: 1px solid #e1e5e9;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
    cursor: pointer;
    transition: background-color 0.2s;
}

.source-item:hover {
    background-color: #f8f9fa;
}

.source-title {
    font-weight: 600;
    margin-bottom: 4px;
    color: #0066cc;
}

.source-metadata {
    font-size: 12px;
    color: #666;
}

.loading {
    text-align: center;
    padding: 20px;
    color: #666;
}

.error {
    background: #f8d7da;
    color: #721c24;
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 16px;
}
`;

// Inject styles
const styleSheet = document.createElement('style');
styleSheet.textContent = searchStyles;
document.head.appendChild(styleSheet);
