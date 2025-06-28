#!/usr/bin/env python3
"""
Convenient script to run database population with sensible defaults.
"""

import sys
import os
from batch_populate import BatchPopulator


def main():
    """Run database population with user-friendly options"""
    
    print("🏛️  US Cities Database Population Tool")
    print("=====================================")
    
    # Check if we're running a test
    if "--test" in sys.argv:
        print("🧪 Running test population (5 cities only)")
        populator = BatchPopulator()
        test_cities = populator.get_priority_cities()[:5]
        populator.populate_batch_sequential(test_cities, discover_vendors=True)
        return
    
    # Check database file
    db_path = "/root/engagic/app/meetings.db"
    if not os.path.exists(os.path.dirname(db_path)):
        print(f"⚠️  Database directory doesn't exist: {os.path.dirname(db_path)}")
        print("   Creating directory...")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    print(f"📊 Database location: {db_path}")
    
    # Ask user for options
    print("\nOptions:")
    print("1. Quick start (priority cities only, no vendor discovery)")
    print("2. Full population (all cities, with vendor discovery)")
    print("3. Test run (5 cities only)")
    print("4. Priority cities with vendor discovery")
    
    choice = input("\nSelect option (1-4): ").strip()
    
    populator = BatchPopulator()
    
    if choice == "1":
        print("\n🚀 Quick start: Populating priority cities without vendor discovery")
        priority_cities = populator.get_priority_cities()
        populator.populate_batch_sequential(priority_cities, discover_vendors=False)
        
    elif choice == "2":
        print("\n🌍 Full population: This will take several hours...")
        confirm = input("Continue? (y/N): ").strip().lower()
        if confirm == 'y':
            populator.run_full_population(
                min_population=1000,
                parallel=False,
                discover_vendors=True,
                priority_first=True
            )
        else:
            print("Cancelled.")
            return
            
    elif choice == "3":
        print("\n🧪 Test run: 5 cities only")
        test_cities = populator.get_priority_cities()[:5]
        populator.populate_batch_sequential(test_cities, discover_vendors=True)
        
    elif choice == "4":
        print("\n⭐ Priority cities with vendor discovery")
        priority_cities = populator.get_priority_cities()
        populator.populate_batch_sequential(priority_cities, discover_vendors=True)
        
    else:
        print("Invalid choice. Exiting.")
        return
    
    # Show final stats
    stats = populator.get_stats()
    print(f"\n✅ Population complete!")
    print(f"   Processed: {stats['total_processed']}")
    print(f"   Successful: {stats['successful_stores']}")
    print(f"   Vendors found: {stats['vendor_discoveries']}")
    
    if stats['successful_stores'] > 0:
        print(f"\n🎉 {stats['successful_stores']} cities are now in your database!")
        print("   You can now restart your API server to use the pre-populated data.")


if __name__ == "__main__":
    main()