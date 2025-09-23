// Simple analytics utility for tracking user interactions

export interface AnalyticsEvent {
  eventName: string;
  properties?: Record<string, any>;
  timestamp?: number;
}

class Analytics {
  private static instance: Analytics;
  private initialized: boolean = false;
  private queue: AnalyticsEvent[] = [];
  private sessionId: string;
  private debugMode: boolean = false;

  private constructor() {
    this.sessionId = this.generateSessionId();
  }

  public static getInstance(): Analytics {
    if (!Analytics.instance) {
      Analytics.instance = new Analytics();
    }
    return Analytics.instance;
  }

  public init(options: { debug?: boolean } = {}): void {
    if (this.initialized) return;
    
    this.debugMode = options.debug || false;
    this.initialized = true;
    
    // Process any events that were tracked before initialization
    this.processQueue();
    
    // Set up event listeners for page visibility changes
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
          this.track('page_exit');
        } else if (document.visibilityState === 'visible') {
          this.track('page_return');
        }
      });
    }
    
    // Track page view on init
    this.track('page_view', {
      url: typeof window !== 'undefined' ? window.location.href : '',
      referrer: typeof document !== 'undefined' ? document.referrer : '',
    });
    
    this.log('Analytics initialized');
  }

  public track(eventName: string, properties: Record<string, any> = {}): void {
    const event: AnalyticsEvent = {
      eventName,
      properties: {
        ...properties,
        sessionId: this.sessionId,
        url: typeof window !== 'undefined' ? window.location.href : '',
      },
      timestamp: Date.now(),
    };
    
    this.queue.push(event);
    
    if (this.initialized) {
      this.processQueue();
    }
  }
  
  private processQueue(): void {
    if (!this.queue.length) return;
    
    const events = [...this.queue];
    this.queue = [];
    
    // In a real implementation, you would send these events to your analytics service
    // For now, we'll just log them if debug mode is enabled
    events.forEach(event => {
      this.log('Event tracked:', event);
      
      // In a production app, you would send this to your analytics endpoint
      // Example:
      // fetch('/api/analytics', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify(event),
      // }).catch(err => console.error('Failed to send analytics event:', err));
      
      // Dispatch a custom event that can be listened to
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('analytics_event', { 
          detail: event 
        }));
      }
    });
  }
  
  private generateSessionId(): string {
    // Generate a random session ID
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
  
  private log(...args: any[]): void {
    if (this.debugMode) {
      console.log('[Analytics]', ...args);
    }
  }
}

// Export a singleton instance
export const analytics = Analytics.getInstance();

// Helper hooks and utilities for React components
export const trackEvent = (eventName: string, properties: Record<string, any> = {}): void => {
  analytics.track(eventName, properties);
};

export const setupAnalyticsListeners = (): void => {
  if (typeof window === 'undefined') return;
  
  // Track search events
  document.addEventListener('submit', (event) => {
    const target = event.target as HTMLFormElement;
    if (target.classList.contains('search-form')) {
      const searchInput = target.querySelector('input[type="text"]') as HTMLInputElement;
      if (searchInput) {
        trackEvent('search', { query: searchInput.value });
      }
    }
  });
  
  // Track clicks on result links
  document.addEventListener('click', (event) => {
    const target = event.target as HTMLElement;
    const resultLink = target.closest('.watch-link') as HTMLAnchorElement;
    
    if (resultLink) {
      trackEvent('result_click', { 
        url: resultLink.href,
        type: 'youtube'
      });
    }
  });
};
