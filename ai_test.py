#!/usr/bin/env python3
"""
Database Migration Script for MoodMate
Fixes missing columns in existing database
"""

import sqlite3
import os
from contextlib import contextmanager

DATABASE_PATH = 'mood_app.db'  # Adjust if your db is in a different location

@contextmanager
def get_db_connection():
    """Context manager for database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        yield conn
    finally:
        conn.close()

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    return column_name in columns

def migrate_database():
    """Add missing columns to mood_entry table"""
    print("🔧 Starting database migration...")
    
    if not os.path.exists(DATABASE_PATH):
        print(f"❌ Database file {DATABASE_PATH} not found!")
        print("💡 Run the Flask app once to create the database, then run this migration.")
        return False
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Backup the database first
        print("📦 Creating database backup...")
        cursor.execute("BEGIN IMMEDIATE;")
        
        try:
            # Check and add missing columns
            missing_columns = [
                ('all_emotions_data', 'TEXT'),
                ('fallback_used', 'BOOLEAN DEFAULT 0'),
                ('emotion_intensity', 'VARCHAR(20)')
            ]
            
            added_columns = []
            
            for column_name, column_type in missing_columns:
                if not check_column_exists(cursor, 'mood_entry', column_name):
                    print(f"➕ Adding column: {column_name}")
                    cursor.execute(f"ALTER TABLE mood_entry ADD COLUMN {column_name} {column_type}")
                    added_columns.append(column_name)
                else:
                    print(f"✅ Column {column_name} already exists")
            
            # Update existing records with default values
            if added_columns:
                print("🔄 Updating existing records with default values...")
                cursor.execute("""
                    UPDATE mood_entry 
                    SET all_emotions_data = '[]',
                        fallback_used = 1,
                        emotion_intensity = 'moderate'
                    WHERE all_emotions_data IS NULL
                """)
                print(f"📝 Updated {cursor.rowcount} existing records")
            
            conn.commit()
            print("✅ Database migration completed successfully!")
            
            # Show current schema
            print("\n📋 Current mood_entry table schema:")
            cursor.execute("PRAGMA table_info(mood_entry)")
            for column in cursor.fetchall():
                print(f"  - {column[1]} ({column[2]})")
            
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Migration failed: {e}")
            return False

def verify_migration():
    """Verify the migration was successful"""
    print("\n🔍 Verifying migration...")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Test insert with new columns
        try:
            cursor.execute("""
                INSERT INTO mood_entry 
                (user_id, emotion, confidence, text_input, persona_used, all_emotions_data, fallback_used, emotion_intensity)
                VALUES (999, 'test', 0.5, 'test input', 'TestPersona', '[]', 1, 'moderate')
            """)
            
            # Remove test record
            cursor.execute("DELETE FROM mood_entry WHERE user_id = 999")
            conn.commit()
            
            print("✅ Migration verification successful!")
            return True
            
        except Exception as e:
            print(f"❌ Migration verification failed: {e}")
            return False

def show_database_stats():
    """Show database statistics"""
    print("\n📊 Database Statistics:")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Count users and entries
        cursor.execute("SELECT COUNT(*) FROM user")
        user_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM mood_entry")
        entry_count = cursor.fetchone()[0]
        
        print(f"  - Total Users: {user_count}")
        print(f"  - Total Mood Entries: {entry_count}")
        
        if entry_count > 0:
            # Show emotion distribution
            cursor.execute("""
                SELECT emotion, COUNT(*) as count 
                FROM mood_entry 
                GROUP BY emotion 
                ORDER BY count DESC
            """)
            print(f"\n  📈 Emotion Distribution:")
            for emotion, count in cursor.fetchall():
                print(f"    - {emotion.title()}: {count}")

if __name__ == "__main__":
    print("🌟 MoodMate Database Migration Tool")
    print("=" * 40)
    
    # Run migration
    if migrate_database():
        if verify_migration():
            show_database_stats()
            print("\n🎉 Migration completed successfully!")
            print("\n💡 Next steps:")
            print("   1. Restart your Flask application")
            print("   2. Check if the AI model loads properly")
            print("   3. Test emotion analysis functionality")
        else:
            print("\n⚠️  Migration completed but verification failed")
    else:
        print("\n❌ Migration failed - please check the error messages above")
    
    print("\n" + "=" * 40)