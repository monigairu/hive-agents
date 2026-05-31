# FastAPI CRUD の参照雛形（L3リソース）

implementer が必要と判断したときだけ読み込む詳細リファレンス。

```python
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

class ItemCreate(BaseModel):
    title: str
    description: Optional[str] = None

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class Item(ItemCreate):
    id: int

_db: dict[int, Item] = {}
_next_id = 1

@app.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate) -> Item:
    global _next_id
    item = Item(id=_next_id, **payload.model_dump())
    _db[_next_id] = item
    _next_id += 1
    return item

@app.get("/items", response_model=list[Item])
def list_items() -> list[Item]:
    return list(_db.values())

@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    return _db[item_id]

@app.put("/items/{item_id}", response_model=Item)
def update_item(item_id: int, payload: ItemUpdate) -> Item:
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    current = _db[item_id]
    updated = current.model_copy(update=payload.model_dump(exclude_unset=True))
    _db[item_id] = updated
    return updated

@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int) -> None:
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    del _db[item_id]
```
