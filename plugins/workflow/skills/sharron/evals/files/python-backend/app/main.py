from fastapi import FastAPI

app = FastAPI()

ORDERS = {1: {"id": 1, "item": "notebook", "qty": 2}}


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    return ORDERS.get(order_id, {"error": "not found"})
