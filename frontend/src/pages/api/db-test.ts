import { NextApiRequest, NextApiResponse } from 'next';
import { Pool } from 'pg';

// Database connection
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  // Disable SSL for local development
  ssl: false
});

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  try {
    // Simple query to test database connection
    const result = await pool.query('SELECT 1 as test');
    
    res.status(200).json({ 
      success: true, 
      message: 'Database connection successful',
      data: result.rows[0]
    });
  } catch (error) {
    console.error('Database connection error:', error);
    
    res.status(500).json({ 
      success: false, 
      message: 'Database connection failed',
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
}
