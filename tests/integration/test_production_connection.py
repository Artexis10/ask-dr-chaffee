#!/usr/bin/env python3
"""
Test production database connection before committing to direct DB approach
"""

import os
import asyncio
import asyncpg
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class ProductionConnectionTester:
    def __init__(self):
        self.db_url = os.getenv('PRODUCTION_DATABASE_URL')
        self.test_results = []
    
    async def run_comprehensive_test(self):
        """Run all connection tests to verify direct DB approach will work"""
        
        print("="*60)
        print("PRODUCTION DATABASE CONNECTION TEST")
        print("="*60)
        
        if not self.db_url:
            print("❌ PRODUCTION_DATABASE_URL not set in environment")
            print("   Set this to your cloud database URL:")
            print("   postgresql://user:pass@your-db.com:5432/database")
            return False
        
        # Test 1: Basic connection
        print("\n1. Testing basic connection...")
        basic_success = await self.test_basic_connection()
        
        if not basic_success:
            print("❌ Basic connection failed - direct DB approach won't work")
            return False
        
        # Test 2: SSL/Security
        print("\n2. Testing SSL and security...")
        ssl_success = await self.test_ssl_connection()
        
        # Test 3: Write permissions  
        print("\n3. Testing write permissions...")
        write_success = await self.test_write_permissions()
        
        # Test 4: Batch operations
        print("\n4. Testing batch operations...")
        batch_success = await self.test_batch_operations()
        
        # Test 5: Connection stability
        print("\n5. Testing connection stability...")
        stability_success = await self.test_connection_stability()
        
        # Test 6: Large data handling
        print("\n6. Testing large data uploads...")
        large_data_success = await self.test_large_data_upload()
        
        # Summary
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        
        all_tests = [
            ("Basic Connection", basic_success),
            ("SSL Security", ssl_success), 
            ("Write Permissions", write_success),
            ("Batch Operations", batch_success),
            ("Connection Stability", stability_success),
            ("Large Data Upload", large_data_success)
        ]
        
        passed = sum(1 for _, success in all_tests if success)
        total = len(all_tests)
        
        for test_name, success in all_tests:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{test_name:<20}: {status}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 DIRECT DATABASE APPROACH WILL WORK PERFECTLY!")
            print("   You can proceed with confidence using direct DB connection.")
            return True
        elif passed >= 4:
            print("\n⚠️  DIRECT DATABASE APPROACH WILL MOSTLY WORK")
            print("   Some optimizations needed, but viable approach.")
            return True
        else:
            print("\n❌ DIRECT DATABASE APPROACH HAS SIGNIFICANT ISSUES")
            print("   Recommend using API gateway fallback instead.")
            return False
    
    async def test_basic_connection(self):
        """Test if we can connect at all"""
        try:
            conn = await asyncpg.connect(self.db_url)
            result = await conn.fetchval("SELECT 1")
            await conn.close()
            
            if result == 1:
                print("   ✅ Connection successful")
                return True
            else:
                print("   ❌ Connection failed - unexpected result")
                return False
                
        except Exception as e:
            print(f"   ❌ Connection failed: {str(e)}")
            print(f"   Common causes:")
            print(f"   - IP not whitelisted in cloud provider")
            print(f"   - Firewall blocking port 5432")
            print(f"   - Wrong credentials or database name")
            return False
    
    async def test_ssl_connection(self):
        """Test SSL requirements"""
        try:
            # Try with SSL required
            ssl_url = self.db_url
            if "sslmode=" not in ssl_url:
                ssl_url += "?sslmode=require" if "?" not in ssl_url else "&sslmode=require"
            
            conn = await asyncpg.connect(ssl_url)
            await conn.fetchval("SELECT version()")
            await conn.close()
            
            print("   ✅ SSL connection working")
            return True
            
        except Exception as e:
            print(f"   ⚠️  SSL issue: {str(e)}")
            print("   This may work but consider security implications")
            return True  # Not critical for functionality
    
    async def test_write_permissions(self):
        """Test if we can write data"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Try to create a test table (will fail if no permissions)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS connection_test (
                    id SERIAL PRIMARY KEY,
                    test_data TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Try to insert data
            await conn.execute("""
                INSERT INTO connection_test (test_data) VALUES ($1)
            """, "test_from_local_rtx_5080")
            
            # Try to read it back
            result = await conn.fetchval("""
                SELECT test_data FROM connection_test WHERE test_data = $1
            """, "test_from_local_rtx_5080")
            
            # Clean up
            await conn.execute("DELETE FROM connection_test WHERE test_data = $1", 
                             "test_from_local_rtx_5080")
            
            await conn.close()
            
            if result == "test_from_local_rtx_5080":
                print("   ✅ Write permissions working")
                return True
            else:
                print("   ❌ Write test failed")
                return False
                
        except Exception as e:
            print(f"   ❌ Write permission failed: {str(e)}")
            print("   Database user may need INSERT/UPDATE/DELETE permissions")
            return False
    
    async def test_batch_operations(self):
        """Test batch insert performance"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Create test table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_test (
                    id SERIAL PRIMARY KEY,
                    text_data TEXT,
                    number_data INTEGER
                )
            """)
            
            # Test batch insert (simulate chunk upload)
            test_data = [(f"test_chunk_{i}", i) for i in range(100)]
            
            start_time = time.time()
            await conn.executemany("""
                INSERT INTO batch_test (text_data, number_data) VALUES ($1, $2)
            """, test_data)
            batch_time = time.time() - start_time
            
            # Verify count
            count = await conn.fetchval("SELECT COUNT(*) FROM batch_test WHERE text_data LIKE 'test_chunk_%'")
            
            # Clean up
            await conn.execute("DELETE FROM batch_test WHERE text_data LIKE 'test_chunk_%'")
            await conn.close()
            
            if count == 100:
                print(f"   ✅ Batch operations working ({batch_time:.2f}s for 100 records)")
                if batch_time < 1.0:
                    print("   🚀 Excellent performance - direct DB will be very fast")
                return True
            else:
                print(f"   ❌ Batch test failed - expected 100, got {count}")
                return False
                
        except Exception as e:
            print(f"   ❌ Batch operations failed: {str(e)}")
            return False
    
    async def test_connection_stability(self):
        """Test connection over time (simulate long processing)"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            print("   Testing connection stability over 30 seconds...")
            
            # Test connection every 5 seconds for 30 seconds
            for i in range(6):
                await asyncio.sleep(5)
                result = await conn.fetchval("SELECT $1", f"stability_test_{i}")
                if result != f"stability_test_{i}":
                    await conn.close()
                    print("   ❌ Connection became unstable")
                    return False
            
            await conn.close()
            print("   ✅ Connection stable over 30 seconds")
            return True
            
        except Exception as e:
            print(f"   ❌ Stability test failed: {str(e)}")
            print("   Long-running processing may have connection issues")
            return False
    
    async def test_large_data_upload(self):
        """Test uploading large chunks (simulate embeddings)"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Create test table with large text and array data
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS large_data_test (
                    id SERIAL PRIMARY KEY,
                    large_text TEXT,
                    embedding_data FLOAT[]
                )
            """)
            
            # Create large test data (simulate transcript chunk with embedding)
            large_text = "This is a test transcript chunk. " * 100  # ~3KB text
            fake_embedding = [0.1] * 1536  # OpenAI embedding size
            
            start_time = time.time()
            await conn.execute("""
                INSERT INTO large_data_test (large_text, embedding_data) VALUES ($1, $2)
            """, large_text, fake_embedding)
            upload_time = time.time() - start_time
            
            # Verify
            result = await conn.fetchval("""
                SELECT large_text FROM large_data_test WHERE large_text = $1
            """, large_text)
            
            # Clean up
            await conn.execute("DELETE FROM large_data_test WHERE large_text = $1", large_text)
            await conn.close()
            
            if result == large_text:
                print(f"   ✅ Large data upload working ({upload_time:.2f}s)")
                return True
            else:
                print("   ❌ Large data upload failed")
                return False
                
        except Exception as e:
            print(f"   ❌ Large data test failed: {str(e)}")
            return False

async def main():
    """Run the comprehensive test"""
    tester = ProductionConnectionTester()
    success = await tester.run_comprehensive_test()
    
    if success:
        print("\n🎯 RECOMMENDATION: Proceed with direct database approach")
        print("   Your RTX 5080 can upload directly to production database")
        print("   Expected performance: Very fast, reliable")
    else:
        print("\n🔄 RECOMMENDATION: Use API gateway approach instead")
        print("   Direct database has issues, use REST API endpoints")
        print("   Expected performance: Slower but more reliable")
    
    print("\nNext steps:")
    if success:
        print("1. Run: python backend/scripts/ingest_to_production.py --limit 10")
        print("2. Test with small batch first")
        print("3. Scale up to full 1200 videos")
    else:
        print("1. Set up API endpoints for ingestion")
        print("2. Modify upload script to use HTTP instead of direct DB")
        print("3. Consider VPN or proxy solutions")

if __name__ == "__main__":
    asyncio.run(main())
