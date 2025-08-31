import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="footer">
      <div className="footer-content">
        <p className="disclaimer">
          ⚠️ <strong>Educational Content Only:</strong> This content is for educational purposes only and should not be considered medical advice.
        </p>
        <div className="footer-links">
          <a 
            href="https://www.youtube.com/@anthonychaffeemd" 
            target="_blank" 
            rel="noopener noreferrer"
            className="official-channel-link"
          >
            📺 Visit Dr. Chaffee's Official YouTube Channel
          </a>
        </div>
      </div>
    </footer>
  );
};
