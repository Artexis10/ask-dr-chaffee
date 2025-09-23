import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="footer">
      <div className="footer-content">
        <div className="footer-top">
          <div className="footer-logo">
            <div className="footer-logo-icon">AC</div>
            <div className="footer-logo-text">
              <h3>Ask Dr. Chaffee</h3>
              <p>Medical Knowledge Base</p>
            </div>
          </div>
          
          <div className="footer-links-container">
            <div className="footer-links-column">
              <h4>Social Media</h4>
              <div className="footer-links">
                <a 
                  href="https://www.youtube.com/@anthonychaffeemd" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M14 12L10.5 14.5V9.5L14 12Z" fill="currentColor" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M2 12.7075V11.2924C2 8.39705 2 6.94939 2.90549 5.87546C3.8111 4.80153 5.23968 4.61082 8.09684 4.22939C9.45792 4.05962 10.8432 4 12 4C13.1568 4 14.5421 4.05962 15.9032 4.22939C18.7603 4.61082 20.1889 4.80153 21.0945 5.87546C22 6.94939 22 8.39705 22 11.2924V12.7075C22 15.6028 22 17.0505 21.0945 18.1244C20.1889 19.1984 18.7603 19.3891 15.9032 19.7705C14.5421 19.9403 13.1568 19.9999 12 19.9999C10.8432 19.9999 9.45792 19.9403 8.09684 19.7705C5.23968 19.3891 3.8111 19.1984 2.90549 18.1244C2 17.0505 2 15.6028 2 12.7075Z" stroke="currentColor" strokeWidth="1.5"/>
                  </svg>
                  YouTube
                </a>
                <a 
                  href="https://www.instagram.com/anthonychaffeemd/" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 16C14.2091 16 16 14.2091 16 12C16 9.79086 14.2091 8 12 8C9.79086 8 8 9.79086 8 12C8 14.2091 9.79086 16 12 16Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M3 16V8C3 5.23858 5.23858 3 8 3H16C18.7614 3 21 5.23858 21 8V16C21 18.7614 18.7614 21 16 21H8C5.23858 21 3 18.7614 3 16Z" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M17.5 6.51L17.51 6.49889" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Instagram
                </a>
                <a 
                  href="https://www.linkedin.com/in/anthony-chaffee-md-25786843/" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 11V16M8 8V8.01M12 16V11M16 16V13C16 11.9391 15.5786 11.0217 14.8284 10.3716C14.0783 9.72143 13.0609 9.5 12 9.5C10.9391 9.5 9.92172 9.72143 9.17157 10.3716C8.42143 11.0217 8 11.9391 8 13M21 8V16C21 17.1046 20.1046 18 19 18H5C3.89543 18 3 17.1046 3 16V8C3 6.89543 3.89543 6 5 6H19C20.1046 6 21 6.89543 21 8Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  LinkedIn
                </a>
                <a 
                  href="https://x.com/anthony_chaffee" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M22 4.01C21.9992 4.17826 21.9397 4.33978 21.8314 4.47354C21.7231 4.6073 21.5721 4.70396 21.4 4.75C20.4 5.1 19.9 5.35 19.5 6.25C19.192 6.86 18.3312 8.66357 18 9.75L17.5 11.25C17.3687 11.5638 17.2373 11.8587 17.1 12.25C16.9216 12.7483 16.7332 13.2483 16.55 13.75C16.4326 14.0347 16.3245 14.3231 16.2 14.75C16.1009 15.0842 16.0465 15.4295 16.0465 15.7772C16.0465 16.1249 16.1009 16.4702 16.2 16.8042C16.3 17.1382 16.5 17.5 16.8 17.75C17.1 18 17.5 18 17.8 18C18.2 18 18.5 17.8 18.8 17.6C19.1 17.4 19.3 17.2 19.6 17C19.9 16.8 20.2 16.6 20.5 16.5C20.8 16.4 21.1 16.3 21.4 16.3C21.7 16.3 22 16.4 22.2 16.6C22.4 16.8 22.5 17 22.5 17.3C22.5 17.6 22.3 17.8 22.1 18C21.9 18.2 21.7 18.3 21.4 18.5C21.1 18.7 20.9 18.8 20.6 19C20.3 19.2 20 19.4 19.7 19.6C19.4 19.8 19.1 20 18.8 20.2C18.5 20.4 18.2 20.5 17.9 20.7C17.6 20.9 17.3 21 17 21C16.7 21 16.4 21 16.1 20.9C15.8 20.8 15.6 20.6 15.4 20.4C15.2 20.2 15 20 14.9 19.7C14.8 19.4 14.7 19.1 14.6 18.8C14.5 18.5 14.4 18.2 14.3 17.9C14.2 17.6 14.1 17.3 13.9 17.1C13.7 16.9 13.5 16.7 13.3 16.5C13.1 16.3 12.9 16.1 12.6 15.9C12.3 15.7 12 15.5 11.7 15.3C11.4 15.1 11 15 10.6 14.9C10.2 14.8 9.8 14.7 9.4 14.7C9 14.7 8.6 14.7 8.2 14.7C7.8 14.7 7.4 14.7 7 14.7C6.6 14.7 6.2 14.7 5.9 14.6C5.6 14.5 5.3 14.4 5 14.2C4.7 14 4.5 13.8 4.3 13.5C4.1 13.2 4 12.9 4 12.5C4 12.1 4.1 11.8 4.2 11.5C4.3 11.2 4.5 11 4.7 10.8C4.9 10.6 5.1 10.4 5.4 10.2C5.7 10 5.9 9.9 6.2 9.7C6.5 9.5 6.8 9.4 7.1 9.2C7.4 9 7.6 8.9 7.9 8.7C8.2 8.5 8.4 8.3 8.6 8.1C8.8 7.9 9 7.7 9.1 7.4C9.2 7.1 9.3 6.9 9.3 6.6C9.3 6.3 9.2 6 9 5.8C8.8 5.6 8.5 5.5 8.2 5.5C7.9 5.5 7.6 5.6 7.4 5.8C7.2 6 7 6.2 6.8 6.5C6.6 6.8 6.5 7 6.3 7.3C6.1 7.6 5.9 7.9 5.7 8.1C5.5 8.3 5.3 8.5 5 8.6C4.7 8.7 4.4 8.8 4.1 8.8C3.8 8.8 3.5 8.7 3.3 8.5C3.1 8.3 3 8 3 7.7C3 7.4 3.1 7.1 3.2 6.8C3.3 6.5 3.5 6.3 3.7 6C3.9 5.7 4.1 5.5 4.4 5.2C4.7 4.9 4.9 4.7 5.2 4.5C5.5 4.3 5.8 4.1 6.1 3.9C6.4 3.7 6.7 3.5 7 3.4C7.3 3.3 7.6 3.2 7.9 3.1C8.2 3 8.5 3 8.8 3C9.1 3 9.5 3 9.8 3.1C10.1 3.2 10.5 3.2 10.8 3.3C11.1 3.4 11.5 3.5 11.8 3.7C12.1 3.9 12.5 4 12.8 4.2C13.1 4.4 13.4 4.6 13.7 4.8C14 5 14.3 5.2 14.5 5.4C14.7 5.6 15 5.8 15.2 6C15.4 6.2 15.7 6.4 15.9 6.5C16.1 6.6 16.4 6.8 16.6 6.9C16.8 7 17.1 7.1 17.3 7.2C17.5 7.3 17.8 7.4 18 7.5C18.2 7.6 18.5 7.6 18.7 7.7C18.9 7.8 19.2 7.8 19.4 7.8C19.6 7.8 19.9 7.8 20.1 7.8C20.3 7.8 20.6 7.7 20.8 7.6C21 7.5 21.2 7.4 21.4 7.2C21.6 7 21.7 6.8 21.8 6.6C21.9 6.4 22 6.1 22 5.8C22 5.5 22 5.2 22 5C22 4.8 22 4.6 22 4.4C22 4.2 22 4.01 22 4.01Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  X (Twitter)
                </a>
              </div>
            </div>
            
            <div className="footer-links-column">
              <h4>Support</h4>
              <div className="footer-links">
                <a 
                  href="https://www.patreon.com/AnthonyChaffeeMD" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M19 14C21.2091 14 23 12.2091 23 10C23 7.79086 21.2091 6 19 6C16.7909 6 15 7.79086 15 10C15 12.2091 16.7909 14 19 14Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M15 13.5V21H3.5C3.22386 21 3 20.7761 3 20.5V5.5C3 5.22386 3.22386 5 3.5 5H15V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Support on Patreon
                </a>
                <a 
                  href="https://www.youtube.com/@anthonychaffeemd/join" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 12.5C13.6569 12.5 15 11.1569 15 9.5C15 7.84315 13.6569 6.5 12 6.5C10.3431 6.5 9 7.84315 9 9.5C9 11.1569 10.3431 12.5 12 12.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M19.5 19.5L16.5 16.5M12 21.5C7.02944 21.5 3 17.4706 3 12.5C3 7.52944 7.02944 3.5 12 3.5C16.9706 3.5 21 7.52944 21 12.5C21 14.5631 20.3375 16.4757 19.2236 18.0186" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  YouTube Membership
                </a>
                <div className="footer-text-info">
                  Dr. Chaffee is a board-certified neurosurgeon and advocate for the carnivore diet and ancestral health.
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div className="footer-divider"></div>
        
        <div className="footer-bottom">
          <p className="disclaimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 16V12M12 8H12.01M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <span>
              <strong>Educational Content Only:</strong> This content is for educational purposes only and should not be considered medical advice. Always consult with a healthcare professional.
            </span>
          </p>
          <p className="copyright">&copy; {new Date().getFullYear()} Ask Dr. Chaffee</p>
        </div>
      </div>
      
      <style jsx>{`
        .footer-top {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          flex-wrap: wrap;
          gap: var(--space-6);
          margin-bottom: var(--space-6);
        }
        
        .footer-logo {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }
        
        .footer-logo-icon {
          width: 50px;
          height: 50px;
          background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
          color: white;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.2rem;
          font-weight: 700;
        }
        
        .footer-logo-text h3 {
          margin: 0;
          font-size: 1.2rem;
          font-weight: 700;
          color: var(--color-text);
        }
        
        .footer-logo-text p {
          margin: 0;
          font-size: 0.9rem;
          color: var(--color-text-light);
        }
        
        .footer-links-container {
          display: flex;
          gap: var(--space-8);
          flex-wrap: wrap;
        }
        
        .footer-links-column h4 {
          margin: 0 0 var(--space-3) 0;
          font-size: 1rem;
          font-weight: 600;
          color: var(--color-text);
        }
        
        .footer-links {
          display: flex;
          flex-direction: column;
          gap: var(--space-2);
        }
        
        .footer-link {
          display: flex;
          align-items: center;
          gap: var(--space-2);
          color: var(--color-text-light);
          text-decoration: none;
          font-size: 0.9rem;
          transition: all var(--transition-normal);
        }
        
        .footer-link:hover {
          color: var(--color-primary);
          transform: translateX(2px);
        }
        
        .footer-text-info {
          font-size: 0.85rem;
          color: var(--color-text-light);
          margin-top: var(--space-3);
          line-height: 1.5;
          max-width: 220px;
          padding: var(--space-2);
          background: rgba(59, 130, 246, 0.05);
          border-radius: var(--radius-md);
        }
        
        .footer-divider {
          height: 1px;
          background: var(--color-border);
          margin: var(--space-4) 0;
        }
        
        .footer-bottom {
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: var(--space-4);
        }
        
        .disclaimer {
          display: flex;
          align-items: flex-start;
          gap: var(--space-2);
          color: var(--color-text-light);
          font-size: 0.9rem;
          margin: 0;
          max-width: 700px;
        }
        
        .disclaimer svg {
          flex-shrink: 0;
          margin-top: 3px;
          color: var(--color-warning);
        }
        
        .disclaimer strong {
          color: var(--color-text);
        }
        
        .copyright {
          color: var(--color-text-light);
          font-size: 0.9rem;
          margin: 0;
        }
        
        @media (max-width: 768px) {
          .footer-top {
            flex-direction: column;
            align-items: center;
            text-align: center;
          }
          
          .footer-links-container {
            width: 100%;
            justify-content: space-around;
          }
          
          .footer-bottom {
            flex-direction: column;
            text-align: center;
          }
          
          .disclaimer {
            margin-bottom: var(--space-3);
          }
        }
      `}</style>
    </footer>
  );
};
