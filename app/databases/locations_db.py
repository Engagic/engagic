import sqlite3
import logging
from typing import Optional, List, Dict, Any
from .base_db import BaseDatabase
from uszipcode import SearchEngine

logger = logging.getLogger("engagic")

class LocationsDatabase(BaseDatabase):
    """Database for cities, states, and zipcode mappings"""
    
    def __init__(self, db_path: str):
        self.zipcode_search = SearchEngine()
        super().__init__(db_path)
    
    def _init_database(self):
        """Initialize the locations database schema"""
        schema = """
        -- Cities table - master city registry
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_name TEXT NOT NULL,
            state TEXT NOT NULL,
            city_slug TEXT NOT NULL UNIQUE,
            vendor TEXT,
            county TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(city_name, state, city_slug)
        );

        -- Zipcodes table - zipcode to city mapping
        CREATE TABLE IF NOT EXISTS zipcodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zipcode TEXT NOT NULL,
            city_id INTEGER NOT NULL,
            is_primary BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (city_id) REFERENCES cities(id) ON DELETE CASCADE,
            UNIQUE(zipcode, city_id)
        );

        -- Create indices for performance
        CREATE INDEX IF NOT EXISTS idx_cities_slug ON cities(city_slug);
        CREATE INDEX IF NOT EXISTS idx_cities_name_state ON cities(city_name, state);
        CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode);
        CREATE INDEX IF NOT EXISTS idx_zipcodes_city_id ON zipcodes(city_id);
        """
        self.execute_script(schema)
    
    def add_city(self, city_name: str, state: str, city_slug: str, vendor: str, 
                 county: str = None, zipcodes: List[str] = None) -> int:
        """Add a new city with optional zipcodes"""
        logger.info(f"Adding city: {city_name}, {state} with vendor {vendor}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert city
            cursor.execute("""
                INSERT INTO cities (city_name, state, city_slug, vendor, county)
                VALUES (?, ?, ?, ?, ?)
            """, (city_name, state, city_slug, vendor, county))
            
            city_id = cursor.lastrowid
            
            # Add zipcodes if provided
            if zipcodes:
                for i, zipcode in enumerate(zipcodes):
                    is_primary = i == 0  # First zipcode is primary
                    cursor.execute("""
                        INSERT OR IGNORE INTO zipcodes (zipcode, city_id, is_primary)
                        VALUES (?, ?, ?)
                    """, (zipcode, city_id, is_primary))
            
            conn.commit()
            logger.info(f"Successfully added city {city_name} with ID {city_id}")
            return city_id
    
    def get_city_by_zipcode(self, zipcode: str) -> Optional[Dict[str, Any]]:
        """Get city information by zipcode"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, z.zipcode, z.is_primary
                FROM cities c
                JOIN zipcodes z ON c.id = z.city_id
                WHERE z.zipcode = ?
            """, (zipcode,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_city_by_name(self, city_name: str, state: str) -> Optional[Dict[str, Any]]:
        """Get city information by name and state (case-insensitive with space normalization)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Normalize inputs: case-insensitive and handle spaces
            city_normalized = city_name.strip().replace(' ', '').lower()
            state_normalized = state.strip().upper()
            
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                WHERE LOWER(REPLACE(c.city_name, ' ', '')) = ? AND UPPER(c.state) = ?
                GROUP BY c.id
                ORDER BY c.id
                LIMIT 1
            """, (city_normalized, state_normalized))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                return result
            return None
    
    def get_cities_by_name_only(self, city_name: str) -> List[Dict[str, Any]]:
        """Get all cities matching a name (regardless of state) for ambiguous searches"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Normalize input: case-insensitive and handle spaces
            city_normalized = city_name.strip().replace(' ', '').lower()
            
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                WHERE LOWER(REPLACE(c.city_name, ' ', '')) = ?
                GROUP BY c.id
                ORDER BY c.state, c.city_name
            """, (city_normalized,))
            
            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                results.append(result)
            return results
    
    def get_city_by_slug(self, city_slug: str) -> Optional[Dict[str, Any]]:
        """Get city information by slug"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                WHERE c.city_slug = ?
                GROUP BY c.id
            """, (city_slug,))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                return result
            return None
    
    def get_all_cities(self) -> List[Dict[str, Any]]:
        """Get all cities with their zipcode information"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, 
                       GROUP_CONCAT(z.zipcode) as zipcodes,
                       (SELECT z2.zipcode FROM zipcodes z2 WHERE z2.city_id = c.id AND z2.is_primary = 1) as primary_zipcode
                FROM cities c
                LEFT JOIN zipcodes z ON c.id = z.city_id
                GROUP BY c.id
                ORDER BY c.city_name, c.state
            """)
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result['zipcodes']:
                    result['zipcodes'] = result['zipcodes'].split(',')
                results.append(result)
            return results
    
    def delete_city(self, city_slug: str) -> bool:
        """Delete a city and all associated data"""
        logger.info(f"Deleting city: {city_slug}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get city_id first
            cursor.execute("SELECT id FROM cities WHERE city_slug = ?", (city_slug,))
            city_row = cursor.fetchone()
            if not city_row:
                logger.warning(f"City not found for deletion: {city_slug}")
                return False
            
            city_id = city_row['id']
            
            # Delete city (zipcodes will be deleted due to foreign key cascade)
            cursor.execute("DELETE FROM cities WHERE id = ?", (city_id,))
            
            conn.commit()
            logger.info(f"Successfully deleted city {city_slug}")
            return True
    
    def delete_cities_without_vendor(self) -> int:
        """Delete all cities that don't have an associated vendor"""
        logger.info("Deleting cities without vendor")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get count first
            cursor.execute("""
                SELECT COUNT(*) as count FROM cities 
                WHERE vendor IS NULL OR vendor = ''
            """)
            count = cursor.fetchone()['count']
            
            if count == 0:
                logger.info("No cities without vendor found")
                return 0
            
            # Delete cities without vendor (cascades to zipcodes)
            cursor.execute("""
                DELETE FROM cities 
                WHERE vendor IS NULL OR vendor = ''
            """)
            
            conn.commit()
            logger.info(f"Successfully deleted {count} cities without vendor")
            return count
    
    def update_city(self, city_id: int, vendor: str = None, city_slug: str = None) -> bool:
        """Update city vendor and/or city_slug information"""
        logger.info(f"Updating city ID {city_id}: vendor={vendor}, city_slug={city_slug}")
        
        if vendor is None and city_slug is None:
            logger.warning("No fields to update")
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build update query dynamically
            update_parts = []
            params = []
            
            if vendor is not None:
                update_parts.append("vendor = ?")
                params.append(vendor)
            
            if city_slug is not None:
                update_parts.append("city_slug = ?")
                params.append(city_slug)
            
            # Always update the updated_at timestamp
            update_parts.append("updated_at = CURRENT_TIMESTAMP")
            
            # Add city_id to params
            params.append(city_id)
            
            query = f"""
                UPDATE cities 
                SET {', '.join(update_parts)}
                WHERE id = ?
            """
            
            cursor.execute(query, params)
            
            if cursor.rowcount == 0:
                logger.warning(f"No city found with ID {city_id}")
                conn.commit()
                return False
            
            conn.commit()
            logger.info(f"Successfully updated city ID {city_id}")
            return True