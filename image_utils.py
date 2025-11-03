import os
import requests
import urllib3
import numpy as np
from typing import List, Dict, Optional
from config import BASE_URL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# CONFIGURATION
# ============================================================
BASE_URL = st.secrets.get("BASE_URL")
DEFAULT_TIMEOUT = 200

# ============================================================
# TEXT EMBEDDING API
# ============================================================
def get_text_embedding(text: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[List[float]]:
    """
    Get text embedding from Modal API
    
    Args:
        text: Input text to embed
        timeout: Request timeout in seconds
    
    Returns:
        List of embedding values or None if failed
    """
    try:
        endpoint = f"{BASE_URL}/get_text_embedding"
        payload = {"query_text": text}
        
        print(f"📡 Requesting embedding for: '{text[:50]}...'")
        
        response = requests.post(endpoint, json=payload, timeout=timeout, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            embeddings = data.get("embeddings")
            
            if embeddings:
                print(f"✅ Received embedding (dimension: {len(embeddings)})")
                return embeddings
            else:
                print("⚠️ No embeddings in response")
                return None
        else:
            print(f"❌ API request failed [{response.status_code}]: {response.text.strip()}")
            return None
    
    except requests.exceptions.Timeout:
        print(f"❌ Request timeout after {timeout} seconds")
        return None
    except Exception as e:
        print(f"❌ Error getting text embedding: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# IMAGE SIMILARITY SEARCH
# ============================================================
def get_similar_images(
    db, 
    topic: str, 
    subject: str = "", 
    top_k: int = 2,
    min_similarity: float = 0.0
) -> List[Dict]:
    """
    Find most similar images to a topic using cosine similarity
    
    Args:
        db: Database instance
        topic: Topic name to search for
        subject: Optional subject name for better context
        top_k: Number of top similar images to return
        min_similarity: Minimum similarity threshold (0-1)
    
    Returns:
        List of dicts with image_path, file_name, and similarity_score
    """
    try:
        # Create search query combining topic and subject
        if subject:
            search_query = f"{subject}: {topic}"
        else:
            search_query = topic
        
        print(f"🔍 Searching images for: '{search_query}'")
        
        # Get text embedding for the topic
        text_embedding = get_text_embedding(search_query)
        
        if not text_embedding:
            print("❌ Failed to get text embedding")
            return []
        
        # Query database for similar images using cosine similarity
        conn = db.connect()
        if not conn:
            print("❌ Database connection failed")
            return []
        
        cursor = conn.cursor()
        
        # Convert embedding to PostgreSQL array format
        embedding_str = "[" + ",".join(map(str, text_embedding)) + "]"
        
        # Use cosine similarity: 1 - (embedding <=> query_embedding)
        # <=> is the cosine distance operator in pgvector
        query = """
            SELECT 
                id,
                file_name,
                image_path,
                1 - (embedding <=> %s::vector) AS similarity_score
            FROM image_embeddings
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        
        cursor.execute(query, (embedding_str, embedding_str, top_k))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Format results
        similar_images = []
        for row in results:
            similarity = float(row[3])
            
            # Filter by minimum similarity threshold
            if similarity >= min_similarity:
                similar_images.append({
                    'id': row[0],
                    'file_name': row[1],
                    'image_path': row[2],
                    'similarity_score': round(similarity, 4)
                })
        
        print(f"✅ Found {len(similar_images)} similar images (min similarity: {min_similarity})")
        for img in similar_images:
            print(f"  📸 {img['file_name']} (similarity: {img['similarity_score']*100:.1f}%)")
        
        return similar_images
    
    except Exception as e:
        print(f"❌ Error finding similar images: {e}")
        import traceback
        traceback.print_exc()
        return []


# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors
    
    Args:
        vec1: First vector
        vec2: Second vector
    
    Returns:
        Similarity score between -1 and 1
    """
    try:
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    except Exception as e:
        print(f"❌ Error calculating cosine similarity: {e}")
        return 0.0


def validate_image_path(image_path: str) -> bool:
    """
    Validate if image path exists and is accessible
    
    Args:
        image_path: Path to image file
    
    Returns:
        True if valid, False otherwise
    """
    import os
    try:
        return os.path.exists(image_path) and os.path.isfile(image_path)
    except Exception:
        return False


# ============================================================
# BATCH PROCESSING (Optional - for future use)
# ============================================================
def get_text_embeddings_batch(texts: List[str], timeout: int = 120) -> List[Optional[List[float]]]:
    """
    Get embeddings for multiple texts (if API supports batch)
    
    Args:
        texts: List of texts to embed
        timeout: Request timeout in seconds
    
    Returns:
        List of embeddings (None for failed requests)
    """
    embeddings = []
    
    for text in texts:
        embedding = get_text_embedding(text, timeout)
        embeddings.append(embedding)
    
    return embeddings
