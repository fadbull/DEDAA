"""Helpers for loading ChromaDB collections and resolving folders."""
import os
import chromadb

def load_collection(db_path, name):
    client = chromadb.PersistentClient(path=db_path)
    try:
        col = client.get_collection(name)
    except Exception:
        return None
    return col.get(include=["metadatas", "documents"])


def collection_folder(db_path, collection_name):
    """Return the HNSW vector segment folder for a collection (its data source
    folder inside the ChromaDB dir). Falls back to None if not resolvable."""
    import os
    import sqlite3
    db = os.path.join(db_path, "chroma.sqlite3")
    if not os.path.isfile(db):
        return None
    try:
        con = sqlite3.connect(db)
        try:
            cur = con.cursor()
            cur.execute("SELECT id FROM collections WHERE name=?", (collection_name,))
            row = cur.fetchone()
            if not row:
                return None
            coll_id = row[0]
            # Segment table columns: (id, type, scope, collection).
            # 'scope' holds the segment kind (e.g. 'VECTOR'); 'type' holds the
            # HNSW URN string. Match on scope == 'VECTOR' for the data folder.
            cur.execute("SELECT id, scope, collection FROM segments")
            for seg_id, seg_scope, seg_coll in cur.fetchall():
                if seg_scope == "VECTOR" and seg_coll == coll_id:
                    return seg_id
            return None
        finally:
            con.close()
    except Exception:
        return None


def dir_size_mb(path):
    """Return the total size of a directory in MB (rounded to 2 decimals)."""
    import os
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)
