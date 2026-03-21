import json
import os
import re

# Use absolute path to the database
DB_PATH = r"c:\Users\Vladimir\.gemini\antigravity\scratch\knihy-databaze\books_db.json"

_library_data = None

def _load_db():
    global _library_data
    if _library_data is None:
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                _library_data = json.load(f)
        except Exception as e:
            print(f"Error loading library DB: {e}")
            _library_data = {"books": [], "authors": []}
    return _library_data

def _normalize(s: str) -> str:
    # Basic text normalization to improve search hits (similar to what we did in JS)
    s = s.lower()
    # Remove basic punctuation
    s = re.sub(r'[^\w\s]', '', s)
    return s

def search_library(query: str = "", genre: str = "all") -> list[dict]:
    """Search for books matching the query in title or author. Optionally filter by genre."""
    db = _load_db()
    results = []
    q_norm = _normalize(query) if query else ""
    
    for book in db.get("books", []):
        # Filter by genre if specified
        if genre and genre.lower() != "all" and book.get("genre", "").lower() != genre.lower():
            continue
            
        t_norm = _normalize(book.get("title", ""))
        a_norm = _normalize(book.get("author", ""))
        
        if not query or q_norm in t_norm or q_norm in a_norm:
            results.append({
                "title": book.get("title"),
                "author": book.get("author"),
                "genre": book.get("genre"),
                "fame": book.get("fame")
            })
            if len(results) >= 20: # Limit results so we don't overwhelm Gemini context
                break
    return results

def get_books_by_author(author: str) -> list[dict]:
    """Get all books by a specific author."""
    db = _load_db()
    results = []
    q_norm = _normalize(author)
    
    for book in db.get("books", []):
        a_norm = _normalize(book.get("author", ""))
        if q_norm in a_norm:
            results.append({
                "title": book.get("title"),
                "genre": book.get("genre")
            })
            if len(results) >= 50:
                break
    return results

def get_library_stats() -> dict:
    """Get basic statistics about the library."""
    db = _load_db()
    books = db.get("books", [])
    authors = db.get("authors", [])
    
    genres = {}
    for book in books:
        g = book.get("genre", "unknown")
        genres[g] = genres.get(g, 0) + 1
        
    return {
        "total_books": len(books),
        "total_authors": len(authors),
        "genres": genres
    }
